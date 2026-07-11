from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.ai.features import (FEATURE_COLUMNS, TARGET_COLUMN, build_features,
                             latest_feature_row, training_frame)


def _ohlcv(n=300, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, n)))
    idx = [date(2025, 1, 1) + timedelta(days=i) for i in range(n)]
    return pd.DataFrame({
        "open": close * (1 + rng.normal(0, 0.002, n)),
        "high": close * 1.01, "low": close * 0.99, "close": close,
        "volume": rng.integers(1000, 5000, n).astype(float),
    }, index=idx)


def test_features_have_expected_columns():
    features = build_features(_ohlcv())
    assert set(FEATURE_COLUMNS + [TARGET_COLUMN]) <= set(features.columns)


def test_target_is_next_day_return_no_leakage():
    df = _ohlcv(100)
    features = build_features(df)
    close = df["close"]
    # target at row T equals (close[T+1]/close[T] - 1) * 100
    expected = (close.iloc[51] / close.iloc[50] - 1) * 100
    assert features[TARGET_COLUMN].iloc[50] == pytest.approx(expected)
    # last row's target must be NaN (tomorrow unknown)
    assert pd.isna(features[TARGET_COLUMN].iloc[-1])


def test_training_frame_drops_incomplete_rows():
    frame = training_frame(build_features(_ohlcv()))
    assert not frame.isna().any().any()
    assert len(frame) > 200


def test_latest_feature_row_exists_even_without_target():
    features = build_features(_ohlcv())
    row = latest_feature_row(features)
    assert row is not None
    assert not row[FEATURE_COLUMNS].isna().any()


def test_train_and_predict_end_to_end():
    sklearn = pytest.importorskip("sklearn")
    from app.ai.predictor import train_and_predict

    result = train_and_predict(_ohlcv(400))

    assert result.direction in ("UP", "DOWN", "FLAT")
    assert result.train_rows > 250
    assert 0 <= result.test_direction_accuracy <= 100
    assert result.test_mae_pct > 0
    assert abs(result.predicted_return_pct) < 20      # sane magnitude


def test_train_rejects_short_history():
    pytest.importorskip("sklearn")
    from app.ai.predictor import InsufficientDataError, train_and_predict

    with pytest.raises(InsufficientDataError):
        train_and_predict(_ohlcv(60))


def test_train_all_persists_predictions(session, reliance):
    pytest.importorskip("sklearn")
    from app.ai.service import train_all
    from app.models import AiPrediction, OhlcvDaily

    df = _ohlcv(300)
    for idx_date, row in df.iterrows():
        session.add(OhlcvDaily(symbol_id=reliance.id, trade_date=idx_date,
                               open=float(row["open"]), high=float(row["high"]),
                               low=float(row["low"]), close=float(row["close"]),
                               adj_close=float(row["close"]), volume=int(row["volume"])))
    session.commit()

    result = train_all(session)

    assert result["status"] == "SUCCESS"
    assert result["trained"] == 1
    prediction = session.get(AiPrediction, reliance.id)
    assert prediction is not None
    assert prediction.direction in ("UP", "DOWN", "FLAT")
    assert prediction.model_name.startswith("RandomForest")
