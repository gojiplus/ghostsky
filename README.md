## &#x1F47B;&#x1F98B; Post Random Ghost Blog to Bluesky

Fetch a random post from your Ghost blog’s sitemap and publish it to your Bluesky feed on a schedule or on demand.

## Features

- Reads all post URLs from your Ghost sitemap (`sitemap-posts.xml`)
- Picks one at random each run
- Authenticates and posts via the Bluesky AT Protocol client
- Fully configurable via Action inputs

## Usage

### 1. Add the Action to your repo

Create a folder `.github/actions/post-ghost` and put both:
- [action.yaml](#action-metadata)  
- `scripts/post_random_ghost.py` (from earlier)

### 2. Configure Secrets

Go to **Settings → Secrets** and add:
- `BSKY_HANDLE` – your Bluesky username
- `BSKY_PASSWORD` – your Bluesky password

### 3. Example workflow

```yaml
name: 🥝 Post Random Ghost Blog to Bluesky

on:
  schedule:
    - cron: '0 16 * * *'     # every day at 16:00 UTC
  workflow_dispatch:         # allow manual trigger

jobs:
  post:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Post random blog link
        uses: ./.github/actions/post-ghost
        with:
          handle: ${{ secrets.BSKY_HANDLE }}
          password: ${{ secrets.BSKY_PASSWORD }}
          sitemap-url: https://www.gojiberries.io/sitemap-posts.xml
```

### Inputs

| Name        | Description                                     | Required | Default                                 |
|-------------|-------------------------------------------------|:--------:|:----------------------------------------|
| `handle`      | Your Bluesky handle (username)                  | ✅       |                                          |
| `password`    | Your Bluesky password                           | ✅       |                                          |
| `sitemap-url` | Full URL to your Ghost blog’s `sitemap-posts.xml` | ✅       | `https://yourblog.com/sitemap-posts.xml` |



### How it works

1. Fetch the sitemap (XML) and extract all <loc> URLs
2. Choose one at random
3. Login to Bluesky via atproto-client
4. Post a status like
