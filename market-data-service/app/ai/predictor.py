"""Next-day return model: RandomForest, chronological 80/20 evaluation.

sklearn is imported lazily so the rest of the service runs without it.
Models are not persisted — 500-row datasets retrain in seconds (stateless).
"""
from dataclasses import dataclass

import pandas as pd

from app.ai.features import FEATURE_COLUMNS, TARGET_COLUMN, build_features, \
    latest_feature_row, training_frame

MODEL_NAME = "RandomForestRegressor(n=200)"
MIN_TRAINING_ROWS = 120
FLAT_THRESHOLD_PCT = 0.05


@dataclass(frozen=True)
class PredictionResult:
    predicted_return_pct: float
    direction: str                       # UP | DOWN | FLAT
    test_direction_accuracy: float | None
    test_mae_pct: float | None
    train_rows: int
    model_name: str


class InsufficientDataError(ValueError):
    pass


def train_and_predict(df: pd.DataFrame) -> PredictionResult:
    """df: OHLCV ascending. Trains on the first 80% (chronological), evaluates on
    the last 20%, then refits on all rows and predicts the next day."""
    from sklearn.ensemble import RandomForestRegressor

    features = build_features(df)
    data = training_frame(features)
    if len(data) < MIN_TRAINING_ROWS:
        raise InsufficientDataError(
            f"Need >= {MIN_TRAINING_ROWS} usable rows, have {len(data)}")

    X, y = data[FEATURE_COLUMNS], data[TARGET_COLUMN]
    split = int(len(data) * 0.8)

    eval_model = RandomForestRegressor(n_estimators=200, min_samples_leaf=5,
                                       random_state=42, n_jobs=-1)
    eval_model.fit(X.iloc[:split], y.iloc[:split])
    test_pred = pd.Series(eval_model.predict(X.iloc[split:]), index=y.index[split:])
    test_actual = y.iloc[split:]
    direction_accuracy = float(((test_pred > 0) == (test_actual > 0)).mean() * 100)
    mae = float((test_pred - test_actual).abs().mean())

    final_model = RandomForestRegressor(n_estimators=200, min_samples_leaf=5,
                                        random_state=42, n_jobs=-1)
    final_model.fit(X, y)
    live_row = latest_feature_row(features)
    if live_row is None:
        raise InsufficientDataError("No complete feature row to predict from")
    predicted = float(final_model.predict(live_row[FEATURE_COLUMNS].to_frame().T)[0])

    if predicted > FLAT_THRESHOLD_PCT:
        direction = "UP"
    elif predicted < -FLAT_THRESHOLD_PCT:
        direction = "DOWN"
    else:
        direction = "FLAT"

    return PredictionResult(
        predicted_return_pct=round(predicted, 4),
        direction=direction,
        test_direction_accuracy=round(direction_accuracy, 2),
        test_mae_pct=round(mae, 4),
        train_rows=len(data),
        model_name=MODEL_NAME,
    )
