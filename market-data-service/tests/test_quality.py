import pandas as pd

from app.services.quality import validate_frame


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


GOOD = {"trade_date": "2026-01-02", "open": 100.0, "high": 110.0, "low": 95.0,
        "close": 105.0, "adj_close": 104.0, "volume": 1000}


def test_good_row_passes():
    clean, rejected = validate_frame(_frame([GOOD]))
    assert rejected == 0
    assert len(clean) == 1
    assert clean.iloc[0]["volume"] == 1000


def test_negative_price_rejected():
    clean, rejected = validate_frame(_frame([{**GOOD, "close": -5}]))
    assert rejected == 1 and clean.empty


def test_high_below_low_rejected():
    clean, rejected = validate_frame(_frame([{**GOOD, "high": 90.0, "low": 95.0}]))
    assert rejected == 1 and clean.empty


def test_missing_field_rejected():
    clean, rejected = validate_frame(_frame([{**GOOD, "open": None}]))
    assert rejected == 1 and clean.empty


def test_bad_date_rejected():
    clean, rejected = validate_frame(_frame([{**GOOD, "trade_date": "not-a-date"}]))
    assert rejected == 1 and clean.empty


def test_missing_adj_close_is_allowed():
    clean, rejected = validate_frame(_frame([{**GOOD, "adj_close": None}]))
    assert rejected == 0 and len(clean) == 1


def test_mixed_frame_keeps_only_good_rows():
    clean, rejected = validate_frame(_frame([GOOD, {**GOOD, "volume": -1},
                                             {**GOOD, "trade_date": "2026-01-03"}]))
    assert rejected == 1
    assert len(clean) == 2


def test_empty_frame():
    clean, rejected = validate_frame(pd.DataFrame())
    assert rejected == 0 and clean.empty
