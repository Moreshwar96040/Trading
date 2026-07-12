# Personal Trading Platform

NSE equities · all 7 phases: market data, screener + technical analysis, fundamentals,
strategy builder + backtesting, paper trading + portfolio, risk + alerts,
journal + AI analysis. See `docs/ARCHITECTURE.md` for design details.

## Stack

Angular 19 + Material + TradingView lightweight-charts · Spring Boot 3.5 / Java 21 ·
Python FastAPI (ingestion, future AI engine) · PostgreSQL 16 · Docker (DB only).

## Prerequisites

Java 21, Maven 3.9+, Node 20+, Python 3.11+, Docker Desktop.

## First-time setup

```bash
cp .env.example .env

# 1. Database
docker compose up -d

# 2. Backend (applies Flyway schema + seeds 20 NSE symbols)
cd backend && mvn spring-boot:run

# 3. Python market-data service
cd market-data-service
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements-dev.txt
uvicorn app.main:app --port 8000

# 4. Frontend
cd frontend && npm install && npm start
```

Trigger the first sync to backfill history from Yahoo Finance (lookback window set by
`SYNC_DEFAULT_LOOKBACK_DAYS`, default 730 days):
`curl -X POST localhost:8080/api/v1/sync/daily -H "Content-Type: application/json" -d "{}"`.

Open http://localhost:4200 → search `RELIANCE` → candlestick chart.

## Daily use

The Python service auto-syncs EOD data at 18:30 IST (configurable via `SYNC_CRON`).
Manual sync: `curl -X POST localhost:8080/api/v1/sync/daily -H "Content-Type: application/json" -d "{}"`.

## API summary

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/symbols?query=rel` | search symbol master |
| `GET /api/v1/symbols/{ticker}/candles?from&to` | daily candles (ISO dates) |
| `GET /api/v1/quotes/{ticker}` | delayed quote (proxied to Python → Yahoo) |
| `POST /api/v1/sync/daily` | trigger EOD sync (gap backfill included) |
| `POST /api/v1/sync/snapshot` | recompute screener snapshots (auto after daily sync) |
| `GET /api/v1/indicators/{ticker}?from&to` | indicator series (SMA/EMA/RSI/MACD/BB/ATR) |
| `POST /api/v1/screener/run` | run screen: `{"conditions":[{"field":"rsi_14","op":"lt","value":30}]}` — `ref` instead of `value` compares two fields |
| `GET /api/v1/screener/fields` | available screener fields + operators (incl. P/E, ROE, D/E…) |
| `GET /api/v1/fundamentals/{ticker}` | ratios + annual/quarterly statements |
| `POST /api/v1/sync/fundamentals` | fetch fundamentals from Yahoo (auto-runs Saturdays 8:00 IST) |
| `POST/GET/PUT/DELETE /api/v1/strategies` | strategy CRUD (definitions validated by the Python engine) |
| `POST /api/v1/strategies/{id}/backtests` | run a backtest (synchronous) |
| `GET /api/v1/backtests/{id}` | metrics + equity curve + trade list |
| `GET /api/v1/paper/account` | paper account: cash, equity, P&L, positions |
| `POST /api/v1/paper/orders` | place market order: `{"ticker":"TCS","side":"BUY","quantity":10}` |
| `GET /api/v1/paper/orders` | order history (fills + rejections) |
| `POST /api/v1/paper/account/reset` | wipe positions, restore cash |
| `GET/PUT /api/v1/risk/settings` | risk limits (max position/sector %, risk per trade) |
| `GET /api/v1/risk/report` | exposure vs limits, breach warnings |
| `POST /api/v1/risk/position-size` | qty from entry/stop and risk % |
| `GET/POST/DELETE /api/v1/alerts` | alerts on any screener field; auto-checked after daily sync |
| `POST /api/v1/alerts/evaluate` | check all active alerts now |
| `GET/POST/PUT/DELETE /api/v1/journal` | trade journal entries (title, body, tags, optional symbol) |
| `GET /api/v1/ai/predictions` | next-day predictions with honest test-set accuracy |
| `POST /api/v1/ai/train` | retrain RandomForest models on stored history (~30s) |

## Tests

```bash
cd backend && mvn test                      # JUnit + Mockito (+ Testcontainers if Docker up)
cd market-data-service && python -m pytest  # unit tests, SQLite in-memory
cd frontend && npm test                     # Karma/Jasmine (needs Chrome)
```
