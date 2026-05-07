#!/usr/bin/env python3
"""PM x AI Daily — news scraper with content-type tagging and Claude translation"""

import hashlib
import json
import os
import re
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

RSS_SOURCES = [
    ("https://www.producthunt.com/feed", "Product Hunt", "producthunt", "product"),
    ("https://techcrunch.com/feed/", "TechCrunch", "rss", None),
    ("https://venturebeat.com/feed/", "VentureBeat", "rss", None),
    ("https://www.theverge.com/rss/index.xml", "The Verge", "rss", None),
]

HEADERS = {"User-Agent": "Mozilla/5.0 PM-AI-Daily/1.0 (github.com)"}
DAYS_TO_KEEP = 3
TRANSLATE_BATCH = 8


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

def detect_content_type(title, source_type):
    """Classify content into readable type labels."""
    if source_type == "producthunt":
        return "產品發布"
    if source_type == "reddit":
        return "社群討論"
    if source_type == "hn":
        if title.startswith("Show HN:"):
            return "作品展示"
        if title.startswith("Ask HN:"):
            return "問答討論"
        return "技術新聞"
    if source_type == "rss":
        return "產業新聞"
    return "新聞"


# ── Scrapers ──────────────────────────────────────────────────────────────

def fetch_reddit(subreddit, default_category):
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=15"
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
        title = p.get("title", "").strip()
        items.append({
            "id": f"reddit_{p['id']}",
            "title": title,
            "url": f"https://www.reddit.com{p['permalink']}",
            "source": f"r/{subreddit}",
            "source_type": "reddit",
            "category": default_category,
            "content_type": detect_content_type(title, "reddit"),
            "published_at": created.isoformat(),
            "score": p.get("score", 0),
            "comments": p.get("num_comments", 0),
            "summary": p.get("selftext", "")[:300].strip(),
            "title_zh": "",
            "summary_zh": "",
        })
    return items


def fetch_hn(query, category):
    cutoff_ts = int(cutoff_dt().timestamp())
    url = (
        f"https://hn.algolia.com/api/v1/search"
        f"?query={query}&tags=story"
        f"&numericFilters=created_at_i>{cutoff_ts}"
        f"&hitsPerPage=10"
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
        title = h.get("title", "")
        items.append({
            "id": f"hn_{h['objectID']}",
            "title": title,
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
            "source": "Hacker News",
            "source_type": "hn",
            "category": category,
            "content_type": detect_content_type(title, "hn"),
            "published_at": h.get("created_at", now_utc().isoformat()),
            "score": h.get("points", 0),
            "comments": h.get("num_comments", 0),
            "summary": "",
            "title_zh": "",
            "summary_zh": "",
        })
    return items


def fetch_rss(feed_url, source_name, source_type, fallback_category):
    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        print(f"  [RSS/{source_name}] Error: {e}", file=sys.stderr)
        return []

    items = []
    for entry in feed.entries[:20]:
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
            "content_type": detect_content_type(title, source_type),
            "published_at": dt.isoformat(),
            "score": 0,
            "comments": 0,
            "summary": summary,
            "title_zh": "",
            "summary_zh": "",
        })
    return items


# ── Translation ───────────────────────────────────────────────────────────

def translate_batch(batch, client):
    """Send a batch of items to Claude for Chinese title + summary."""
    lines = []
    for i, item in enumerate(batch):
        lines.append(f"{i+1}. 標題: {item['title']}")
        if item.get("summary"):
            lines.append(f"   摘要: {item['summary'][:200]}")

    prompt = (
        "你是台灣科技媒體編輯，請針對以下每篇文章完成兩件事：\n\n"
        "1. title_zh：自然流暢的繁體中文標題（符合台灣媒體風格，勿逐字翻譯）\n"
        "2. summary_zh：以讀完整篇文章的角度，用繁體中文撰寫 3-4 句的閱讀總結。\n"
        "   內容需涵蓋：文章核心論點、關鍵數據或事件、以及對 PM 或 AI 從業者的實際意義。\n"
        "   請用自己的理解與判斷撰寫，而非翻譯原文描述。\n\n"
        "直接回傳 JSON array，不加任何說明文字：\n"
        '[{"title_zh": "...", "summary_zh": "..."}, ...]\n\n'
        "文章列表：\n" + "\n".join(lines)
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        raise ValueError("No JSON array in response")
    return json.loads(match.group())


def add_translations(items, api_key):
    try:
        import anthropic
    except ImportError:
        print("  anthropic not installed, skipping translation")
        return

    client = anthropic.Anthropic(api_key=api_key)
    total = len(items)

    for start in range(0, total, TRANSLATE_BATCH):
        batch = items[start:start + TRANSLATE_BATCH]
        end = start + len(batch)
        print(f"  Translating {start+1}-{end}/{total}...")
        try:
            results = translate_batch(batch, client)
            for j, t in enumerate(results):
                if j < len(batch):
                    batch[j]["title_zh"] = t.get("title_zh", "")
                    batch[j]["summary_zh"] = t.get("summary_zh", "")
        except Exception as e:
            print(f"  Batch {start//TRANSLATE_BATCH+1} failed: {e}", file=sys.stderr)


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

    # Translate (requires ANTHROPIC_API_KEY)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        print(f"\nTranslating {len(unique)} items with Claude...")
        add_translations(unique, api_key)
    else:
        print("\nNo ANTHROPIC_API_KEY — skipping translation")

    os.makedirs("data", exist_ok=True)
    output = {
        "updated_at": now_utc().isoformat(),
        "total": len(unique),
        "items": unique,
    }
    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nDone: {len(unique)} items saved to data/news.json")


if __name__ == "__main__":
    main()
