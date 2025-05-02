#!/usr/bin/env python3
import os
import random
import re
import requests
import logging
from atproto import Client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("bluesky_autopost")

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
logger.info(f"Fetching sitemap from {SITEMAP}")
resp = requests.get(SITEMAP)
resp.raise_for_status()
urls = re.findall(r"<loc>(https?://.*?)</loc>", resp.text)
if not urls:
    logger.error("No URLs found in sitemap")
    raise RuntimeError("No URLs found in sitemap")
post_url = random.choice(urls)
logger.info(f"Selected post URL: {post_url}")

# — 2. fetch the post HTML and extract <title> —
logger.info(f"Fetching post content from {post_url}")
try:
    response = requests.get(post_url)
    response.raise_for_status()
    html = response.text
    m = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
    title = m.group(1).strip() if m else post_url
    logger.info(f"Extracted title: {title}")
except Exception as e:
    logger.error(f"Error fetching post: {str(e)}")
    title = post_url
    logger.info(f"Using URL as title: {title}")

# — 3. build message and truncate if necessary —
label = "Read more →"

# Calculate available space for title
# Account for the label text and two newline characters
# Each newline counts as 1 character in the final count
newlines_chars = 2  # Two newlines "\n\n" = 2 characters
available_chars = MAX_LEN - len(label) - newlines_chars

logger.info(f"Maximum message length: {MAX_LEN} characters")
logger.info(f"Label length: {len(label)} characters")
logger.info(f"Available space for title: {available_chars} characters")
logger.info(f"Original title length: {len(title)} characters")

# Truncate title if necessary
original_title = title
if len(title) > available_chars:
    # Leave space for the ellipsis (…) character
    title = title[:available_chars - 1].rstrip() + "…"
    logger.info(f"Title truncated from {len(original_title)} to {len(title)} characters")

# Create the full message
message = f"{title}\n\n{label}"

# Verify message length
actual_length = len(message)
logger.info(f"Final message length: {actual_length}/{MAX_LEN} characters")

if actual_length > MAX_LEN:
    logger.error(f"Message exceeded maximum length: {actual_length} > {MAX_LEN}")
    raise RuntimeError(f"Message exceeded maximum length: {actual_length} > {MAX_LEN}")

logger.info(f"Message: {message}")

# — 4. compute facet over the label text —
# find the byte offsets of the label in the UTF-8 message
logger.info("Computing facets for link embedding")
char_start = message.find(label)
prefix_b = message[:char_start].encode("utf-8")
label_b  = label.encode("utf-8")
byte_start = len(prefix_b)
byte_end   = byte_start + len(label_b)

logger.info(f"Character start: {char_start}")
logger.info(f"Byte start: {byte_start}, Byte end: {byte_end}")

facets = [
    {
        "index": {"byteStart": byte_start, "byteEnd": byte_end},
        "features": [
            {"$type": "app.bsky.richtext.facet#link", "uri": post_url}
        ]
    }
]
logger.info(f"Facets created: {facets}")

# — 5. login and post —
logger.info(f"Logging in to Bluesky as {HANDLE}")
try:
    client = Client(SPROUT_URL)
    client.login(HANDLE, PASSWORD)
    
    logger.info("Sending post to Bluesky")
    res = client.send_post(message, facets=facets)
    
    logger.info(f"Successfully posted to Bluesky: {res.uri}")
    print("Posted to Bluesky:", res.uri)
except Exception as e:
    logger.error(f"Error posting to Bluesky: {str(e)}")
    raise
