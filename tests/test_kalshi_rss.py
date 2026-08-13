import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from kalshi_rss import (
    event_description,
    format_price,
    has_market_activity,
    market_description,
    matches_series_keywords,
)


def test_matches_series_keywords_case_insensitive_across_supported_fields():
    series = {
        "title": "Will the Bank of Japan raise rates?",
        "subtitle": "Policy meeting",
        "ticker": "KXBOJ-26SEP",
        "event_ticker": "KX-JAPAN-RATES",
    }

    assert matches_series_keywords(series, ["bank of japan"])
    assert matches_series_keywords(series, ["BOJ"])
    assert matches_series_keywords(series, ["japan"])
    assert not matches_series_keywords(series, ["ECB"])


def test_matches_series_keywords_tolerates_missing_fields():
    assert not matches_series_keywords({"title": None}, ["yen"])


def test_matches_series_keywords_uses_word_boundaries_on_title_fields():
    assert not matches_series_keywords(
        {"title": "yes Sonja Zhiyenbayeva,yes Francisca Jorge"},
        ["yen"],
    )
    assert not matches_series_keywords(
        {"title": "yes Federico Cina"},
        ["Fed"],
    )
    assert matches_series_keywords(
        {"title": "Will the yen weaken further?"},
        ["yen"],
    )
    assert matches_series_keywords(
        {"title": "Fed rate decision"},
        ["Fed"],
    )


def test_matches_series_keywords_still_matches_ticker_substrings():
    assert matches_series_keywords({"ticker": "KXJPY-26SEP"}, ["JPY"])
    assert matches_series_keywords({"event_ticker": "KXBOJ"}, ["BOJ"])
    assert not matches_series_keywords({"ticker": "KXSPX"}, ["JPY"])


def test_matches_series_keywords_code_tickers_only_substring_for_uppercase():
    assert not matches_series_keywords({"ticker": "KXFRYENDORSE"}, ["yen"])
    assert matches_series_keywords({"title": "Japanese yen exchange rate"}, ["yen"])
    assert matches_series_keywords({"ticker": "KXUSDJPYW-26AUG"}, ["JPY"])


def test_fetch_series_follows_cursor_pagination():
    from kalshi_rss import fetch_series

    session = FakeSession(
        [
            FakeResponse({"series": [{"ticker": "KXJPY", "title": "Yen"}], "cursor": "s1"}),
            FakeResponse({"series": [{"ticker": "KXBOJ", "title": "BOJ"}], "cursor": ""}),
        ]
    )

    series = fetch_series(
        session,
        "https://example.test/series",
        timeout=5,
        max_pages=10,
        page_limit=200,
    )
    assert [item["ticker"] for item in series] == ["KXJPY", "KXBOJ"]
    assert session.calls[0]["params"] == {"limit": 200}
    assert session.calls[1]["params"] == {"limit": 200, "cursor": "s1"}


def test_fetch_events_for_series_requests_open_nested_markets():
    from kalshi_rss import fetch_events_for_series

    session = FakeSession(
        [
            FakeResponse(
                {
                    "events": [
                        {
                            "event_ticker": "KXJPY-1",
                            "title": "Yen event",
                            "markets": [{"ticker": "M1", "status": "active"}],
                        }
                    ],
                    "cursor": "",
                }
            )
        ]
    )

    events = fetch_events_for_series(
        session,
        "https://example.test/events",
        series_ticker="KXJPY",
        timeout=5,
        max_pages=3,
        page_limit=100,
    )
    assert [event["event_ticker"] for event in events] == ["KXJPY-1"]
    assert session.calls[0]["params"] == {
        "limit": 100,
        "series_ticker": "KXJPY",
        "status": "open",
        "with_nested_markets": "true",
    }


def test_fetch_events_for_series_clamps_page_limit():
    from kalshi_rss import fetch_events_for_series

    session = FakeSession([FakeResponse({"events": [], "cursor": ""})])
    fetch_events_for_series(
        session,
        "https://example.test/events",
        series_ticker="KXJPY",
        timeout=5,
        max_pages=1,
        page_limit=1000,
    )
    assert session.calls[0]["params"]["limit"] == 200


def test_collect_keyword_events_returns_one_item_per_active_event():
    from kalshi_rss import collect_keyword_events

    class MultiSession:
        def __init__(self):
            self.calls = []
            self._series = FakeResponse(
                {
                    "series": [
                        {"ticker": "KXJPY", "title": "U.S. Dollar/Japanese yen"},
                        {"ticker": "KXSPX", "title": "S&P 500"},
                    ],
                    "cursor": "",
                }
            )
            self._events = {
                "KXJPY": FakeResponse(
                    {
                        "events": [
                            {
                                "event_ticker": "KXJPY-26AUG",
                                "title": "USD/JPY price on Aug 26",
                                "series_ticker": "KXJPY",
                                "last_updated_ts": "2026-08-13T01:00:00Z",
                                "markets": [
                                    {
                                        "ticker": "KXJPY-26AUG-HOLD",
                                        "yes_sub_title": "Hold",
                                        "yes_bid_size_fp": "10.00",
                                        "yes_ask_size_fp": "0.00",
                                        "volume_24h_fp": "0.00",
                                        "yes_bid_dollars": "0.40",
                                        "yes_ask_dollars": "0.45",
                                    },
                                    {
                                        "ticker": "KXJPY-26AUG-EMPTY",
                                        "yes_sub_title": "Above 158.959",
                                        "yes_bid_size_fp": "0.00",
                                        "yes_ask_size_fp": "0.00",
                                        "volume_24h_fp": "0.00",
                                    },
                                ],
                            },
                            {
                                "event_ticker": "KXJPY-EMPTY",
                                "title": "Empty event",
                                "markets": [
                                    {
                                        "ticker": "DEAD",
                                        "yes_bid_size_fp": "0",
                                        "yes_ask_size_fp": "0",
                                        "volume_24h_fp": "0",
                                    }
                                ],
                            },
                        ],
                        "cursor": "",
                    }
                ),
            }

        def get(self, url, params, timeout):
            self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
            if url.endswith("/series"):
                return self._series
            return self._events[params["series_ticker"]]

    events = collect_keyword_events(
        MultiSession(),
        events_url="https://example.test/events",
        series_url="https://example.test/series",
        keywords=["yen"],
        timeout=5,
        max_pages=5,
        page_limit=100,
    )
    assert [event["event_ticker"] for event in events] == ["KXJPY-26AUG"]
    assert [market["ticker"] for market in events[0]["markets"]] == ["KXJPY-26AUG-HOLD"]


def test_has_market_activity_uses_volume_or_quote_sizes():
    assert has_market_activity({"volume_24h_fp": "12.50"})
    assert has_market_activity({"yes_bid_size_fp": "5.00", "volume_24h_fp": "0"})
    assert has_market_activity({"yes_ask_size_fp": "3.00", "volume_24h_fp": "0"})
    # 99% ask with size is still real liquidity
    assert has_market_activity(
        {
            "yes_ask_dollars": "0.99",
            "yes_ask_size_fp": "26.00",
            "volume_24h_fp": "0.00",
        }
    )
    assert not has_market_activity(
        {
            "yes_bid_dollars": "0.00",
            "yes_ask_dollars": "0.99",
            "yes_bid_size_fp": "0.00",
            "yes_ask_size_fp": "0.00",
            "volume_24h_fp": "0.00",
            "last_price_dollars": "0.68",
        }
    )
    assert not has_market_activity({"ticker": "KXJPY-1"})


def test_format_price_converts_dollars_to_percentage():
    assert format_price("0.5600") == "56.0%"
    assert format_price(0.5) == "50.0%"
    assert format_price(None) is None
    assert format_price("") is None


def test_market_description_omits_missing_values():
    market = {
        "ticker": "KXJPY-1",
        "event_ticker": "KXJPY",
        "yes_bid_dollars": "0.48",
        "yes_ask_dollars": "0.52",
        "last_price_dollars": "0.50",
        "volume_24h_fp": "123.00",
        "close_time": "2026-09-01T00:00:00Z",
    }

    description = market_description(market)

    assert "YES bid: 48.0%" in description
    assert "YES ask: 52.0%" in description
    assert "Last: 50.0%" in description
    assert "24h volume: 123.00" in description
    assert "Close: 2026-09-01T00:00:00Z" in description
    assert "Ticker: KXJPY-1" in description
    assert "Event: KXJPY" in description

    sparse = market_description({"ticker": "ONLY-TICKER"})
    assert "Ticker: ONLY-TICKER" in sparse
    assert "YES bid" not in sparse
    assert "24h volume" not in sparse


def test_event_description_lists_active_market_outcomes():
    description = event_description(
        {
            "title": "Bank of Japan rate decision in September",
            "sub_title": "Sep 17, 2026 meeting",
            "series_ticker": "KXCBDECISIONJAPAN",
            "event_ticker": "KXCBDECISIONJAPAN-26SEP17",
            "markets": [
                {
                    "yes_sub_title": "Hold",
                    "ticker": "HOLD",
                    "yes_bid_dollars": "0.26",
                    "yes_ask_dollars": "0.38",
                    "volume_24h_fp": "101.12",
                    "yes_bid_size_fp": "6.49",
                    "yes_ask_size_fp": "75.00",
                },
                {
                    "yes_sub_title": "Empty",
                    "ticker": "EMPTY",
                    "volume_24h_fp": "0",
                    "yes_bid_size_fp": "0",
                    "yes_ask_size_fp": "0",
                },
            ],
        }
    )

    assert "Sub: Sep 17, 2026 meeting" in description
    assert "Series: KXCBDECISIONJAPAN" in description
    assert "Event: KXCBDECISIONJAPAN-26SEP17" in description
    assert "Hold — YES bid: 26.0%; YES ask: 38.0%; 24h volume: 101.12" in description
    assert "Empty" not in description


def test_build_rss_emits_one_item_per_event_with_stable_guid():
    from kalshi_rss import build_rss

    xml_bytes = build_rss(
        [
            {
                "event_ticker": "KXCBDECISIONJAPAN-26SEP17",
                "title": "Bank of Japan rate decision in September",
                "sub_title": "Sep 17, 2026 meeting",
                "series_ticker": "KXCBDECISIONJAPAN",
                "last_updated_ts": "2026-08-13T01:02:03Z",
                "markets": [
                    {
                        "yes_sub_title": "Hold",
                        "yes_bid_dollars": "0.40",
                        "yes_ask_dollars": "0.45",
                        "volume_24h_fp": "10",
                        "yes_bid_size_fp": "1",
                        "yes_ask_size_fp": "1",
                    }
                ],
            }
        ]
    )

    root = ET.fromstring(xml_bytes)
    assert root.tag == "rss"
    channel = root.find("channel")
    assert channel is not None
    assert channel.findtext("title") == "Kalshi Watch"
    item = channel.find("item")
    assert item is not None
    assert item.findtext("title") == "Bank of Japan rate decision in September"
    assert item.findtext("guid") == "KXCBDECISIONJAPAN-26SEP17"
    assert item.find("guid").attrib["isPermaLink"] == "false"
    assert item.findtext("link") == (
        "https://kalshi.com/markets/kxcbdecisionjapan/kxcbdecisionjapan-26sep17"
    )
    assert item.findtext("pubDate") == "Thu, 13 Aug 2026 01:02:03 +0000"
    assert "Hold — YES bid: 40.0%" in (item.findtext("description") or "")


def test_event_page_url_uses_series_and_event_tickers():
    from kalshi_rss import event_page_url

    assert event_page_url(
        {
            "series_ticker": "KXUSDJPY",
            "event_ticker": "KXUSDJPY-26AUG1310",
        }
    ) == "https://kalshi.com/markets/kxusdjpy/kxusdjpy-26aug1310"
    assert event_page_url({"event_ticker": "KXBOJ-CREATED"}) == (
        "https://kalshi.com/markets"
    )
    assert event_page_url({}) == "https://kalshi.com/markets"


def test_build_rss_uses_market_updated_time_when_event_timestamp_missing():
    from kalshi_rss import build_rss

    root = ET.fromstring(
        build_rss(
            [
                {
                    "event_ticker": "KXBOJ-CREATED",
                    "title": "BOJ event",
                    "markets": [
                        {
                            "yes_sub_title": "Hold",
                            "updated_time": "2026-08-12T12:00:00Z",
                            "volume_24h_fp": "1",
                            "yes_bid_size_fp": "1",
                            "yes_ask_size_fp": "0",
                        }
                    ],
                }
            ]
        )
    )
    assert root.findtext("./channel/item/pubDate") == "Wed, 12 Aug 2026 12:00:00 +0000"


def test_build_rss_pubdate_uses_latest_nested_market_time():
    from kalshi_rss import build_rss

    root = ET.fromstring(
        build_rss(
            [
                {
                    "event_ticker": "KXCBDECISIONJAPAN-26SEP17",
                    "title": "Bank of Japan rate decision in September",
                    "last_updated_ts": "2026-07-28T19:58:00Z",
                    "markets": [
                        {
                            "yes_sub_title": "Hold",
                            "updated_time": "2026-08-13T03:32:25Z",
                            "volume_24h_fp": "1",
                            "yes_bid_size_fp": "1",
                            "yes_ask_size_fp": "1",
                        },
                        {
                            "yes_sub_title": "Hike",
                            "updated_time": "2026-08-12T01:00:00Z",
                            "volume_24h_fp": "1",
                            "yes_bid_size_fp": "1",
                            "yes_ask_size_fp": "1",
                        },
                    ],
                }
            ]
        )
    )
    assert root.findtext("./channel/item/pubDate") == "Thu, 13 Aug 2026 03:32:25 +0000"


def test_event_latest_timestamp_is_shared_by_sort_and_pubdate():
    from kalshi_rss import _event_latest_timestamp, _sort_key

    event = {
        "last_updated_ts": "2026-07-28T19:58:00Z",
        "markets": [
            {"updated_time": "2026-08-13T03:32:25Z"},
            {"created_time": "2026-08-01T00:00:00Z"},
        ],
    }
    assert _event_latest_timestamp(event) == "2026-08-13T03:32:25Z"
    assert _sort_key(event) == "2026-08-13T03:32:25Z"


def test_write_atomic_replaces_file_with_valid_xml(tmp_path: Path):
    from kalshi_rss import build_rss, write_atomic

    output = tmp_path / "feed.xml"
    output.write_text("old", encoding="utf-8")
    data = build_rss(
        [
            {
                "event_ticker": "KXJPY-1",
                "title": "Yen event",
                "markets": [{"yes_sub_title": "Up", "volume_24h_fp": "1", "yes_bid_size_fp": "1"}],
            }
        ]
    )

    write_atomic(output, data)

    root = ET.parse(output).getroot()
    assert root.findtext("./channel/item/guid") == "KXJPY-1"
    assert not list(tmp_path.glob("*.tmp"))


class FakeResponse:
    def __init__(self, payload, error=None):
        self._payload = payload
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        return self.responses.pop(0)


def test_fetch_open_markets_follows_cursor_pagination():
    from kalshi_rss import fetch_open_markets

    session = FakeSession(
        [
            FakeResponse({"markets": [{"ticker": "A"}], "cursor": "next-1"}),
            FakeResponse({"markets": [{"ticker": "B"}], "cursor": ""}),
        ]
    )

    markets = fetch_open_markets(
        session,
        "https://example.test/markets",
        timeout=7.5,
        max_pages=10,
        page_limit=1000,
    )

    assert [market["ticker"] for market in markets] == ["A", "B"]
    assert session.calls[0]["params"] == {"status": "open", "limit": 1000}
    assert session.calls[1]["params"] == {
        "status": "open",
        "limit": 1000,
        "cursor": "next-1",
    }
    assert session.calls[0]["timeout"] == 7.5


def test_fetch_open_markets_stops_on_repeated_cursor():
    from kalshi_rss import fetch_open_markets

    session = FakeSession(
        [
            FakeResponse({"markets": [{"ticker": "A"}], "cursor": "same"}),
            FakeResponse({"markets": [{"ticker": "B"}], "cursor": "same"}),
        ]
    )

    markets = fetch_open_markets(
        session,
        "https://example.test/markets",
        timeout=5,
        max_pages=10,
        page_limit=100,
    )

    assert [market["ticker"] for market in markets] == ["A", "B"]
    assert len(session.calls) == 2


def test_fetch_open_markets_propagates_http_error():
    import requests
    from kalshi_rss import fetch_open_markets

    error = requests.HTTPError("503 Server Error")
    session = FakeSession([FakeResponse({}, error=error)])

    with pytest.raises(requests.HTTPError, match="503"):
        fetch_open_markets(
            session,
            "https://example.test/markets",
            timeout=5,
            max_pages=3,
            page_limit=100,
        )


def test_load_config_reads_json_file(tmp_path: Path):
    from kalshi_rss import load_config

    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"keywords":["BOJ","JPY"],"output":"custom.xml","page_limit":250}',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["keywords"] == ["BOJ", "JPY"]
    assert config["output"] == "custom.xml"
    assert config["page_limit"] == 250
