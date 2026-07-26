from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AiInsight, MarketNews
from app.services.market_news_service import (cached_macro_sentiment,
                                              latest_market_news, parse_feed)

RSS_SAMPLE = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Feed</title>
<item><title>Sensex rallies 800 points on rate-cut hopes</title>
<link>https://example.com/a</link>
<pubDate>Tue, 14 Jul 2026 09:30:00 +0530</pubDate></item>
<item><title>Rupee slips past 85 as crude spikes</title>
<link>https://example.com/b</link>
<pubDate>Tue, 14 Jul 2026 08:00:00 +0530</pubDate></item>
<item><title></title><link>https://example.com/skip</link></item>
</channel></rss>"""

ATOM_SAMPLE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>FT</title>
<entry><title>Global stocks steady before Fed minutes</title>
<link href="https://ft.example/x"/>
<updated>2026-07-14T05:00:00Z</updated></entry>
</feed>"""


def test_parse_rss():
    items = parse_feed(RSS_SAMPLE, "TestFeed")
    assert len(items) == 2                       # empty title skipped
    assert items[0]["source"] == "TestFeed"
    assert items[0]["title"].startswith("Sensex rallies")
    assert items[0]["link"] == "https://example.com/a"
    assert items[0]["published_at"].year == 2026


def test_parse_atom():
    items = parse_feed(ATOM_SAMPLE, "FT")
    assert len(items) == 1
    assert items[0]["link"] == "https://ft.example/x"
    assert items[0]["published_at"].year == 2026


def test_parse_garbage_never_raises():
    assert parse_feed("not xml at all", "X") == []
    assert parse_feed("<rss><channel></channel></rss>", "X") == []


def test_latest_market_news_orders_newest_and_drops_stale(session: Session):
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    session.add(MarketNews(source="A", title="old", dedup_key="k1",
                           published_at=now - timedelta(hours=6)))
    session.add(MarketNews(source="B", title="new", dedup_key="k2",
                           published_at=now - timedelta(hours=1)))
    session.add(MarketNews(source="C", title="stale", dedup_key="k3",
                           published_at=now - timedelta(days=5)))   # beyond 2-day window
    session.commit()
    rows = latest_market_news(session)
    assert [r.title for r in rows] == ["new", "old"]


def test_cached_macro_sentiment_reads_digest(session: Session):
    assert cached_macro_sentiment(session) is None
    session.add(AiInsight(symbol_id=0, kind="MACRO",
                          content={"sentiment": "negative"}, fingerprint="f"))
    session.commit()
    assert cached_macro_sentiment(session) == "negative"


def test_macro_layer_moves_conviction(session: Session):
    """Negative market-wide tone must lower every setup's conviction."""
    from datetime import date

    from app.models import ScreenerSnapshot, Strategy, StrategySignal, Symbol
    from app.services.conviction_service import alpha_stack

    sym = Symbol(ticker="TCS", yahoo_symbol="TCS.NS", name="TCS", sector="IT")
    strat = Strategy(name="S", definition={"entry": []})
    session.add_all([sym, strat])
    session.flush()
    session.add(StrategySignal(strategy_id=strat.id, symbol_id=sym.id, signal="ENTRY",
                               as_of_date=date(2026, 7, 14), close=3000))
    session.add(ScreenerSnapshot(symbol_id=sym.id, as_of_date=date(2026, 7, 14),
                                 close=3000, sma_50=2800, sma_200=2600, rsi_14=60,
                                 atr_14=50, return_1m_pct=4.0))
    session.commit()

    baseline = alpha_stack(session)["setups"][0]
    session.add(AiInsight(symbol_id=0, kind="MACRO",
                          content={"sentiment": "negative"}, fingerprint="f"))
    session.commit()
    with_macro = alpha_stack(session)["setups"][0]

    assert with_macro["conviction"] < baseline["conviction"]
    macro = next(b for b in with_macro["breakdown"] if b["layer"] == "macro")
    # Layers contribute weight x strength (0..1); a negative tape scores 0 of 6.
    assert macro["points"] == 0.0
    assert macro["max"] == 6.0
    base_macro = next(b for b in baseline["breakdown"] if b["layer"] == "macro")
    assert base_macro["points"] == 3.0        # no digest = neutral half-credit
