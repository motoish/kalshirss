# Kalshi RSS

[简体中文](README.zh-CN.md)

Turn open Kalshi Events for the topics you follow into an RSS 2.0 feed.

Uses Kalshi's public API. No Kalshi account or API key is required.

## Quick start

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install requests
```

Edit `config.json`, then run:

```bash
python kalshi_rss.py
```

The script writes `feed.xml` to the project root. Import it into an RSS reader or publish it as an online feed.

## Configuration

The two fields you will usually change are `keywords` and `series_tickers`:

```json
{
  "keywords": ["BOJ", "Bank of Japan", "JPY", "yen"],
  "series_tickers": ["KXBOJDECISION"]
}
```

- `series_tickers`: Series to read explicitly. When set, it takes priority and the script does not scan every Series.
- `keywords`: Used to match Series titles, subtitles, and tickers when `series_tickers` is not set.

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

Start a static server from the project root:

```bash
python3 -m http.server 8000
```

Open <http://localhost:8000/public/> for the web preview, or <http://localhost:8000/feed.xml> for the raw RSS file.

Do not open the page directly with `file://`; the browser will block it from reading the local XML file.

## Tests

```bash
pip install pytest
python -m pytest -q
```
