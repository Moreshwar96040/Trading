"""Morning AI briefing: a pre-market plan for THIS trader's book.

Assembles what actually matters before the open — Guardian action queue, market
regime, freshly fired signals, overnight headlines for held tickers — and has
Claude write the day's plan. Generated once per day (cached in ai_insights,
kind=BRIEFING, symbol_id 0) and warmed by the scheduler before market open so
it's already waiting when the app is opened.
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.config import Settings

log = logging.getLogger(__name__)

BRIEFING_SYSTEM = (
    "You are the pre-market briefing writer for one retail swing trader on the NSE. "
    "You get their open positions with health checks, the market regime, strategy "
    "signals that fired on the latest bar, and recent headlines for stocks they hold. "
    "Respond with ONLY a JSON object, no markdown fences, keys: headline (one sentence "
    "setting today's tone for THEIR book, not the world), market_read (2 sentences on "
    "the regime and what it means for their style), position_plans (array of "
    "{ticker, plan} — one imperative sentence per open position, referencing its checks "
    "and news where relevant), opportunities (array of max 3 short strings drawn from "
    "the fired signals, or [] if none deserve attention), discipline_note (one sentence, "
    "specific to the data — e.g. reference their missing stops or concentration). "
    "Be concrete and calm; numbers over adjectives; never predict prices; never say "
    "buy/sell as advice — frame as their own plan's logic.")


def _gather_inputs(session: Session) -> dict:
    from app.services.guardian_service import position_health
    from app.services.regime_service import compute_regime

    guardian = position_health(session)
    regime = compute_regime(session)

    signals = [dict(r) for r in session.execute(text("""
        SELECT st.name AS strategy, s.ticker, sig.signal, sig.close
        FROM strategy_signals sig
        JOIN symbols s ON s.id = sig.symbol_id
        JOIN strategies st ON st.id = sig.strategy_id
        WHERE sig.as_of_date = (SELECT MAX(as_of_date) FROM strategy_signals)
        ORDER BY sig.signal, s.ticker LIMIT 20
    """)).mappings().all()]

    held = [p["ticker"] for p in guardian.get("positions", [])]
    news = []
    if held:
        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        stmt = text("""
            SELECT s.ticker, n.title, n.publisher
            FROM news_articles n JOIN symbols s ON s.id = n.symbol_id
            WHERE s.ticker IN :held AND n.published_at >= :cutoff
            ORDER BY n.published_at DESC LIMIT 12
        """).bindparams(bindparam("held", expanding=True))
        news = [dict(r) for r in session.execute(
            stmt, {"held": held, "cutoff": cutoff}).mappings().all()]

    return {"guardian": guardian, "regime": regime, "signals": signals,
            "held_news": news}


def build_briefing(session: Session, settings: Settings, force: bool = False) -> dict:
    """Today's briefing: deterministic inputs always; Claude narrative when enabled."""
    from app.ai import narrator
    from app.models import AiInsight

    inputs = _gather_inputs(session)
    today = date.today().isoformat()
    result = {"date": today,
              "actions": inputs["guardian"].get("actions", []),
              "summary": inputs["guardian"].get("summary"),
              "regime": inputs["regime"],
              "signals": inputs["signals"],
              "llm_enabled": narrator.llm_enabled(settings),
              "narrative": None}

    if not narrator.llm_enabled(settings):
        return result

    fingerprint = f"{today}-a{len(result['actions'])}-s{len(inputs['signals'])}"
    row = session.get(AiInsight, (0, "BRIEFING"))
    if not force and row is not None and row.fingerprint == fingerprint:
        result["narrative"] = {"insight": row.content, "cached": True}
        return result

    try:
        raw = narrator._call_claude(
            settings, BRIEFING_SYSTEM,
            json.dumps(inputs, default=str), session=session, kind="BRIEFING")
        content = narrator._parse_json(raw)
    except Exception as exc:                        # noqa: BLE001 — brief is optional
        log.error("Briefing generation failed: %s", exc)
        result["narrative"] = {"error": str(exc)}
        return result

    if row is None:
        row = AiInsight(symbol_id=0, kind="BRIEFING")
    row.content = content
    row.fingerprint = fingerprint
    row.model_name = settings.anthropic_model
    row.generated_at = datetime.now(timezone.utc)
    session.merge(row)
    session.commit()
    result["narrative"] = {"insight": content, "cached": False}
    return result
