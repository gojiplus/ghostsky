import json
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from scripts import post_random_ghost as bot

NOW = datetime(2026, 10, 23, 16, 0, tzinfo=timezone.utc)
ARTICLE = "https://www.gojiberries.io/example/"


class Response:
    def __init__(self, *, content=b"", text="", data=None):
        self.content = content
        self.text = text
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def test_sitemap_reads_post_urls_without_image_urls():
    xml = b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
      <url><loc>https://www.gojiberries.io/example/</loc>
      <lastmod>2026-10-20</lastmod>
      <image:image><image:loc>https://images.example.com/cover.jpg</image:loc></image:image>
      </url></urlset>"""
    session = Session([Response(content=xml)])

    assert bot.fetch_sitemap_urls(session) == [ARTICLE]
    assert session.calls[0][0] == bot.SITEMAP_URL


def test_latest_uses_rss_publication_date():
    xml = b"""<rss><channel>
      <item><link>https://www.gojiberries.io/old/</link>
      <pubDate>Tue, 01 Jan 2019 00:00:00 GMT</pubDate></item>
      <item><link>https://www.gojiberries.io/new/</link>
      <pubDate>Thu, 01 Oct 2026 00:00:00 GMT</pubDate></item>
      </channel></rss>"""

    assert bot.fetch_latest_urls(Session([Response(content=xml)])) == [
        "https://www.gojiberries.io/new/",
        "https://www.gojiberries.io/old/",
    ]


def test_canonical_url_rejects_other_domains():
    assert bot.canonical_url("https://gojiberries.io/example/?ref=x") == ARTICLE
    with pytest.raises(ValueError, match="Unexpected blog URL"):
        bot.canonical_url("https://example.com/article/")


def test_history_and_selection_respect_cooldown():
    history = [
        {"url": ARTICLE, "posted_at": (NOW - timedelta(days=89)).isoformat()},
        {
            "url": "https://www.gojiberries.io/older/",
            "posted_at": (NOW - timedelta(days=91)).isoformat(),
        },
    ]
    excluded = bot.recent_history_urls(history, NOW)
    assert excluded == {ARTICLE}
    assert (
        bot.choose_url(
            [ARTICLE, "https://www.gojiberries.io/older/"],
            excluded,
            "latest",
            None,
        )
        == "https://www.gojiberries.io/older/"
    )


def test_recent_feed_urls_skips_reposts_and_old_posts():
    def item(url, days_ago, reason=None):
        result = {
            "post": {
                "author": {"handle": "me.bsky.social"},
                "record": {
                    "createdAt": (NOW - timedelta(days=days_ago)).isoformat(),
                    "text": url,
                },
            }
        }
        if reason is not None:
            result["reason"] = reason
        return result

    session = Session(
        [
            Response(
                data={
                    "cursor": "next",
                    "feed": [
                        item(ARTICLE, 1),
                        item("https://www.gojiberries.io/repost/", 2, reason={}),
                    ],
                }
            ),
            Response(
                data={
                    "cursor": "older",
                    "feed": [item("https://www.gojiberries.io/old/", 91)],
                }
            ),
        ]
    )

    assert bot.recent_feed_urls(session, "me.bsky.social", NOW) == {ARTICLE}
    assert session.calls[1][1]["params"]["cursor"] == "next"


def test_metadata_uses_ghost_open_graph_fields():
    html = """<html><head>
      <meta property="og:title" content="An article">
      <meta property="og:description" content="A useful excerpt.">
      </head><body><article><p>Other text</p></article></body></html>"""

    assert bot.fetch_post_metadata(Session([Response(text=html)]), ARTICLE) == (
        "An article",
        "A useful excerpt.",
    )


def test_format_post_limits_length_and_facets_utf8_url():
    text, facets = bot.format_post("Café", "é" * 500, ARTICLE)
    index = facets[0]["index"]

    assert len(text) <= 300
    assert text.endswith(ARTICLE)
    assert (
        text.encode("utf-8")[index["byteStart"] : index["byteEnd"]].decode("utf-8")
        == ARTICLE
    )


def test_format_post_prefers_a_complete_sentence():
    description = (
        "A complete opening sentence that explains the idea in enough detail. "
        + "More detail " * 50
    )

    text, _ = bot.format_post("Title", description, ARTICLE)

    assert (
        "A complete opening sentence that explains the idea in enough detail." in text
    )
    assert "More detail" not in text


def test_record_post_writes_history(tmp_path):
    path = tmp_path / "post_history.json"
    bot.record_post([], ARTICLE, "at://posted", NOW, path)

    assert json.loads(path.read_text())[0] == {
        "url": ARTICLE,
        "posted_at": NOW.isoformat(),
        "post_uri": "at://posted",
    }


def test_dry_run_does_not_publish(monkeypatch, capsys):
    monkeypatch.setattr(bot, "fetch_sitemap_urls", lambda *_: [ARTICLE])
    monkeypatch.setattr(bot, "recent_feed_urls", lambda *_: set())
    monkeypatch.setattr(bot, "load_history", lambda: [])
    monkeypatch.setattr(bot, "fetch_post_metadata", lambda *_: ("Title", "Excerpt"))
    monkeypatch.setattr(
        bot, "record_post", lambda *_: pytest.fail("Dry run must not record a post")
    )
    monkeypatch.setattr(
        sys, "argv", ["post_random_ghost.py", "--dry-run", "--handle", "me.bsky.social"]
    )

    bot.main()

    assert "Title\n\nExcerpt" in capsys.readouterr().out


def test_manual_url_must_be_in_sitemap(monkeypatch):
    monkeypatch.setattr(bot, "fetch_sitemap_urls", lambda *_: [ARTICLE])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_random_ghost.py",
            "--dry-run",
            "--handle",
            "me.bsky.social",
            "--url",
            "https://www.gojiberries.io/not-in-sitemap/",
        ],
    )

    with pytest.raises(SystemExit):
        bot.main()


def test_live_post_records_uri(monkeypatch):
    monkeypatch.setattr(bot, "fetch_sitemap_urls", lambda *_: [ARTICLE])
    monkeypatch.setattr(bot, "recent_feed_urls", lambda *_: set())
    monkeypatch.setattr(bot, "load_history", lambda: [])
    monkeypatch.setattr(bot, "fetch_post_metadata", lambda *_: ("Title", "Excerpt"))
    monkeypatch.setenv("BSKY_PASSWORD", "test-password")
    monkeypatch.setattr(
        sys, "argv", ["post_random_ghost.py", "--handle", "me.bsky.social"]
    )
    recorded = []
    monkeypatch.setattr(bot, "record_post", lambda *args: recorded.append(args))

    class FakeClient:
        def login(self, handle, password):
            assert (handle, password) == ("me.bsky.social", "test-password")

        def send_post(self, text, facets):
            assert text.endswith(ARTICLE)
            assert facets[0]["features"][0]["uri"] == ARTICLE
            return SimpleNamespace(uri="at://posted")

    monkeypatch.setitem(sys.modules, "atproto", SimpleNamespace(Client=FakeClient))
    bot.main()

    assert recorded[0][1:3] == (ARTICLE, "at://posted")
