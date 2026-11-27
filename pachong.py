"""Collect Medium publication metadata from RSS feeds."""
from __future__ import annotations

import argparse
import csv
import json
import random
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import requests
from requests import Response

PUBLICATION_SLUG = "inst414-data-science-tech"
SEED_TAG = "inst414featured"
FIELDS = ["title", "link", "pubDate", "author", "tags", "source"]
USER_AGENT = "Mozilla/5.0 (compatible; INST414AcademicProject/1.0; +https://github.com/Lin0359/414A2)"


@dataclass
class Article:
    title: str
    link: str
    pubDate: str
    author: str
    tags: list[str]
    source: str


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.netloc.lower().endswith("medium.com"):
        path = parts.path.rstrip("/")
        if parts.netloc.lower() == "www.medium.com":
            parts = parts._replace(netloc="medium.com")
        return urlunsplit((parts.scheme or "https", parts.netloc, path, "", ""))
    return url.strip()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def element_text(element: ET.Element, names: set[str]) -> str:
    for child in element.iter():
        if local_name(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def parse_feed(content: bytes, source: str) -> list[Article]:
    root = ET.fromstring(content)
    articles = []
    for item in root.iter():
        if local_name(item.tag) not in {"item", "entry"}:
            continue
        title = element_text(item, {"title"})
        link = ""
        for child in item:
            if local_name(child.tag) == "link":
                link = child.attrib.get("href", "") or (child.text or "").strip()
                if child.attrib.get("rel", "alternate") == "alternate":
                    break
        if not link:
            continue
        author = element_text(item, {"creator", "author"})
        pub_date = element_text(item, {"pubdate", "published", "updated"})
        tags = [child.attrib.get("term", "").strip() or (child.text or "").strip()
                for child in item.iter() if local_name(child.tag) == "category"]
        articles.append(Article(title, canonical_url(link), pub_date, author,
                                list(dict.fromkeys(tag for tag in tags if tag)), source))
    return articles


def fetch_feed(session: requests.Session, url: str, retries: int) -> bytes:
    for attempt in range(retries + 1):
        response: Response = session.get(url, timeout=25)
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == retries:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2 ** attempt + random.random(), 30)
            time.sleep(delay)
            continue
        response.raise_for_status()
        return response.content
    raise RuntimeError(f"Unable to fetch feed: {url}")


def collect(target: int, delay: float, retries: int) -> list[Article]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    feeds = [(f"https://medium.com/feed/{PUBLICATION_SLUG}", "publication")]
    found: dict[str, Article] = {}
    index = 0
    while index < len(feeds) and len(found) < target:
        url, source = feeds[index]
        index += 1
        try:
            items = parse_feed(fetch_feed(session, url, retries), source)
        except (requests.RequestException, ET.ParseError) as error:
            print(f"Skipped {url}: {error}")
            continue
        for article in items:
            if article.link:
                found.setdefault(article.link, article)
                for tag in article.tags:
                    tag_url = f"https://medium.com/feed/tag/{tag}"
                    if len(feeds) < target * 2 and all(existing[0] != tag_url for existing in feeds):
                        feeds.append((tag_url, f"tag:{tag}"))
        if index < len(feeds) and len(found) < target:
            time.sleep(max(0, delay))
    return list(found.values())[:target]


def save_articles(articles: list[Article], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = output_dir / f"medium_articles_{stamp}.csv"
    json_path = output_dir / f"medium_articles_{stamp}.json"
    rows = [asdict(article) for article in articles]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            row["tags"] = "|".join(row["tags"])
            writer.writerow(row)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=100, help="Maximum unique articles to collect.")
    parser.add_argument("--output-dir", type=Path, default=Path("data"), help="Folder for the CSV and JSON files.")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between feed requests.")
    parser.add_argument("--retries", type=int, default=4, help="Retries for rate limits and temporary server errors.")
    args = parser.parse_args()
    if args.target < 1 or args.retries < 0 or args.delay < 0:
        parser.error("--target must be positive; --retries and --delay cannot be negative.")
    articles = collect(args.target, args.delay, args.retries)
    csv_path, json_path = save_articles(articles, args.output_dir)
    print(f"Collected {len(articles)} unique articles.")
    print(f"CSV:  {csv_path.resolve()}")
    print(f"JSON: {json_path.resolve()}")


if __name__ == "__main__":
    main()
