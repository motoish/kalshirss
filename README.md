# Kalshi RSS

[简体中文](README.zh-CN.md)

Turn open Kalshi Events for the topics you follow into an RSS 2.0 feed.

Uses Kalshi's public API. No Kalshi account or API key is required.

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --group dev
```

Edit `config.json`, then generate a feed:

```bash
uv run python kalshi_rss.py
```

The script writes `feed.xml` to the project root.

Upload it to KV (remote = production; omit `--remote` for local Wrangler KV):

```bash
uv run pywrangler kv key put feed.xml --path=feed.xml --binding=RSS_KV --remote
```

## Configuration

`series_tickers` and `keywords` are two **mutually exclusive** ways to choose which Series to read. They are not combined.

```json
{
  "keywords": ["BOJ", "Bank of Japan", "JPY", "yen"],
  "series_tickers": ["KXBOJDECISION"]
}
```

**If `series_tickers` is non-empty (this repo's default):**

- Fetch open Events only for those exact Series ticker strings.
- Do **not** scan Kalshi's full Series catalog.
- `keywords` is **ignored** for matching. Keep it as documentation, or clear `series_tickers` if you want keyword scan.

**If `series_tickers` is empty or omitted:**

- Page through all Series and keep those that match `keywords`.
- Title and subtitle: case-insensitive **word-boundary** match (`yen` matches "Japanese yen", not "yenendor").
- Ticker / event ticker: uppercase code keywords like `JPY` or `BOJ` use **substring** match; other keywords still use word boundaries.

Use explicit `series_tickers` in production. Scanning every Series is slow and easy to rate-limit.

Other options:

| Field | Description |
| --- | --- |
| `api_url` | Kalshi Markets API URL |
| `channel_title` | RSS channel title |
| `output` | Output filename; defaults to `feed.xml` |
| `timeout_seconds` | Request timeout in seconds |
| `page_limit` | Number of items per page; Events are automatically capped at 200 |
| `max_pages` | Pagination limit to prevent an endless cursor loop |

## Filtering

```text
Series → open Event → active market → RSS item
```

- Only Events with `status=open` are included.
- A market is kept when its 24-hour volume, YES bid size, or YES ask size is greater than zero.
- Each Event becomes one RSS item. Market prices, volume, and tickers are included in its description.
- The RSS `guid` is the Event ticker, so refreshing the feed does not create a new ID for the same Event.

## Local preview

```bash
uv sync --group dev
uv run python kalshi_rss.py
uv run pywrangler kv key put feed.xml --path=feed.xml --binding=RSS_KV
uv run pywrangler dev
```

Open <http://localhost:8787/> for the web preview, or <http://localhost:8787/feed.xml> for the raw RSS.

Do not open the page with `file://`; the browser cannot read `/feed.xml` that way.

## Tests

```bash
uv run pytest -q
```
