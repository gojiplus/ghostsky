#!/usr/bin/env python3
import os
import random
import re
import requests
import logging
import argparse
from atproto import Client
from bs4 import BeautifulSoup
from datetime import datetime
import sys

# Configure argument parser
parser = argparse.ArgumentParser(description='Post blog content to Bluesky')
parser.add_argument('--latest', action='store_true', help='Post the latest article instead of a random one')
args = parser.parse_args()

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

# Look for lastmod tags if present
dates = re.findall(r"<lastmod>(.*?)</lastmod>", resp.text)
url_date_pairs = []

if dates and len(dates) == len(urls):
    # If we have dates for all URLs, create pairs for sorting
    logger.info("Found lastmod dates in sitemap")
    url_date_pairs = list(zip(urls, dates))
    
    # Sort by date if we're looking for latest post
    if args.latest:
        logger.info("Sorting URLs by date to find latest post")
        url_date_pairs.sort(key=lambda x: x[1], reverse=True)
        post_url = url_date_pairs[0][0]
        post_date = url_date_pairs[0][1]
        logger.info(f"Selected latest post: {post_url} (date: {post_date})")
    else:
        # Random selection
        logger.info("Selecting random post from sitemap")
        selected_pair = random.choice(url_date_pairs)
        post_url = selected_pair[0]
        post_date = selected_pair[1]
        logger.info(f"Selected random post: {post_url} (date: {post_date})")
else:
    # Fallback to just URLs without dates
    if not urls:
        logger.error("No URLs found in sitemap")
        raise RuntimeError("No URLs found in sitemap")
    
    if args.latest:
        logger.warning("No lastmod dates found in sitemap, cannot determine latest post accurately")
        logger.info("Using URL patterns to try to determine latest post")
        
        # Try to infer latest by URL pattern (many blogs have dates in URLs)
        # This is a fallback approach that may not work for all sites
        date_pattern = re.compile(r'/(20\d{2})/(\d{2})/(\d{2})/')
        dated_urls = []
        
        for url in urls:
            match = date_pattern.search(url)
            if match:
                year, month, day = match.groups()
                date_str = f"{year}-{month}-{day}"
                dated_urls.append((url, date_str))
        
        if dated_urls:
            logger.info("Found dates in URL patterns")
            dated_urls.sort(key=lambda x: x[1], reverse=True)
            post_url = dated_urls[0][0]
            logger.info(f"Selected latest post based on URL pattern: {post_url}")
        else:
            logger.warning("Could not determine dates from URLs, selecting first URL in sitemap")
            post_url = urls[0]
            logger.info(f"Selected first post in sitemap: {post_url}")
    else:
        # Random selection without dates
        logger.info("Selecting random post from sitemap")
        post_url = random.choice(urls)
        logger.info(f"Selected random post: {post_url}")

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

# FIXED: Check if title appears at the start of content to avoid duplication
title_at_start = False
if title and content and len(title) < len(content):
    # Remove any HTML entities or special characters before comparison
    clean_title = re.sub(r'&[a-zA-Z]+;', ' ', title).strip()
    clean_content = re.sub(r'&[a-zA-Z]+;', ' ', content[:len(title)+20]).strip()
    
    # Check if content starts with title (allowing for minor differences)
    if clean_content.startswith(clean_title) or content.startswith(title):
        title_at_start = True
        logger.info("Title appears at the start of content - avoiding duplication")

# Create the message based on what content we have
if title_at_start:
    # If title is already at the start of content, just use content
    combined_text = content
elif title and content:
    # If we have both title and content, combine them
    combined_text = f"{title} - {content}"
else:
    # Use whatever we have
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

logger.info("Script completed successfully")
