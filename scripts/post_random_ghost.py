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

urls = re.findall(r"<loc>(.*?)</loc>", resp.text)
if not urls:
    raise RuntimeError("No URLs found in sitemap")

post_url = random.choice(urls)

# --- 2. Build post text and facets ---
message = f"Check out this post: {post_url}"

# Compute byte offsets for the URL in the message
char_start = message.find(post_url)
if char_start < 0:
    raise ValueError(f"URL '{post_url}' not found in message")

prefix_bytes = message[:char_start].encode('utf-8')
url_bytes    = post_url.encode('utf-8')
byte_start   = len(prefix_bytes)
byte_end     = byte_start + len(url_bytes)

facets = [
    {
        "index": {"byteStart": byte_start, "byteEnd": byte_end},
        "features": [
            {
                "$type": "app.bsky.richtext.facet#link",
                "uri": post_url
            }
        ]
    }
]

# --- 3. Login and post to Bluesky ---
client = Client(SPROUT_URL)
client.login(HANDLE, PASSWORD)

res = client.send_post(message, facets=facets)

# Correct attribute access here:
print("Posted to Bluesky:", res.uri)
