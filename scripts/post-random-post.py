#!/usr/bin/env python3
import os
import random
import requests
from atproto_client import AtprotoClient

# --- Configuration from env ---
SPROUT_URL = "https://bsky.social"  # change if needed
HANDLE     = os.getenv("BSKY_HANDLE")
PASSWORD   = os.getenv("BSKY_PASSWORD")
SITEMAP    = "https://www.gojiberries.io/sitemap-posts.xml"

if not (HANDLE and PASSWORD):
    raise RuntimeError("Missing BSKY_HANDLE / BSKY_PASSWORD environment variables")

# --- 1. Fetch all post URLs from sitemap ---
resp = requests.get(SITEMAP)
resp.raise_for_status()
# Simple regex parse; for production you might use xml.etree
import re
urls = re.findall(r"<loc>(.*?)</loc>", resp.text)
if not urls:
    raise RuntimeError("No URLs found in sitemap")
post = random.choice(urls)

# --- 2. Login and post ---
client = AtprotoClient()
client.login(HANDLE, PASSWORD)

status = f"Check out this post: {post}"
res = client.com.atproto.repo.create_record(
    repo=client.session.handle,
    collection="app.bsky.feed.post",
    record={"text": status}
)

print("Posted to Bluesky:", res["uri"])
