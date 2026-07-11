from pathlib import Path

from sqlalchemy import func, select

from app.models import OhlcvDaily, SyncAudit
from app.services.csv_ingestion import ingest_directory

CSV = """Date,Open,High,Low,Close,AdjClose,Volume,Split
2026-01-01,100,110,95,105,104,1000,train
2026-01-02,105,115,100,110,109,2000,train
2026-01-03,-1,115,100,110,109,2000,train
"""


def _write_csv(tmp_path: Path, ticker: str, content: str = CSV) -> Path:
    p = tmp_path / f"{ticker}.csv"
    p.write_text(content)
    return p


def test_ingest_inserts_valid_rows_and_rejects_bad(session, reliance, tmp_path):
    _write_csv(tmp_path, "RELIANCE")
    summary = ingest_directory(session, str(tmp_path))

    assert summary["status"] == "SUCCESS"
    assert summary["rows_inserted"] == 2
    assert summary["rows_rejected"] == 1
    assert session.scalar(select(func.count()).select_from(OhlcvDaily)) == 2


def test_ingest_is_idempotent(session, reliance, tmp_path):
    _write_csv(tmp_path, "RELIANCE")
    ingest_directory(session, str(tmp_path))
    summary2 = ingest_directory(session, str(tmp_path))

    assert summary2["rows_inserted"] == 0          # duplicates skipped
    assert session.scalar(select(func.count()).select_from(OhlcvDaily)) == 2


def test_ingest_writes_audit_row(session, reliance, tmp_path):
    _write_csv(tmp_path, "RELIANCE")
    ingest_directory(session, str(tmp_path))

    audit = session.scalars(select(SyncAudit)).first()
    assert audit.run_type == "CSV_IMPORT"
    assert audit.status == "SUCCESS"
    assert audit.rows_inserted == 2
    assert audit.finished_at is not None


def test_missing_csv_is_skipped_not_failed(session, reliance, tmp_path):
    summary = ingest_directory(session, str(tmp_path))   # empty dir
    assert summary["status"] == "SUCCESS"
    assert summary["rows_inserted"] == 0
