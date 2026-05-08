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

AI_KEYWORDS_ZH = {
    "人工智慧", "人工智能", "機器學習", "机器学习", "深度學習", "深度学习",
    "大語言模型", "大语言模型", "語言模型", "语言模型", "生成式",
    "神經網路", "神经网络", "自然語言", "自然语言", "chatgpt", "gpt",
    "claude", "gemini", "llm", "向量", "嵌入", "微調", "微调",
    "模型訓練", "模型训练", "算法", "演算法", "自動化ai", "智慧助理",
    # 補充
    "ai工具", "ai助手", "ai應用", "生成式ai", "大型語言模型",
    "提示詞", "ai代理", "大模型", "基礎模型", "多模態",
    "文字生成", "圖像生成", "文生圖", "ai繪圖", "智慧",
    "openai", "google deepmind", "meta ai",
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

PM_KEYWORDS_ZH = {
    "產品經理", "产品经理", "產品管理", "产品管理", "需求分析",
    "用戶研究", "用户研究", "使用者研究", "敏捷開發", "敏捷", "迭代",
    "產品路線圖", "产品路线图", "產品策略", "产品策略",
    "用戶體驗", "用户体验", "使用者體驗", "ux", "用戶故事",
    "產品思維", "产品思维", "需求文件", "prd", "mvp", "go-to-market",
    # 補充
    "產品設計", "功能設計", "需求規格", "產品開發", "版本迭代",
    "產品上線", "產品優化", "數位產品", "功能需求",
    "saas", "b2b", "b2c", "數位轉型", "系統設計",
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
    # (url, 來源名稱, source_type, fallback_category, max_entries)
    # ── 台灣科技媒體 ──────────────────────────────────────────
    ("https://technews.tw/feed/",                    "科技新報",     "rss",  None,      30),
    ("https://www.inside.com.tw/feed",               "INSIDE",       "rss",  None,      25),
    ("https://www.bnext.com.tw/rss",                 "數位時代",     "rss",  None,      25),
    ("https://www.ithome.com.tw/rss",                "iThome",       "rss",  None,      25),
    ("https://buzzorange.com/techorange/feed/",       "TechOrange",   "rss",  None,      20),
    ("https://meet.bnext.com.tw/feed",               "Meet創業智庫", "rss",  None,      20),
    ("https://www.thenewslens.com/rss.xml",          "TNL媒體",      "rss",  None,      20),
    # ── 台灣社群（PTT） ───────────────────────────────────────
    ("https://www.ptt.cc/bbs/Soft_Job/index.rss",   "PTT Soft_Job", "ptt",  None,      20),
    ("https://www.ptt.cc/bbs/Tech_Job/index.rss",   "PTT Tech_Job", "ptt",  None,      20),
    # ── 中文 PM 媒體 ──────────────────────────────────────────
    ("https://www.woshipm.com/feed",                 "人人都是產品經理", "rss", "pm",   30),
    # ── 中文 AI 媒體 ──────────────────────────────────────────
    ("https://www.qbitai.com/feed",                  "量子位",       "rss",  "ai",      30),
    ("https://www.jiqizhixin.com/rss",               "機器之心",     "rss",  "ai",      30),
    # ── 英文來源（補充） ──────────────────────────────────────
    ("https://www.producthunt.com/feed",             "Product Hunt", "producthunt", "product", 10),
    ("https://techcrunch.com/feed/",                 "TechCrunch",   "rss",  None,      10),
    ("https://venturebeat.com/feed/",                "VentureBeat",  "rss",  None,      10),
    ("https://www.theverge.com/rss/index.xml",       "The Verge",    "rss",  None,      10),
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

def is_chinese(text):
    zh_chars = len(re.findall(r'[一-鿿㐀-䶿]', text))
    return zh_chars / max(len(text), 1) > 0.2

def categorize(title, desc=""):
    text = (title + " " + desc).lower()
    pm_score = sum(1 for k in PM_KEYWORDS if k in text)
    ai_score = sum(1 for k in AI_KEYWORDS if k in text)
    # Also check Chinese keywords
    pm_score += sum(1 for k in PM_KEYWORDS_ZH if k in text)
    ai_score += sum(1 for k in AI_KEYWORDS_ZH if k in text)
    if pm_score == 0 and ai_score == 0:
        return None
    return "pm" if pm_score >= ai_score else "ai"

def extract_rss_body(entry):
    """Extract full plain-text body from an RSS entry (uses content:encoded if available)."""
    html = ''
    if hasattr(entry, 'content') and entry.content:
        html = entry.content[0].get('value', '')
    if not html:
        html = entry.get('summary', '')
    if not html:
        return ''
    text = re.sub(r'<[^>]+>', ' ', html)
    for entity, char in [('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'),
                          ('&quot;', '"'), ('&#x27;', "'"), ('&apos;', "'"), ('&nbsp;', ' ')]:
        text = text.replace(entity, char)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()[:5000]


def detect_content_type(title, source_type):
    """Classify content into readable type labels."""
    if source_type == "producthunt":
        return "產品發布"
    if source_type == "reddit":
        return "社群討論"
    if source_type == "ptt":
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
    url = f"https://www.reddit.com/r/{subreddit}/hot.rss?limit=15"
    rss_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    try:
        feed = feedparser.parse(url, request_headers=rss_headers)
        if not feed.entries:
            raise ValueError("empty feed")
    except Exception as e:
        print(f"  [Reddit/{subreddit}] Error: {e}", file=sys.stderr)
        return []

    items = []
    for entry in feed.entries[:15]:
        title = entry.get("title", "").strip()
        parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
        created = datetime(*parsed_time[:6], tzinfo=timezone.utc) if parsed_time else now_utc()
        if created < cutoff_dt():
            continue
        post_id = short_hash(entry.get("link", title))
        raw_summary = entry.get("summary", "")
        reddit_body = re.sub(r'<[^>]+>', ' ', raw_summary)
        reddit_body = re.sub(r'\s+', ' ', reddit_body).strip()[:3000]
        items.append({
            "id": f"reddit_{post_id}",
            "title": title,
            "url": entry.get("link", ""),
            "source": f"r/{subreddit}",
            "source_type": "reddit",
            "category": default_category,
            "content_type": detect_content_type(title, "reddit"),
            "published_at": created.isoformat(),
            "score": 0,
            "comments": 0,
            "summary": raw_summary[:300].strip(),
            "body_text": reddit_body,
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
            "body_text": "",
            "title_zh": "",
            "summary_zh": "",
        })
    return items


def fetch_rss(feed_url, source_name, source_type, fallback_category, max_entries=20):
    try:
        feed = feedparser.parse(feed_url, request_headers={"User-Agent": HEADERS["User-Agent"]})
    except Exception as e:
        print(f"  [RSS/{source_name}] Error: {e}", file=sys.stderr)
        return []

    items = []
    for entry in feed.entries[:max_entries]:
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
            "id": f"{source_type}_{short_hash(entry.get('link', title))}",
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
            "body_text": extract_rss_body(entry),
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
        "1. title_zh：\n"
        "   - 若標題為英文 → 翻譯成自然流暢的繁體中文（符合台灣媒體風格）\n"
        "   - 若標題為中文 → 直接使用原標題，若為簡體則轉為繁體\n"
        "2. summary_zh：以讀完整篇文章的角度，用繁體中文撰寫 3-4 句的閱讀總結。\n"
        "   內容需涵蓋：文章核心論點、關鍵數據或事件、以及對 PM 或 AI 從業者的實際意義。\n"
        "   請用自己的理解與判斷撰寫，而非翻譯或複製原文描述。\n\n"
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
    for feed_url, source_name, source_type, fallback_category, max_entries in RSS_SOURCES:
        items = fetch_rss(feed_url, source_name, source_type, fallback_category, max_entries)
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
