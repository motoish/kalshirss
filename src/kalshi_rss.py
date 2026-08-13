from __future__ import annotations

import asyncio
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse

from workers import fetch

DEFAULT_API_URL = "https://external-api.kalshi.com/trade-api/v2/markets"
KALSHI_MARKETS_URL = "https://kalshi.com/markets"
TITLE_FIELDS = ("title", "subtitle")
TICKER_FIELDS = ("ticker", "event_ticker")
EVENTS_PAGE_LIMIT_MAX = 200
FEED_KV_KEY = "feed.xml"
USER_AGENT = "kalshi-rss/0.1"
FETCH_MAX_RETRIES = 8
FETCH_RETRY_BASE_SECONDS = 1.0
FETCH_RETRY_MAX_SECONDS = 30.0
FETCH_PAGE_PAUSE_SECONDS = 0.75

# Bundled into the Worker module — filesystem Path reads are unreliable in Pyodide.
# Prefer explicit series tickers so cron/refresh does not scan ~10k series each run.
DEFAULT_CONFIG: dict[str, Any] = {
    "api_url": DEFAULT_API_URL,
    "keywords": [
        "BOJ",
        "Bank of Japan",
        "JPY",
        "yen",
    ],
    "series_tickers": [
        "KXBOJDECISION",
        "KXCBDECISIONJAPAN",
        "KXJPY",
        "KXJPYINT",
        "KXJPYQ",
        "KXUSDJPY",
        "KXUSDJPYAH",
        "KXUSDJPYAW",
        "KXUSDJPYD",
        "KXUSDJPYE",
        "KXUSDJPYEU",
        "KXUSDJPYH",
        "KXUSDJPYMAX",
        "KXUSDJPYMIN",
        "KXUSDJPYQ",
        "KXUSDJPYW",
        "JPY",
        "USDJPY",
        "USDJPYH",
        "USDJPYMAX",
        "USDJPYMIN",
    ],
    "channel_title": "Kalshi Watch",
    "timeout_seconds": 15,
    "page_limit": 200,
    "max_pages": 5,
}


def _word_boundary_pattern(keyword: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def _is_code_keyword(keyword: str) -> bool:
    return bool(keyword) and " " not in keyword and keyword.isupper()


def matches_series_keywords(entity: dict[str, Any], keywords: list[str]) -> bool:
    title_haystack = "\n".join(str(entity.get(field) or "") for field in TITLE_FIELDS)
    ticker_haystack = "\n".join(str(entity.get(field) or "") for field in TICKER_FIELDS)

    for keyword in keywords:
        cleaned = str(keyword).strip()
        if not cleaned:
            continue
        if _word_boundary_pattern(cleaned).search(title_haystack):
            return True
        if _is_code_keyword(cleaned):
            if cleaned.casefold() in ticker_haystack.casefold():
                return True
            continue
        if _word_boundary_pattern(cleaned).search(ticker_haystack):
            return True
    return False


def _as_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def has_market_activity(market: dict[str, Any]) -> bool:
    volume = _as_float(market.get("volume_24h_fp"))
    if volume is not None and volume > 0:
        return True

    bid_size = _as_float(market.get("yes_bid_size_fp"))
    if bid_size is not None and bid_size > 0:
        return True

    ask_size = _as_float(market.get("yes_ask_size_fp"))
    if ask_size is not None and ask_size > 0:
        return True

    return False


def format_price(value: object) -> str | None:
    parsed = _as_float(value)
    if parsed is None:
        return None
    return f"{parsed * 100:.1f}%"


def _market_summary_line(market: dict[str, Any]) -> str:
    label = str(
        market.get("yes_sub_title")
        or market.get("title")
        or market.get("ticker")
        or "Market"
    )
    bits: list[str] = []
    for field, name in (
        ("yes_bid_dollars", "YES bid"),
        ("yes_ask_dollars", "YES ask"),
        ("last_price_dollars", "Last"),
    ):
        formatted = format_price(market.get(field))
        if formatted is not None:
            bits.append(f"{name}: {formatted}")

    volume = market.get("volume_24h_fp")
    if volume not in (None, ""):
        bits.append(f"24h volume: {volume}")

    ticker = market.get("ticker")
    if ticker:
        bits.append(f"Ticker: {ticker}")

    if not bits:
        return label
    return f"{label} — {'; '.join(bits)}"


def event_description(event: dict[str, Any]) -> str:
    parts: list[str] = []

    sub_title = event.get("sub_title")
    if sub_title:
        parts.append(f"Sub: {sub_title}")

    series_ticker = event.get("series_ticker")
    if series_ticker:
        parts.append(f"Series: {series_ticker}")

    event_ticker = event.get("event_ticker")
    if event_ticker:
        parts.append(f"Event: {event_ticker}")

    markets = [market for market in (event.get("markets") or []) if isinstance(market, dict)]
    active = [market for market in markets if has_market_activity(market)]
    active.sort(key=lambda market: _as_float(market.get("volume_24h_fp")) or 0.0, reverse=True)
    parts.extend(_market_summary_line(market) for market in active)
    return "\n".join(parts)


def _rss_date(value: object) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return format_datetime(parsed.astimezone(timezone.utc))
    except (TypeError, ValueError):
        return None


def _event_latest_timestamp(event: dict[str, Any]) -> str:
    timestamps = [str(event.get("last_updated_ts") or "")]
    for market in event.get("markets") or []:
        if not isinstance(market, dict):
            continue
        timestamps.append(str(market.get("updated_time") or market.get("created_time") or ""))
    return max(timestamps, default="")


def _event_pub_date(event: dict[str, Any]) -> str | None:
    return _rss_date(_event_latest_timestamp(event))


def event_page_url(event: dict[str, Any]) -> str:
    series_ticker = str(event.get("series_ticker") or "").strip()
    event_ticker = str(event.get("event_ticker") or "").strip()
    if series_ticker and event_ticker:
        return f"{KALSHI_MARKETS_URL}/{series_ticker.lower()}/{event_ticker.lower()}"
    return KALSHI_MARKETS_URL


def build_rss(events: list[dict[str, Any]], channel_title: str = "Kalshi Watch") -> bytes:
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = channel_title
    ET.SubElement(channel, "link").text = KALSHI_MARKETS_URL
    ET.SubElement(channel, "description").text = "Open Kalshi events matching configured keywords."

    for event in events:
        event_ticker = str(event.get("event_ticker") or "")
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = str(
            event.get("title") or event_ticker or "Kalshi event"
        )
        ET.SubElement(item, "link").text = event_page_url(event)
        guid = ET.SubElement(item, "guid", {"isPermaLink": "false"})
        guid.text = event_ticker
        ET.SubElement(item, "description").text = event_description(event)

        pub_date = _event_pub_date(event)
        if pub_date:
            ET.SubElement(item, "pubDate").text = pub_date

    ET.indent(rss, space="  ")
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)


def markets_api_url(api_url: str) -> str:
    parsed = urlparse(api_url)
    path = parsed.path.rstrip("/")
    if path.endswith("/series"):
        path = f"{path[: -len('/series')]}/markets"
    elif path.endswith("/events"):
        path = f"{path[: -len('/events')]}/markets"
    elif not path.endswith("/markets"):
        path = f"{path}/markets"
    return parsed._replace(path=path, params="", query="", fragment="").geturl()


def series_api_url(api_url: str) -> str:
    markets_url = markets_api_url(api_url)
    if markets_url.endswith("/markets"):
        return f"{markets_url[: -len('/markets')]}/series"
    return f"{markets_url.rstrip('/')}/series"


def events_api_url(api_url: str) -> str:
    markets_url = markets_api_url(api_url)
    if markets_url.endswith("/markets"):
        return f"{markets_url[: -len('/markets')]}/events"
    return f"{markets_url.rstrip('/')}/events"


def _request_url(base: str, params: dict[str, object]) -> str:
    parsed = urlparse(base)
    query = urlencode({key: str(value) for key, value in params.items()})
    return urlunparse(parsed._replace(query=query))


async def _fetch_json(url: str) -> dict[str, Any]:
    delay = FETCH_RETRY_BASE_SECONDS
    last_error: Exception | None = None

    for attempt in range(FETCH_MAX_RETRIES + 1):
        response = await fetch(url, headers={"User-Agent": USER_AGENT})
        if response.status == 429:
            body = await response.text()
            last_error = RuntimeError(
                f"Kalshi API 429 for {url}: {body[:200]}"
            )
            if attempt >= FETCH_MAX_RETRIES:
                raise last_error
            await asyncio.sleep(delay)
            delay = min(delay * 2, FETCH_RETRY_MAX_SECONDS)
            continue

        if response.status >= 400:
            body = await response.text()
            raise RuntimeError(f"Kalshi API {response.status} for {url}: {body[:200]}")

        payload = await response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"Kalshi API returned non-object JSON for {url}")
        return payload

    assert last_error is not None
    raise last_error


async def _paginated_list(
    url: str,
    result_key: str,
    max_pages: int,
    page_limit: int,
    extra_params: dict[str, object] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()

    for page_index in range(max_pages):
        if page_index > 0:
            await asyncio.sleep(FETCH_PAGE_PAUSE_SECONDS)

        params: dict[str, object] = {"limit": page_limit}
        if extra_params:
            params.update(extra_params)
        if cursor:
            params["cursor"] = cursor

        payload = await _fetch_json(_request_url(url, params))
        page_items = payload.get(result_key) or []
        if isinstance(page_items, list):
            items.extend(item for item in page_items if isinstance(item, dict))

        next_cursor = str(payload.get("cursor") or "")
        if not next_cursor or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    return items


async def fetch_series(
    series_url: str,
    max_pages: int,
    page_limit: int,
) -> list[dict[str, Any]]:
    return await _paginated_list(series_url, "series", max_pages, page_limit)


async def fetch_events_for_series(
    events_url: str,
    series_ticker: str,
    max_pages: int,
    page_limit: int,
) -> list[dict[str, Any]]:
    return await _paginated_list(
        events_url,
        "events",
        max_pages,
        min(page_limit, EVENTS_PAGE_LIMIT_MAX),
        extra_params={
            "series_ticker": series_ticker,
            "status": "open",
            "with_nested_markets": "true",
        },
    )


async def collect_keyword_events(
    events_url: str,
    series_url: str,
    keywords: list[str],
    max_pages: int,
    page_limit: int,
    series_tickers: list[str] | None = None,
) -> list[dict[str, Any]]:
    tickers = [str(value).strip() for value in (series_tickers or []) if str(value).strip()]
    if tickers:
        matched_series = [{"ticker": ticker} for ticker in tickers]
    else:
        series_list = await fetch_series(series_url, max_pages, page_limit)
        matched_series = [
            series for series in series_list if matches_series_keywords(series, keywords)
        ]

    events_by_ticker: dict[str, dict[str, Any]] = {}
    for series_index, series in enumerate(matched_series):
        if series_index > 0:
            await asyncio.sleep(FETCH_PAGE_PAUSE_SECONDS)
        series_ticker = str(series.get("ticker") or "").strip()
        if not series_ticker:
            continue
        for event in await fetch_events_for_series(
            events_url,
            series_ticker=series_ticker,
            max_pages=max_pages,
            page_limit=page_limit,
        ):
            event_ticker = str(event.get("event_ticker") or "").strip()
            if not event_ticker:
                continue

            markets = [
                market
                for market in (event.get("markets") or [])
                if isinstance(market, dict) and has_market_activity(market)
            ]
            if not markets:
                continue

            filtered = dict(event)
            filtered["markets"] = markets
            if not filtered.get("series_ticker"):
                filtered["series_ticker"] = series_ticker
            events_by_ticker[event_ticker] = filtered

    return list(events_by_ticker.values())


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("config.json must contain a JSON object")
    return config


def _sort_key(event: dict[str, Any]) -> str:
    return _event_latest_timestamp(event)


async def refresh_feed_bytes(config: dict[str, Any]) -> bytes:
    keywords = [str(value) for value in config.get("keywords", []) if str(value).strip()]
    series_tickers = [
        str(value).strip()
        for value in (config.get("series_tickers") or [])
        if str(value).strip()
    ]
    api_url = str(config.get("api_url") or DEFAULT_API_URL)
    events_url = events_api_url(api_url)
    series_url = series_api_url(api_url)
    max_pages = int(config.get("max_pages", 20))
    page_limit = int(config.get("page_limit", 1000))
    channel_title = str(config.get("channel_title") or "Kalshi Watch")

    matched = await collect_keyword_events(
        events_url=events_url,
        series_url=series_url,
        keywords=keywords,
        max_pages=max_pages,
        page_limit=page_limit,
        series_tickers=series_tickers,
    )
    matched.sort(key=_sort_key, reverse=True)
    return build_rss(matched, channel_title=channel_title)
