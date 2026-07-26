"""LLM-generated plain-language insights (news digests, fundamentals explanations).

Calls the Anthropic Messages API directly over HTTP (no SDK dependency) and caches
results in `ai_insights` keyed by a fingerprint of the inputs, so each insight is
paid for once and regenerated only when its underlying data changes.

If no API key is configured every public function degrades gracefully: callers
get `None` and the UI simply shows the raw data without narrative.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone

import httpx

from app.config import Settings
from app.models import AiInsight, Fundamentals, NewsArticle, Symbol
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

NEWS_SYSTEM = (
    "You are a financial news analyst for Indian (NSE) equities. You are given recent "
    "headlines for one stock. Respond with ONLY a JSON object, no markdown fences, with "
    "keys: summary (2-3 plain sentences a retail investor understands), sentiment (one of "
    "positive/negative/neutral/mixed), key_points (array of max 4 short strings), "
    "watch_for (array of max 2 short strings: upcoming catalysts or risks implied by the "
    "news), catalysts (array of max 4 objects {type, direction} where type is one of "
    "earnings_beat/earnings_miss/guidance_raise/guidance_cut/upgrade/downgrade/order_win/"
    "expansion/buyback/regulatory_action/legal/fraud/management_change and direction is one "
    "of positive/negative/neutral — only include catalysts actually implied by the "
    "headlines, else []). Base everything strictly on the headlines given; do not invent facts.")

FUNDAMENTALS_SYSTEM = (
    "You are a financial educator explaining company fundamentals to a retail investor "
    "who is not a finance professional. You are given valuation and quality ratios plus "
    "recent financial statement figures for one NSE-listed company. Respond with ONLY a "
    "JSON object, no markdown fences, with keys: headline (one sentence overall read), "
    "verdict (one of strong/good/mixed/weak), summary (3-5 plain sentences covering "
    "valuation, profitability, growth and balance-sheet risk), strengths (array of max 4 "
    "short strings), concerns (array of max 4 short strings), metrics_explained (array of "
    "objects {metric, value, meaning} for the 5-7 most decision-relevant metrics, where "
    "meaning is one sentence in everyday language, e.g. \"For every ₹100 of shareholder "
    "money the company earned ₹18 of profit this year — healthy\"). Judge numbers in the "
    "context of Indian equities. Never give buy/sell advice; describe, don't recommend. "
    "If a metric is missing, skip it silently.")


class LlmError(RuntimeError):
    pass


def llm_enabled(settings: Settings) -> bool:
    return bool(settings.anthropic_api_key)


def _call_claude(settings: Settings, system: str, user: str,
                 session: Session | None = None, kind: str = "GENERIC") -> str:
    resp = httpx.post(
        API_URL,
        headers={"x-api-key": settings.anthropic_api_key,
                 "anthropic-version": API_VERSION,
                 "content-type": "application/json"},
        json={"model": settings.anthropic_model,
              "max_tokens": settings.anthropic_max_tokens,
              "system": system,
              "messages": [{"role": "user", "content": user}]},
        timeout=45.0)
    if resp.status_code == 401:
        raise LlmError(
            "Anthropic rejected the API key (401). The key in .env is revoked or "
            "invalid — create a new one at console.anthropic.com → API keys, put it "
            "in ANTHROPIC_API_KEY, and restart the market-data-service.")
    if resp.status_code == 429:
        raise LlmError("Anthropic rate limit hit (429) — wait a minute and retry.")
    if resp.status_code != 200:
        raise LlmError(f"Anthropic API {resp.status_code}: {resp.text[:300]}")
    body = resp.json()
    if session is not None:
        _record_usage(session, settings, kind, body.get("usage") or {})
    parts = body.get("content", [])
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def _record_usage(session: Session, settings: Settings, kind: str, usage: dict) -> None:
    """Best-effort usage log — a tracking failure must never break an insight."""
    from app.models import AiUsage
    try:
        inp = int(usage.get("input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
        cost = (inp * settings.anthropic_price_input_per_mtok
                + out * settings.anthropic_price_output_per_mtok) / 1_000_000
        session.add(AiUsage(kind=kind, model=settings.anthropic_model,
                            input_tokens=inp, output_tokens=out,
                            cost_usd=round(cost, 6)))
        session.commit()
    except Exception:                               # noqa: BLE001
        log.warning("Could not record AI usage", exc_info=True)
        session.rollback()


def _parse_json(text: str) -> dict:
    """Tolerant JSON extraction (models occasionally wrap output in fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LlmError(f"No JSON object in LLM response: {text[:200]}")
    return json.loads(text[start:end + 1])


def _cached(session: Session, symbol_id: int, kind: str, fingerprint: str) -> dict | None:
    row = session.get(AiInsight, (symbol_id, kind))
    if row is not None and row.fingerprint == fingerprint:
        return {"insight": row.content, "generated_at": row.generated_at.isoformat()
                if row.generated_at else None, "cached": True}
    return None


def _store(session: Session, symbol_id: int, kind: str, fingerprint: str,
           content: dict, model: str) -> dict:
    row = session.get(AiInsight, (symbol_id, kind)) or AiInsight(symbol_id=symbol_id, kind=kind)
    row.content = content
    row.fingerprint = fingerprint
    row.model_name = model
    row.generated_at = datetime.now(timezone.utc)
    session.merge(row)
    session.commit()
    return {"insight": content, "generated_at": row.generated_at.isoformat(), "cached": False}


def news_insight(session: Session, settings: Settings, symbol: Symbol,
                 articles: list[NewsArticle]) -> dict | None:
    """Digest of the given articles. Cached until the article set changes."""
    if not llm_enabled(settings) or not articles:
        return None
    fingerprint = hashlib.sha1(
        "|".join(a.external_id for a in articles).encode()).hexdigest()[:40]
    hit = _cached(session, symbol.id, "NEWS", fingerprint)
    if hit:
        return hit

    lines = [f"- [{a.published_at:%Y-%m-%d}] {a.title} ({a.publisher or 'unknown'})"
             if a.published_at else f"- {a.title} ({a.publisher or 'unknown'})"
             for a in articles]
    user = (f"Stock: {symbol.name} ({symbol.ticker}, NSE)\n"
            f"Recent headlines, newest first:\n" + "\n".join(lines))
    try:
        content = _parse_json(_call_claude(settings, NEWS_SYSTEM, user,
                                           session=session, kind="NEWS"))
    except (LlmError, json.JSONDecodeError, httpx.HTTPError) as exc:
        log.error("News insight failed for %s: %s", symbol.ticker, exc)
        return {"error": str(exc)}
    return _store(session, symbol.id, "NEWS", fingerprint, content, settings.anthropic_model)


def fundamentals_insight(session: Session, settings: Settings, symbol: Symbol,
                         fundamentals: Fundamentals,
                         statement_rows: list[dict] | None = None) -> dict | None:
    """Plain-language read of the stored ratios. Cached until fundamentals refresh."""
    if not llm_enabled(settings):
        return None
    fingerprint = (fundamentals.computed_at.isoformat()[:40]
                   if fundamentals.computed_at else "no-timestamp")
    hit = _cached(session, symbol.id, "FUNDAMENTALS", fingerprint)
    if hit:
        return hit

    ratios = {c.name: getattr(fundamentals, c.name)
              for c in Fundamentals.__table__.columns
              if c.name not in ("symbol_id", "computed_at")
              and getattr(fundamentals, c.name) is not None}
    user = (f"Company: {symbol.name} ({symbol.ticker}, NSE), sector: {symbol.sector or 'unknown'}\n"
            f"Ratios: {json.dumps({k: float(v) for k, v in ratios.items()}, default=str)}\n"
            + (f"Recent statements: {json.dumps(statement_rows, default=str)}"
               if statement_rows else ""))
    try:
        content = _parse_json(_call_claude(settings, FUNDAMENTALS_SYSTEM, user,
                                           session=session, kind="FUNDAMENTALS"))
    except (LlmError, json.JSONDecodeError, httpx.HTTPError) as exc:
        log.error("Fundamentals insight failed for %s: %s", symbol.ticker, exc)
        return {"error": str(exc)}
    return _store(session, symbol.id, "FUNDAMENTALS", fingerprint, content,
                  settings.anthropic_model)
