#!/usr/bin/env python3
"""PM x AI Daily — news scraper"""

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import feedparser
import requests

# ── Config ─────────────────────────────────────────────────────────────────

AI_KEYWORDS = {
    "ai", "artificial intelligence", "llm", "gpt", "chatgpt", "claude",
    "gemini", "machine learning", "deep learning", "neural network",
    "language model", "openai", "anthropic", "google ai", "generative ai",
    "gen ai", "foundation model", "copilot", "mistral", "llama", "diffusion",
    "multimodal", "rag", "retrieval augmented", "gpt-4", "gpt-5", "gpt4",
    "gpt5", "image generation", "text generation", "embedding", "vector",
    "stable diffusion", "midjourney", "transformer", "fine-tun",
}

PM_KEYWORDS = {
    "product manager", "product management", "product roadmap", "agile",
    "scrum", "sprint", "user story", "backlog", "stakeholder",
    "product strategy", "go-to-market", "gtm", "user research",
    "product metrics", "okr", "kpi", "feature flag", "a/b test",
    "product discovery", "customer discovery", "product-led",
    "design thinking", "customer journey", "value proposition",
    "product analytics", "feature request", "product owner",
}

REDDIT_SOURCES = [
    ("ProductManagement", "pm"),
    ("artificial", "ai"),
    ("MachineLearning", "ai"),
    ("ChatGPT", "ai"),
    ("LocalLLaMA", "ai"),
    ("AIAssistants", "ai"),
]

HN_QUERIES = [
    ("product management", "pm"),
    ("AI LLM", "ai"),
    ("artificial intelligence", "ai"),
]

# (url, display_name, source_type, fallback_category)
# fallback_category=None → skip if no AI/PM keyword match
# fallback_category="product" → keep anyway (e.g. Product Hunt)
RSS_SOURCES = [
    ("https://www.producthunt.com/feed", "Product Hunt", "producthunt", "product"),
    ("https://techcrunch.com/feed/", "TechCrunch", "rss", None),
    ("https://venturebeat.com/feed/", "VentureBeat", "rss", None),
    ("https://www.theverge.com/rss/index.xml", "The Verge", "rss", None),
]

HEADERS = {"User-Agent": "Mozilla/5.0 PM-AI-Daily/1.0 (github.com)"}
DAYS_TO_KEEP = 3
REDDIT_LIMIT = 15
HN_LIMIT = 10
RSS_LIMIT = 20


# ── Helpers ───────────────────────────────────────────────────────────────

def now_utc():
    return datetime.now(timezone.utc)

def cutoff_dt():
    return now_utc() - timedelta(days=DAYS_TO_KEEP)

def short_hash(s):
    return hashlib.md5(s.encode()).hexdigest()[:8]

def categorize(title, desc=""):
    text = (title + " " + desc).lower()
    pm_score = sum(1 for k in PM_KEYWORDS if k in text)
    ai_score = sum(1 for k in AI_KEYWORDS if k in text)
    if pm_score == 0 and ai_score == 0:
        return None
    return "pm" if pm_score >= ai_score else "ai"


# ── Scrapers ──────────────────────────────────────────────────────────────

def fetch_reddit(subreddit, default_category):
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={REDDIT_LIMIT}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        posts = r.json()["data"]["children"]
    except Exception as e:
        print(f"  [Reddit/{subreddit}] Error: {e}", file=sys.stderr)
        return []

    items = []
    for post in posts:
        p = post["data"]
        if p.get("stickied"):
            continue
        created = datetime.fromtimestamp(p["created_utc"], tz=timezone.utc)
        if created < cutoff_dt():
            continue
        items.append({
            "id": f"reddit_{p['id']}",
            "title": p.get("title", "").strip(),
            "url": f"https://www.reddit.com{p['permalink']}",
            "source": f"r/{subreddit}",
            "source_type": "reddit",
            "category": default_category,
            "published_at": created.isoformat(),
            "score": p.get("score", 0),
            "comments": p.get("num_comments", 0),
            "summary": p.get("selftext", "")[:300].strip(),
        })
    return items


def fetch_hn(query, category):
    cutoff_ts = int(cutoff_dt().timestamp())
    url = (
        f"https://hn.algolia.com/api/v1/search"
        f"?query={query}&tags=story"
        f"&numericFilters=created_at_i>{cutoff_ts}"
        f"&hitsPerPage={HN_LIMIT}"
    )
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        hits = r.json().get("hits", [])
    except Exception as e:
        print(f"  [HN/{query}] Error: {e}", file=sys.stderr)
        return []

    items = []
    for h in hits:
        items.append({
            "id": f"hn_{h['objectID']}",
            "title": h.get("title", ""),
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
            "source": "Hacker News",
            "source_type": "hn",
            "category": category,
            "published_at": h.get("created_at", now_utc().isoformat()),
            "score": h.get("points", 0),
            "comments": h.get("num_comments", 0),
            "summary": "",
        })
    return items


def fetch_rss(feed_url, source_name, source_type, fallback_category):
    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        print(f"  [RSS/{source_name}] Error: {e}", file=sys.stderr)
        return []

    items = []
    for entry in feed.entries[:RSS_LIMIT]:
        title = entry.get("title", "").strip()
        summary = entry.get("summary", "")[:300].strip()

        parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
        dt = datetime(*parsed_time[:6], tzinfo=timezone.utc) if parsed_time else now_utc()
        if dt < cutoff_dt():
            continue

        cat = categorize(title, summary)
        if cat is None:
            if fallback_category is None:
                continue
            cat = fallback_category

        items.append({
            "id": f"rss_{short_hash(entry.get('link', title))}",
            "title": title,
            "url": entry.get("link", ""),
            "source": source_name,
            "source_type": source_type,
            "category": cat,
            "published_at": dt.isoformat(),
            "score": 0,
            "comments": 0,
            "summary": summary,
        })
    return items


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    all_items = []

    print("Reddit...")
    for subreddit, category in REDDIT_SOURCES:
        items = fetch_reddit(subreddit, category)
        print(f"  r/{subreddit}: {len(items)}")
        all_items.extend(items)

    print("Hacker News...")
    for query, category in HN_QUERIES:
        items = fetch_hn(query, category)
        print(f"  HN [{query}]: {len(items)}")
        all_items.extend(items)

    print("RSS feeds...")
    for feed_url, source_name, source_type, fallback_category in RSS_SOURCES:
        items = fetch_rss(feed_url, source_name, source_type, fallback_category)
        print(f"  {source_name}: {len(items)}")
        all_items.extend(items)

    # Deduplicate
    seen = set()
    unique = []
    for item in all_items:
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)

    # Sort newest first
    unique.sort(key=lambda x: x["published_at"], reverse=True)

    os.makedirs("data", exist_ok=True)
    output = {
        "updated_at": now_utc().isoformat(),
        "total": len(unique),
        "items": unique,
    }
    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nTotal: {len(unique)} items saved to data/news.json")


if __name__ == "__main__":
    main()
