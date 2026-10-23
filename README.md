# Ghostsky

Ghostsky shares articles from [Gojiberries](https://www.gojiberries.io/) on
Bluesky. It posts an article title, a shortened excerpt, and a clickable link.

## Selection and schedule

- Scheduled runs choose a random article from the Ghost post sitemap.
- Manual runs can choose `latest`, which uses publication dates in the RSS feed.
  Sitemap `lastmod` dates reflect later edits and are not publication dates.
- Articles posted in the last 90 days are excluded. The workflow commits
  successful posts to `data/post_history.json` and checks recent Bluesky posts
  before choosing, so a retry after a failed history commit avoids a duplicate.

The workflow runs at 9:17 a.m. Pacific time on Tuesday and Thursday, between
Advertiser's Monday, Wednesday, and Friday repository posts. GitHub may delay
scheduled runs.

## Setup and preview

Set `BSKY_HANDLE` and `BSKY_PASSWORD` as repository Actions secrets. Use a
Bluesky app password. The workflow uses the built-in `GITHUB_TOKEN` with
`contents: write` only for its posting job, to save post history.

Use **Actions → Post Ghost Blog to Bluesky → Run workflow**. Manual runs default
to a dry run, which fetches the article and prints its final post text without
publishing. Choose `latest` to preview a recent article, or enter an
`article_url` from the sitemap to preview and publish that exact article. Set
`dry_run` to false for a live post.

To preview locally:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/post_random_ghost.py --dry-run --handle YOUR_HANDLE
```

No Bluesky password is needed for a dry run.

## Development checks

```sh
black --check scripts tests
isort --check-only scripts tests
flake8 scripts tests
python -m pytest -q
actionlint .github/workflows/ghost-post.yaml
```
