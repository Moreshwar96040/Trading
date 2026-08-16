"""Post-market daily sync scheduler (APScheduler, cron from config)."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.db import session_factory
from app.providers.yahoo import YahooProvider

log = logging.getLogger(__name__)


def _run_sync_job() -> None:
    from app.services.sync_service import sync_daily
    settings = get_settings()
    session = session_factory()()
    try:
        provider = YahooProvider(settings.yahoo_throttle_seconds, settings.yahoo_max_retries,
                                 settings.yahoo_backoff_seconds)
        summary = sync_daily(session, provider,
                             default_lookback_days=settings.sync_default_lookback_days)
        log.info("Scheduled sync finished: %s (+%d rows)", summary["status"],
                 summary["rows_inserted"])
        from app.services.snapshot_service import refresh_snapshots
        snap = refresh_snapshots(session)
        log.info("Snapshot refresh after sync: %d computed", snap["computed"])
        from app.services.alert_service import evaluate_alerts
        alerts = evaluate_alerts(session)
        log.info("Alerts evaluated: %d checked, %d triggered", alerts["checked"],
                 alerts["triggered"])
        from app.services.signal_service import evaluate_signals
        sig = evaluate_signals(session)
        log.info("Strategy signals evaluated: %d fired", sig["signals"])

        # Adaptive conviction: record today's scores, then label whatever has
        # matured. Runs LAST so it scores against a fresh snapshot and signals.
        # This history cannot be backfilled — a missed run is data lost forever,
        # so it is wrapped separately rather than sharing the outer try.
        try:
            from app.services.conviction_recorder import (label_outcomes,
                                                          record_conviction)
            rec = record_conviction(session, settings)
            lab = label_outcomes(session)
            log.info("Conviction: %d recorded, %d skipped, %d newly labelled",
                     rec["recorded"], rec["skipped"], lab["labelled"])
        except Exception:                      # noqa: BLE001 — never fail the sync
            log.exception("Conviction recording failed (sync itself succeeded)")

        # Paper autopilot — no-op unless explicitly enabled. Isolated for the same
        # reason: a rejected order must never take the sync down with it.
        try:
            from app.services.autopilot import reconcile_closed, run_autopilot
            auto = run_autopilot(session, settings)
            if auto.get("status") == "OK":
                closed = reconcile_closed(session)
                log.info("Autopilot: %d opened, %d closed", auto["opened"],
                         closed["closed"])
        except Exception:                      # noqa: BLE001
            log.exception("Autopilot run failed (sync itself succeeded)")

        # Auto-rollback runs DAILY even though adaptation is weekly: an automatic
        # model that has stopped working should not survive until the next
        # adaptation window just because that is when we happened to look.
        try:
            from app.services.circuit_breakers import auto_rollback_if_failing
            out = auto_rollback_if_failing(session)
            if out["reverted"]:
                log.warning("Auto-rollback reverted %d scope(s): %s",
                            len(out["reverted"]), out["reverted"])
        except Exception:                      # noqa: BLE001
            log.exception("Auto-rollback check failed (sync itself succeeded)")
    except Exception:
        log.exception("Scheduled sync crashed")
    finally:
        session.close()


def _run_fundamentals_job() -> None:
    from app.services.fundamentals_service import refresh_fundamentals
    from app.services.snapshot_service import refresh_snapshots
    settings = get_settings()
    session = session_factory()()
    try:
        provider = YahooProvider(settings.yahoo_throttle_seconds, settings.yahoo_max_retries,
                                 settings.yahoo_backoff_seconds)
        summary = refresh_fundamentals(session, provider)
        refresh_snapshots(session)
        log.info("Scheduled fundamentals refresh: %s (%d symbols)", summary["status"],
                 summary["symbols_updated"])
    except Exception:
        log.exception("Scheduled fundamentals refresh crashed")
    finally:
        session.close()


def _run_adaptation_job() -> None:
    """Weekly: let the Alpha Stack retune itself within the approved bounds.

    Weekly rather than daily on purpose. Forward returns take ten trading days to
    mature, so a daily refit would mostly re-fit the same data and produce a chain
    of promotions chasing noise. The per-scope cooldown is the harder guarantee;
    the weekly cadence just avoids the pointless work.
    """
    from app.services.auto_adapt import run_auto_adaptation
    settings = get_settings()
    session = session_factory()()
    try:
        out = run_auto_adaptation(session, settings)
        if out.get("status") == "OK":
            log.info("Auto-adaptation: %d scope(s) promoted", out["promoted"])
            for scope in out["scopes"]:
                log.info("  %s: %s — %s", scope["scope"], scope["action"],
                         scope.get("reason") or scope.get("summary", ""))
        else:
            log.info("Auto-adaptation: %s", out.get("note"))
    except Exception:
        log.exception("Auto-adaptation crashed")
    finally:
        session.close()


def _run_briefing_job() -> None:
    """Warm today's briefing before the open so it's cached when the app loads."""
    from app.services.briefing_service import build_briefing
    from app.services.market_news_service import macro_digest, refresh_market_news
    from app.services.news_sentiment_service import refresh_signal_news
    settings = get_settings()
    session = session_factory()()
    try:
        news = refresh_market_news(session, settings)
        log.info("Market news refreshed: +%d headlines", news["inserted"])
        macro_digest(session, settings)     # warm the macro layer's cache too
        signal_news = refresh_signal_news(session, settings)
        log.info("Signal news refreshed: %d symbols, %d failures",
                 signal_news["processed"], signal_news["failures"])
        result = build_briefing(session, settings, force=True)
        log.info("Morning briefing generated (narrative: %s)",
                 "yes" if result.get("narrative") else "disabled")
    except Exception:
        log.exception("Morning briefing crashed")
    finally:
        session.close()


def start_scheduler() -> BackgroundScheduler | None:
    settings = get_settings()
    if not settings.scheduler_enabled:
        log.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return None
    scheduler = BackgroundScheduler(timezone=settings.timezone)
    scheduler.add_job(_run_sync_job, CronTrigger.from_crontab(settings.sync_cron,
                                                              timezone=settings.timezone),
                      id="daily_sync", replace_existing=True)
    scheduler.add_job(_run_fundamentals_job,
                      CronTrigger.from_crontab(settings.fundamentals_cron,
                                               timezone=settings.timezone),
                      id="weekly_fundamentals", replace_existing=True)
    scheduler.add_job(_run_briefing_job,
                      CronTrigger.from_crontab(settings.briefing_cron,
                                               timezone=settings.timezone),
                      id="morning_briefing", replace_existing=True)
    # Sunday 06:00 — after the week's outcomes have been labelled, before Monday.
    scheduler.add_job(_run_adaptation_job,
                      CronTrigger.from_crontab("0 6 * * SUN",
                                               timezone=settings.timezone),
                      id="weekly_adaptation", replace_existing=True)
    scheduler.start()
    log.info("Scheduler started: daily sync '%s', fundamentals '%s', briefing '%s', "
             "adaptation weekly (auto-adapt %s) (%s)",
             settings.sync_cron, settings.fundamentals_cron, settings.briefing_cron,
             "ON" if settings.auto_adapt_enabled else "off", settings.timezone)
    return scheduler
