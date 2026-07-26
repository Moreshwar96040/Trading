"""Offline tests for the multi-source per-stock news layer.

Precision is the thing worth testing hard: a keyword feed searching "Bajaj
Finance" will return Bajaj Auto stories, and mislabelled headlines produce
confidently wrong sentiment scores. No network is touched here.
"""
from datetime import datetime, timedelta, timezone

from app.services.stock_news_sources import (build_feed_urls, company_tokens,
                                             is_relevant, normalize_items,
                                             search_query, title_key)

FEEDS = ("GoogleNews|https://news.google.com/rss/search?q={query}+when:21d&hl=en-IN,"
         "YahooRSS|https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}")


# ---------- name tokenisation ----------

def test_company_tokens_strips_corporate_noise():
    assert company_tokens("Bajaj Finance Ltd") == ["bajaj", "finance"]
    assert company_tokens("Infosys Limited") == ["infosys"]
    # "India"/"Group" carry no identifying signal and would over-match
    assert "india" not in company_tokens("Hindustan Unilever India Ltd")


# ---------- relevance gate ----------

def test_accepts_headline_naming_the_company():
    assert is_relevant("Bajaj Finance Q1 net profit jumps 18%",
                       "BAJFINANCE", "Bajaj Finance Ltd")


def test_accepts_ticker_mention():
    assert is_relevant("BAJFINANCE hits fresh 52-week high",
                       "BAJFINANCE", "Bajaj Finance Ltd")


def test_rejects_same_family_different_company():
    """The failure that would poison sentiment: sibling Bajaj listings."""
    for other in ("Bajaj Auto Q1 profit rises 12%",
                  "Bajaj Housing Finance IPO opens",   # 'housing' breaks the pair
                  "Bajaj Holdings announces dividend"):
        assert is_relevant(other, "BAJFINANCE", "Bajaj Finance Ltd") is False, other


def test_accepts_common_abbreviation_via_prefix_match():
    """Headlines shorten the legal name; prefix matching keeps those."""
    assert is_relevant("Sun Pharma gets USFDA nod for plant",
                       "SUNPHARMA", "Sun Pharmaceutical Industries Limited")
    assert is_relevant("Reliance Industries to invest in retail arm",
                       "RELIANCE", "Reliance Industries Ltd")


def test_rejects_unrelated_and_empty():
    assert is_relevant("Nifty ends flat ahead of Fed meeting",
                       "BAJFINANCE", "Bajaj Finance Ltd") is False
    assert is_relevant("", "BAJFINANCE", "Bajaj Finance Ltd") is False


def test_single_token_name_matches_on_that_token():
    assert is_relevant("Infosys wins $1.5 bn deal", "INFY", "Infosys Limited")
    assert is_relevant("TCS bags order", "INFY", "Infosys Limited") is False


# ---------- query + url building ----------

def test_search_query_quotes_phrase_and_includes_ticker():
    q = search_query("BAJFINANCE", "Bajaj Finance Ltd")
    assert '"bajaj finance"' in q.lower()
    assert "BAJFINANCE" in q


def test_build_feed_urls_substitutes_placeholders_and_encodes():
    urls = dict(build_feed_urls(FEEDS, "BAJFINANCE", "Bajaj Finance Ltd",
                                "BAJFINANCE.NS"))
    assert "{query}" not in urls["GoogleNews"] and " " not in urls["GoogleNews"]
    assert "bajaj" in urls["GoogleNews"].lower()
    assert urls["YahooRSS"].endswith("BAJFINANCE.NS")


def test_build_feed_urls_ignores_malformed_entries():
    assert build_feed_urls("no-pipe-here", "X", "X Ltd", "X.NS") == []
    assert build_feed_urls("", "X", "X Ltd", "X.NS") == []


# ---------- normalisation, dedup, recency ----------

def _item(title: str, when=None, link="http://e.com/1"):
    return {"title": title, "link": link, "published_at": when, "source": "GoogleNews"}


def test_same_story_across_sources_shares_one_key():
    """Punctuation/spacing differences must not create duplicate rows."""
    assert title_key("Bajaj Finance Q1 profit up 18%") == \
           title_key("bajaj  finance q1 profit up 18")


def test_normalize_filters_irrelevant_and_old():
    now = datetime.now(timezone.utc)
    items = [_item("Bajaj Finance Q1 profit up 18%", now),
             _item("Bajaj Auto launches new bike", now),          # irrelevant
             _item("Bajaj Finance board meet", now - timedelta(days=90))]  # stale
    rows = normalize_items(items, "GoogleNews", "BAJFINANCE", "Bajaj Finance Ltd", 21)
    assert len(rows) == 1
    assert rows[0]["title"].startswith("Bajaj Finance Q1")


def test_normalize_keeps_undated_items():
    """Undated feed entries are recent by construction — don't discard them."""
    rows = normalize_items([_item("Bajaj Finance raises funds", None)],
                          "BingNews", "BAJFINANCE", "Bajaj Finance Ltd", 21)
    assert len(rows) == 1
    assert rows[0]["published_at"] is None


def test_publisher_recovered_from_google_style_title():
    rows = normalize_items([_item("Bajaj Finance Q1 profit up - Mint", None)],
                          "GoogleNews", "BAJFINANCE", "Bajaj Finance Ltd", 21)
    assert rows[0]["publisher"] == "Mint"


def test_publisher_falls_back_to_source_name():
    rows = normalize_items([_item("Bajaj Finance Q1 profit up", None)],
                          "GoogleNews", "BAJFINANCE", "Bajaj Finance Ltd", 21)
    assert rows[0]["publisher"] == "GoogleNews"


def test_store_merges_sources_and_dedups_same_story(session, monkeypatch):
    """yfinance and the RSS tier reporting the same story = one stored row."""
    from app.models import Symbol
    from app.services import news_service

    sym = Symbol(ticker="BAJFINANCE", yahoo_symbol="BAJFINANCE.NS",
                 name="Bajaj Finance Ltd", sector="NBFC")
    session.add(sym)
    session.commit()

    monkeypatch.setattr(news_service, "_yfinance_items", lambda *a, **k: [
        {"external_id": "yf-1", "title": "Bajaj Finance Q1 profit up 18%",
         "publisher": "Reuters", "link": "http://a", "published_at": None},
    ])
    monkeypatch.setattr("app.services.stock_news_sources.fetch_stock_feeds",
                        lambda *a, **k: [
                            # same story, different punctuation + outlet
                            {"external_id": title_key("Bajaj Finance Q1 profit up 18"),
                             "title": "Bajaj Finance Q1 profit up 18",
                             "publisher": "Mint", "link": "http://b",
                             "published_at": None},
                            {"external_id": title_key("Bajaj Finance board approves buyback"),
                             "title": "Bajaj Finance board approves buyback",
                             "publisher": "ET", "link": "http://c",
                             "published_at": None},
                        ])

    inserted = news_service.fetch_and_store_news(session, sym)
    assert inserted == 2                      # 3 candidates, 1 duplicate collapsed

    # re-running stores nothing new (idempotent)
    assert news_service.fetch_and_store_news(session, sym) == 0
    titles = {a.title for a in news_service.latest_news(session, sym.id)}
    assert len(titles) == 2


def test_store_survives_total_source_failure(session, monkeypatch):
    """Every source down = 0 rows, reasons collected, no exception."""
    from app.models import Symbol
    from app.services import news_service

    sym = Symbol(ticker="INFY", yahoo_symbol="INFY.NS", name="Infosys Limited")
    session.add(sym)
    session.commit()

    monkeypatch.setattr(news_service, "_yfinance_items", lambda *a, **k: [])
    monkeypatch.setattr("app.services.stock_news_sources.fetch_stock_feeds",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network down")))

    errors: list = []
    assert news_service.fetch_and_store_news(session, sym, errors=errors) == 0
    assert any("network down" in e for e in errors)


def test_external_id_fits_column_width():
    """news_articles.external_id is VARCHAR(80)."""
    rows = normalize_items([_item("A" * 400, None)], "GoogleNews", "AAA", "AAA Ltd", 21)
    if rows:                                   # 'AAAA…' matches the AAA prefix
        assert len(rows[0]["external_id"]) <= 80
        assert len(rows[0]["title"]) <= 500
