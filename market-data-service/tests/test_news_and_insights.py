from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.ai import narrator
from app.config import Settings
from app.models import AiInsight, Fundamentals, NewsArticle, Symbol
from app.services.news_service import _normalize, latest_news


# ---------- yfinance item normalization ----------

def test_normalize_old_flat_schema():
    item = {"uuid": "abc-123", "title": "RIL posts record profit",
            "publisher": "Reuters", "link": "https://example.com/a",
            "providerPublishTime": 1_752_300_000}
    norm = _normalize(item)
    assert norm["external_id"] == "abc-123"
    assert norm["title"] == "RIL posts record profit"
    assert norm["publisher"] == "Reuters"
    assert norm["published_at"].tzinfo is not None


def test_normalize_new_nested_schema():
    item = {"id": "xyz-9", "content": {
        "title": "Reliance expands retail arm",
        "pubDate": "2026-07-10T09:30:00Z",
        "provider": {"displayName": "Moneycontrol"},
        "canonicalUrl": {"url": "https://example.com/b"},
    }}
    norm = _normalize(item)
    assert norm["external_id"] == "xyz-9"
    assert norm["publisher"] == "Moneycontrol"
    assert norm["link"] == "https://example.com/b"
    assert norm["published_at"].year == 2026


def test_normalize_rejects_items_without_title_or_id():
    assert _normalize({}) is None
    assert _normalize({"uuid": "u1"}) is None
    assert _normalize({"title": "no id"}) is None


def test_latest_news_orders_newest_first(session: Session, reliance: Symbol):
    older = NewsArticle(symbol_id=reliance.id, external_id="e1", title="old",
                        published_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
    newer = NewsArticle(symbol_id=reliance.id, external_id="e2", title="new",
                        published_at=datetime(2026, 7, 10, tzinfo=timezone.utc))
    session.add_all([older, newer])
    session.commit()
    rows = latest_news(session, reliance.id)
    assert [r.title for r in rows] == ["new", "old"]


# ---------- narrator: JSON parsing + caching ----------

def test_parse_json_plain_and_fenced():
    assert narrator._parse_json('{"a": 1}') == {"a": 1}
    assert narrator._parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert narrator._parse_json('noise before {"a": 1} noise after') == {"a": 1}
    with pytest.raises(narrator.LlmError):
        narrator._parse_json("no json here")


def test_llm_disabled_without_key(session: Session, reliance: Symbol):
    settings = Settings(anthropic_api_key="")
    assert narrator.llm_enabled(settings) is False
    assert narrator.news_insight(session, settings, reliance, []) is None


def test_insight_cache_hit_and_invalidation(session: Session, reliance: Symbol,
                                            monkeypatch):
    settings = Settings(anthropic_api_key="test-key")
    calls = {"n": 0}

    def fake_call(*_args, **_kwargs):
        calls["n"] += 1
        return '{"summary": "fine", "sentiment": "neutral"}'

    monkeypatch.setattr(narrator, "_call_claude", fake_call)
    articles = [NewsArticle(symbol_id=reliance.id, external_id="e1", title="t1")]
    session.add_all(articles)
    session.commit()

    first = narrator.news_insight(session, settings, reliance, articles)
    assert first["cached"] is False and calls["n"] == 1
    second = narrator.news_insight(session, settings, reliance, articles)
    assert second["cached"] is True and calls["n"] == 1   # served from cache

    # a new article changes the fingerprint -> regenerates
    extra = NewsArticle(symbol_id=reliance.id, external_id="e2", title="t2")
    session.add(extra)
    session.commit()
    third = narrator.news_insight(session, settings, reliance, articles + [extra])
    assert third["cached"] is False and calls["n"] == 2


def test_fundamentals_insight_caches_by_computed_at(session: Session, reliance: Symbol,
                                                    monkeypatch):
    settings = Settings(anthropic_api_key="test-key")
    calls = {"n": 0}

    def fake_call(*_args, **_kwargs):
        calls["n"] += 1
        return '{"headline": "solid", "verdict": "good"}'

    monkeypatch.setattr(narrator, "_call_claude", fake_call)
    f = Fundamentals(symbol_id=reliance.id, pe_trailing=24.5, roe_pct=18.0,
                     computed_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
    session.add(f)
    session.commit()

    first = narrator.fundamentals_insight(session, settings, reliance, f)
    assert first["insight"]["verdict"] == "good" and calls["n"] == 1
    second = narrator.fundamentals_insight(session, settings, reliance, f)
    assert second["cached"] is True and calls["n"] == 1

    f.computed_at = datetime(2026, 7, 11, tzinfo=timezone.utc)   # refreshed ratios
    session.commit()
    third = narrator.fundamentals_insight(session, settings, reliance, f)
    assert third["cached"] is False and calls["n"] == 2


def test_record_usage_computes_cost(session: Session):
    from app.models import AiUsage

    settings = Settings(anthropic_api_key="k", anthropic_price_input_per_mtok=1.0,
                        anthropic_price_output_per_mtok=5.0)
    narrator._record_usage(session, settings, "NEWS",
                           {"input_tokens": 1_000_000, "output_tokens": 200_000})
    row = session.query(AiUsage).one()
    assert row.kind == "NEWS"
    assert float(row.cost_usd) == 2.0        # 1.0 + 0.2M * 5
    assert row.input_tokens == 1_000_000


def test_record_usage_never_raises(session: Session):
    settings = Settings(anthropic_api_key="k")
    narrator._record_usage(session, settings, "NEWS", {"input_tokens": "garbage"})
    # bad data logged and swallowed — insights must not break on tracking


def test_llm_error_is_reported_not_raised(session: Session, reliance: Symbol,
                                          monkeypatch):
    settings = Settings(anthropic_api_key="test-key")

    def boom(*_args, **_kwargs):
        raise narrator.LlmError("API down")

    monkeypatch.setattr(narrator, "_call_claude", boom)
    articles = [NewsArticle(symbol_id=reliance.id, external_id="e9", title="t")]
    session.add_all(articles)
    session.commit()
    result = narrator.news_insight(session, settings, reliance, articles)
    assert "error" in result
