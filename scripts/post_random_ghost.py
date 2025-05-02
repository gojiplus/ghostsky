#!/usr/bin/env python3
import os
import random
import re
import requests
import logging
from atproto import Client
from bs4 import BeautifulSoup
import html

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
LABEL = "Read more →"

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

# — 2. fetch the post HTML and extract content —
logger.info(f"Fetching post content from {post_url}")
try:
    response = requests.get(post_url)
    response.raise_for_status()
    html_content = response.text
    
    # Parse HTML with BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract title
    title_tag = soup.find('title')
    title = title_tag.get_text().strip() if title_tag else ""
    logger.info(f"Extracted title: {title}")
    
    # Try to find the main content
    # This is site-specific and may need adjustments
    content = ""
    
    # Look for common content containers
    content_selectors = [
        'article', 
        '.post-content', 
        '.entry-content',
        '.content',
        'main',
        '#content'
    ]
    
    for selector in content_selectors:
        content_element = soup.select_one(selector)
        if content_element:
            # Get only text content, removing HTML tags
            content = content_element.get_text(separator=' ', strip=True)
            if content:
                logger.info(f"Found content using selector: {selector}")
                break
    
    if not content and not title:
        logger.warning("Could not extract content or title from HTML")
        title = post_url
    
except Exception as e:
    logger.error(f"Error fetching post: {str(e)}")
    title = post_url
    content = ""
    logger.info(f"Using URL as title: {title}")

# — 3. build message and truncate if necessary —
# Clean up content - remove extra whitespace
if content:
    content = re.sub(r'\s+', ' ', content).strip()
    
# Calculate available space for our message
newlines_chars = 2  # Two newlines "\n\n" = 2 characters
label_length = len(LABEL)
available_chars = MAX_LEN - label_length - newlines_chars

logger.info(f"Maximum message length: {MAX_LEN} characters")
logger.info(f"Label length: {label_length} characters")
logger.info(f"Available space for content: {available_chars} characters")

# Combine title and content if possible
if title and content:
    combined_text = f"{title} - {content}"
else:
    combined_text = title or content or post_url

logger.info(f"Combined text length (before truncation): {len(combined_text)} characters")

# Truncate if necessary
if len(combined_text) > available_chars:
    # Leave space for the ellipsis (…) character
    combined_text = combined_text[:available_chars - 1].rstrip() + "…"
    logger.info(f"Text truncated to {len(combined_text)} characters")

# Create the full message
message = f"{combined_text}\n\n{LABEL}"

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
char_start = message.find(LABEL)
prefix_b = message[:char_start].encode("utf-8")
label_b  = LABEL.encode("utf-8")
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
