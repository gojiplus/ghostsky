#!/usr/bin/env python3
"""Post a Ghost article from Gojiberries to Bluesky."""

import argparse
import json
import os
import random
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

SITEMAP_URL = "https://www.gojiberries.io/sitemap-posts.xml"
RSS_URL = "https://www.gojiberries.io/rss/"
BLUESKY_API = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
HISTORY_PATH = Path(__file__).resolve().parents[1] / "data" / "post_history.json"
COOLDOWN_DAYS = 90
MAX_POST_LENGTH = 300
BLOG_URL = re.compile(r"https://(?:www\.)?gojiberries\.io/[^\s]+", re.I)


def get_xml(session, url):
    response = session.get(url, timeout=20)
    response.raise_for_status()
    return ElementTree.fromstring(response.content)


def canonical_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "gojiberries.io",
        "www.gojiberries.io",
    }:
        raise ValueError(f"Unexpected blog URL: {url}")
    return f"https://www.gojiberries.io{parsed.path.rstrip('/')}/"


def fetch_sitemap_urls(session):
    root = get_xml(session, SITEMAP_URL)
    urls = []
    for item in root.findall("{*}url"):
        loc = item.findtext("{*}loc")
        if loc:
            urls.append(canonical_url(loc))
    if not urls:
        raise RuntimeError("No posts found in the Ghost sitemap")
    return list(dict.fromkeys(urls))


def fetch_latest_urls(session):
    root = get_xml(session, RSS_URL)
    posts = []
    for item in root.findall("./channel/item"):
        url = item.findtext("link")
        published = item.findtext("pubDate")
        if url and published:
            posts.append((parsedate_to_datetime(published), canonical_url(url)))
    if not posts:
        raise RuntimeError("No published posts found in the Ghost RSS feed")
    return [url for _, url in sorted(posts, reverse=True)]


def load_history(path=HISTORY_PATH):
    if not path.exists():
        return []
    history = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(history, list):
        raise ValueError("Post history must be a JSON list")
    return history


def recent_history_urls(history, now):
    cutoff = now - timedelta(days=COOLDOWN_DAYS)
    return {
        canonical_url(entry["url"])
        for entry in history
        if datetime.fromisoformat(entry["posted_at"]) >= cutoff
    }


def recent_feed_urls(session, handle, now):
    cutoff = now - timedelta(days=COOLDOWN_DAYS)
    urls = set()
    cursor = None
    while True:
        params = {"actor": handle, "limit": 100, "filter": "posts_no_replies"}
        if cursor:
            params["cursor"] = cursor
        response = session.get(BLUESKY_API, params=params, timeout=20)
        response.raise_for_status()
        page = response.json()
        oldest = now
        for item in page.get("feed", []):
            if "reason" in item:
                continue
            post = item["post"]
            if post["author"]["handle"].lower() != handle.lower():
                continue
            record = post["record"]
            created = datetime.fromisoformat(record["createdAt"].replace("Z", "+00:00"))
            oldest = min(oldest, created)
            if created < cutoff:
                continue
            for match in BLOG_URL.finditer(record.get("text", "")):
                urls.add(canonical_url(match.group().rstrip(".,!?:;)")))
        cursor = page.get("cursor")
        if not cursor or not page.get("feed") or oldest < cutoff:
            return urls


def choose_url(urls, excluded, post_type, rng):
    available = [url for url in urls if url not in excluded]
    if not available:
        return None
    return available[0] if post_type == "latest" else rng.choice(available)


def fetch_post_metadata(session, url):
    response = session.get(url, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    title_tag = soup.find("meta", property="og:title")
    description_tag = soup.find("meta", property="og:description")
    title = title_tag.get("content", "") if title_tag else ""
    description = description_tag.get("content", "") if description_tag else ""
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    if not description:
        paragraph = soup.select_one("article p")
        description = paragraph.get_text(" ", strip=True) if paragraph else ""
    return title.strip() or url, description.strip()


def format_post(title, description, url):
    base = title.strip()
    suffix = f"\n\n{url}"
    available = MAX_POST_LENGTH - len(base) - len(suffix) - 2
    if available < 0:
        raise ValueError("Article title and URL exceed the post limit")
    summary = " ".join(description.split())
    summary = re.sub(r"\\([\\$*_`])", r"\1", summary)
    if len(summary) > available:
        head = summary[:available]
        sentence_ends = [
            match.end()
            for match in re.finditer(r"[.!?](?=\s|$)", head)
            if match.end() >= min(60, available // 2)
        ]
        if sentence_ends:
            summary = head[: sentence_ends[-1]]
        else:
            summary = summary[: available - 1].rsplit(" ", 1)[0].rstrip() + "…"
    text = f"{base}\n\n{summary}{suffix}" if summary else f"{base}{suffix}"
    start = len(text[: text.index(url)].encode("utf-8"))
    end = start + len(url.encode("utf-8"))
    facets = [
        {
            "index": {"byteStart": start, "byteEnd": end},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
        }
    ]
    return text, facets


def record_post(history, url, uri, now, path=HISTORY_PATH):
    history.append({"url": url, "posted_at": now.isoformat(), "post_uri": uri})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--post-type", choices=("random", "latest"), default="random")
    parser.add_argument("--url", help="Choose one article from the Ghost sitemap")
    parser.add_argument("--handle", default=os.getenv("BSKY_HANDLE"))
    args = parser.parse_args()
    if not args.handle:
        parser.error("BSKY_HANDLE or --handle is required")

    now = datetime.now(timezone.utc)
    session = requests.Session()
    if args.url:
        url = canonical_url(args.url)
        if url not in fetch_sitemap_urls(session):
            parser.error("--url must be an article in the Ghost sitemap")
        urls = [url]
    else:
        urls = (
            fetch_latest_urls(session)
            if args.post_type == "latest"
            else fetch_sitemap_urls(session)
        )
    history = load_history()
    excluded = recent_history_urls(history, now) | recent_feed_urls(
        session, args.handle, now
    )
    url = choose_url(urls, excluded, args.post_type, random)
    if url is None:
        print("No article is available outside the 90-day cooldown")
        return
    title, description = fetch_post_metadata(session, url)
    text, facets = format_post(title, description, url)
    print(f"Selected {url} ({args.post_type})")
    print(text)
    if args.dry_run:
        return

    password = os.getenv("BSKY_PASSWORD")
    if not password:
        parser.error("BSKY_PASSWORD is required to publish")
    from atproto import Client

    client = Client()
    client.login(args.handle, password)
    result = client.send_post(text, facets=facets)
    record_post(history, url, result.uri, now)
    print(f"Published {result.uri}")


if __name__ == "__main__":
    main()
