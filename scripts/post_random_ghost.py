#!/usr/bin/env python3
import os
import random
import re
import requests
from atproto import Client

# — configuration —
SPROUT_URL = "https://bsky.social"
HANDLE     = os.getenv("BSKY_HANDLE")
PASSWORD   = os.getenv("BSKY_PASSWORD")
SITEMAP    = os.getenv(
    "SITEMAP_URL",
    "https://www.gojiberries.io/sitemap-posts.xml"
)
MAX_LEN = 300

if not (HANDLE and PASSWORD):
    raise RuntimeError("Missing BSKY_HANDLE / BSKY_PASSWORD env vars")

# — 1. fetch sitemap and pick a post —
resp = requests.get(SITEMAP); resp.raise_for_status()
urls = re.findall(r"<loc>(https?://.*?)</loc>", resp.text)
if not urls:
    raise RuntimeError("No URLs found in sitemap")
post_url = random.choice(urls)

# — 2. fetch the post HTML and extract <title> —
html = requests.get(post_url).text
m = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
title = m.group(1).strip() if m else post_url

# — 3. build message and truncate if necessary —
label = "Read more →"
# we add two newlines between title and label
remaining = MAX_LEN - len(label) - 2
if len(title) > remaining:
    title = title[: remaining - 1].rstrip() + "…"

message = f"{title}\n\n{label}"

# — 4. compute facet over the label text —
# find the byte offsets of the label in the UTF-8 message
char_start = message.find(label)
prefix_b = message[:char_start].encode("utf-8")
label_b  = label.encode("utf-8")
byte_start = len(prefix_b)
byte_end   = byte_start + len(label_b)

facets = [
    {
        "index": {"byteStart": byte_start, "byteEnd": byte_end},
        "features": [
            {"$type": "app.bsky.richtext.facet#link", "uri": post_url}
        ]
    }
]

# — 5. login and post —
client = Client(SPROUT_URL)
client.login(HANDLE, PASSWORD)
res = client.send_post(message, facets=facets)

print("Posted to Bluesky:", res.uri)
