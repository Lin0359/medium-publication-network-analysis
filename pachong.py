"""
INST414 Medium RSS Collector (rate-limit friendly)

Fixes:
- Handles HTTP 429 with exponential backoff + jitter
- Adds polite delay between requests
- If publication feed is blocked, continue with tag feeds (still enough data)
- Limits expansion to avoid spamming Medium

Outputs:
- CSV + JSON with fields: title, link (canonical), pubDate, author, tags, source
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
import random
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Set, Tuple
from urllib.parse import urlsplit, urlunsplit, quote

import requests
from bs4 import BeautifulSoup


# ===================== EDIT THESE =====================
PUBLICATION_SLUG = "inst414-data-science-tech"
SEED_TAG = "inst414featured"
TARGET = 100
OUT_DIR = r"C:\Users\hl667\Desktop\代码作业\414\A2"
# ======================================================

TIMEOUT = 30

# Polite crawling controls
BASE_DELAY_SEC = 2.0          # wait between successful requests
JITTER_SEC = 1.5              # random extra wait
MAX_RETRIES = 6               # retries for 429/5xx
BACKOFF_BASE = 2.0            # exponential backoff base


@dataclass
class Post:
    title: str
    link: str
    pubDate: str
    author: str
    tags: List[str]
    source: str


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def canonicalize(url: str) -> str:
    """Remove query parameters to deduplicate."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def safe_filename(s: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", (s or "").strip())
    return s[:120] if len(s) > 120 else s


def slugify_tag(tag: str) -> str:
    t = (tag or "").strip().lower()
    t = re.sub(r"\s+", "-", t)
    t = re.sub(r"[^a-z0-9\-]", "", t)
    t = re.sub(r"\-+", "-", t).strip("-")
    return t


def feed_publication(slug: str, limit: int = 100) -> str:
    slug = slug.strip().strip("/")
    return f"https://medium.com/feed/{slug}?limit={limit}"


def feed_tag(tag: str, limit: int = 100) -> str:
    slug = slugify_tag(tag)
    slug = quote(slug)
    return f"https://medium.com/feed/tag/{slug}?limit={limit}"


def polite_sleep():
    time.sleep(BASE_DELAY_SEC + random.random() * JITTER_SEC)


def fetch_xml(url: str) -> str:
    """
    Fetch RSS XML with retry on 429 / transient errors.
    """
    headers = {
        # More browser-like UA helps a bit
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT)
            if r.status_code == 200:
                polite_sleep()
                return r.text

            # Handle 429 rate limiting
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = int(retry_after)
                else:
                    # exponential backoff + jitter
                    wait = (BACKOFF_BASE ** attempt) + random.random() * 2.0
                print(f"429 Too Many Requests. Backing off for {wait:.1f}s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
                last_err = RuntimeError(f"HTTP 429 for {url}")
                continue

            # 5xx retry
            if 500 <= r.status_code < 600:
                wait = (BACKOFF_BASE ** attempt) + random.random() * 2.0
                print(f"{r.status_code} Server error. Retrying in {wait:.1f}s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
                last_err = RuntimeError(f"HTTP {r.status_code} for {url}")
                continue

            # Other errors: stop
            r.raise_for_status()

        except Exception as e:
            last_err = e
            wait = (BACKOFF_BASE ** attempt) + random.random() * 2.0
            print(f"Request error: {e}. Retrying in {wait:.1f}s (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(wait)

    raise last_err if last_err else RuntimeError("Unknown fetch error")


def parse_rss(xml_text: str, source: str) -> List[Post]:
    soup = BeautifulSoup(xml_text, "xml")
    items = soup.find_all("item")
    posts: List[Post] = []

    for it in items:
        title = normalize(it.find("title").get_text(strip=True) if it.find("title") else "")
        raw_link = normalize(it.find("link").get_text(strip=True) if it.find("link") else "")
        link = canonicalize(raw_link)

        pub_date = normalize(it.find("pubDate").get_text(strip=True) if it.find("pubDate") else "")
        creator = it.find("dc:creator")
        author = normalize(creator.get_text(strip=True) if creator else "")

        categories = [normalize(c.get_text(strip=True)) for c in it.find_all("category")]
        seen = set()
        tags: List[str] = []
        for t in categories:
            if t and t not in seen:
                seen.add(t)
                tags.append(t)

        if title and link:
            posts.append(Post(title=title, link=link, pubDate=pub_date, author=author, tags=tags, source=source))

    return posts


def merge(store: Dict[str, Post], new_posts: List[Post]) -> int:
    added = 0
    for p in new_posts:
        if not p.link:
            continue
        if p.link not in store:
            store[p.link] = p
            added += 1
        else:
            if len(p.tags) > len(store[p.link].tags):
                store[p.link] = p
    return added


def top_tags_from_store(store: Dict[str, Post], limit: int = 25) -> List[Tuple[str, int]]:
    freq: Dict[str, int] = {}
    for p in store.values():
        for t in p.tags:
            freq[t] = freq.get(t, 0) + 1
    return sorted(freq.items(), key=lambda x: x[1], reverse=True)[:limit]


def write_csv(posts: List[Post], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["title", "link", "pubDate", "author", "tags", "source"])
        for p in posts:
            w.writerow([p.title, p.link, p.pubDate, p.author, "|".join(p.tags), p.source])


def write_json(posts: List[Post], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in posts], f, ensure_ascii=False, indent=2)


def print_stats(posts: List[Post]) -> None:
    print(f"\nCollected unique posts: {len(posts)}")
    if not posts:
        return
    total_tags = sum(len(p.tags) for p in posts)
    print(f"Total tags assigned (sum over posts): {total_tags}")
    print(f"Avg tags per post: {total_tags / len(posts):.2f}")

    freq: Dict[str, int] = {}
    for p in posts:
        for t in p.tags:
            freq[t] = freq.get(t, 0) + 1
    print("\nTop tags:")
    for t, c in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:12]:
        print(f"- {t}: {c}")

    print("\nSample (first 3):")
    for p in posts[:3]:
        print(f"- {p.title} | tags={len(p.tags)} | {p.link}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    store: Dict[str, Post] = {}
    tried_tags: Set[str] = set()

    # 1) Always start from the course tag feed (most relevant + usually enough)
    seed_tag_url = feed_tag(SEED_TAG, limit=100)
    print(f"Fetching SEED TAG feed: {seed_tag_url}")
    xml = fetch_xml(seed_tag_url)
    seed_posts = parse_rss(xml, source=f"tag:{slugify_tag(SEED_TAG)}")
    merge(store, seed_posts)
    tried_tags.add(SEED_TAG)
    print(f"  -> items={len(seed_posts)}, unique total={len(store)}")

    # 2) Try publication feed, but if it 429s, do NOT crash—just continue
    pub_url = feed_publication(PUBLICATION_SLUG, limit=100)
    print(f"\nFetching PUBLICATION feed: {pub_url}")
    try:
        xml = fetch_xml(pub_url)
        pub_posts = parse_rss(xml, source=f"publication:{PUBLICATION_SLUG}")
        merge(store, pub_posts)
        print(f"  -> items={len(pub_posts)}, unique total={len(store)}")
    except Exception as e:
        print(f"  -> Skipped publication feed due to error: {e}")

    # 3) Expansion via additional tags (rate-limit friendly)
    # Limit rounds to avoid too many requests.
    round_num = 0
    MAX_ROUNDS = 4   # keep small to avoid 429
    TAGS_PER_ROUND = 8

    while len(store) < TARGET and round_num < MAX_ROUNDS:
        round_num += 1
        ranked_tags = [t for t, _ in top_tags_from_store(store, limit=30) if t not in tried_tags]
        if not ranked_tags:
            break

        to_try = ranked_tags[:TAGS_PER_ROUND]
        print(f"\nExpansion round {round_num}: trying {len(to_try)} tag feeds...")

        for t in to_try:
            tried_tags.add(t)
            url = feed_tag(t, limit=100)
            print(f"  Fetching tag feed: {url}")
            try:
                xml = fetch_xml(url)
                posts = parse_rss(xml, source=f"tag:{slugify_tag(t)}")
                added = merge(store, posts)
                print(f"   -> items={len(posts)}, added={added}, unique total={len(store)}")
            except Exception as e:
                print(f"   -> Skipped tag '{t}' due to error: {e}")

        # If Medium is strict today, you can manually stop earlier
        if len(store) < TARGET:
            print(f"Current unique={len(store)} (target={TARGET}). Continuing politely...")

    posts_list = list(store.values())
    posts_list = sorted(posts_list, key=lambda p: p.pubDate, reverse=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"medium_{safe_filename(PUBLICATION_SLUG)}_{safe_filename(SEED_TAG)}_{ts}"
    out_csv = os.path.join(OUT_DIR, base + ".csv")
    out_json = os.path.join(OUT_DIR, base + ".json")

    write_csv(posts_list, out_csv)
    write_json(posts_list, out_json)

    print_stats(posts_list)
    print(f"\nSaved CSV : {out_csv}")
    print(f"Saved JSON: {out_json}")


if __name__ == "__main__":
    main()