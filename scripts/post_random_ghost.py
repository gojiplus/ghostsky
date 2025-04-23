#!/usr/bin/env python3
import os
import random
import re
import requests
from atproto import Client

# --- Configuration from env ---
SPROUT_URL = "https://bsky.social"
HANDLE     = os.getenv("BSKY_HANDLE")
PASSWORD   = os.getenv("BSKY_PASSWORD")
SITEMAP    = os.getenv(
    "SITEMAP_URL",
    "https://www.gojiberries.io/sitemap-posts.xml"
)

if not (HANDLE and PASSWORD):
    raise RuntimeError("Missing BSKY_HANDLE / BSKY_PASSWORD environment variables")

# --- 1. Fetch all post URLs from sitemap ---
resp = requests.get(SITEMAP)
resp.raise_for_status()

# Simple regex parse; for production you might use xml.etree.ElementTree
urls = re.findall(r"<loc>(.*?)</loc>", resp.text)
if not urls:
    raise RuntimeError("No URLs found in sitemap")

post_url = random.choice(urls)

# --- 2. Login and post to Bluesky ---
client = Client(service=SPROUT_URL)
client.login(HANDLE, PASSWORD)

message = f"Check out this post: {post_url}"
res = client.send_post(message)

print("Posted to Bluesky:", res["uri"])
