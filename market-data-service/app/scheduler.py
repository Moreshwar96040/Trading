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


def _run_briefing_job() -> None:
    """Warm today's briefing before the open so it's cached when the app loads."""
    from app.services.briefing_service import build_briefing
    settings = get_settings()
    session = session_factory()()
    try:
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
    scheduler.start()
    log.info("Scheduler started: daily sync '%s', fundamentals '%s', briefing '%s' (%s)",
             settings.sync_cron, settings.fundamentals_cron, settings.briefing_cron,
             settings.timezone)
    return scheduler
