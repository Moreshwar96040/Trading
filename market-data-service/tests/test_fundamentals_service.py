from datetime import date

from sqlalchemy import func, select

from app.models import FinancialStatement, Fundamentals, SyncAudit
from app.providers.base import FundamentalDataProvider, ProviderError
from app.services.fundamentals_service import refresh_fundamentals


class FakeFundamentalsProvider(FundamentalDataProvider):
    def __init__(self, pe=25.0, fail=False):
        self.pe = pe
        self.fail = fail

    def fetch_fundamentals(self, vendor_symbol):
        if self.fail:
            raise ProviderError("boom")
        return {"pe_trailing": self.pe, "market_cap": 1_000_000.0, "roe_pct": 15.0}

    def fetch_statements(self, vendor_symbol):
        return [{"period_end": date(2025, 3, 31), "period_type": "ANNUAL",
                 "revenue": 1000.0, "net_income": 100.0}]


def test_refresh_inserts_ratios_and_statements(session, reliance):
    summary = refresh_fundamentals(session, FakeFundamentalsProvider())

    assert summary["status"] == "SUCCESS"
    assert summary["symbols_updated"] == 1
    fund = session.get(Fundamentals, reliance.id)
    assert float(fund.pe_trailing) == 25.0
    assert session.scalar(select(func.count()).select_from(FinancialStatement)) == 1


def test_refresh_is_idempotent_and_updates(session, reliance):
    refresh_fundamentals(session, FakeFundamentalsProvider(pe=25.0))
    refresh_fundamentals(session, FakeFundamentalsProvider(pe=30.0))

    assert float(session.get(Fundamentals, reliance.id).pe_trailing) == 30.0
    # statement upserted, not duplicated
    assert session.scalar(select(func.count()).select_from(FinancialStatement)) == 1


def test_refresh_failure_is_audited(session, reliance):
    summary = refresh_fundamentals(session, FakeFundamentalsProvider(fail=True))

    assert summary["status"] == "FAILED"
    audit = session.scalars(select(SyncAudit).where(SyncAudit.run_type == "FUNDAMENTALS")).first()
    assert audit.status == "FAILED"
    assert "RELIANCE" in audit.message
