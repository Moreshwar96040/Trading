# Trading Platform — Architecture (Phase 1: Foundation + Market Data)

## Overview

Modular monolith per service, three services total, one database. No microservices,
no Kubernetes — everything runs locally. Each service is independently testable and
replaceable, which is the seam that later allows scaling to many users without rewrites.

```
┌─────────────┐   REST    ┌──────────────────┐   REST    ┌──────────────────────┐
│  Angular UI  ├──────────►│  Spring Boot API  ├──────────►│ Python Market-Data   │
│  :4200       │           │  :8080            │           │ Service :8000        │
└─────────────┘           └────────┬─────────┘           └──────────┬───────────┘
                                    │ read (JPA)                      │ write (SQLAlchemy)
                                    ▼                                 ▼
                             ┌────────────────────────────────────────────┐
                             │            PostgreSQL :5432                │
                             └────────────────────────────────────────────┘
                                                                       ▲
                                                     Yahoo Finance ────┘ (yfinance, EOD + delayed quotes)
```

## Responsibilities

| Service | Owns | Never does |
|---|---|---|
| **Angular UI** (`frontend/`) | Presentation, chart rendering | Business logic, direct DB/Python access |
| **Spring Boot API** (`backend/`) | Domain API, schema (Flyway), validation, security | Data ingestion, talking to Yahoo |
| **Python service** (`market-data-service/`) | Ingestion (CSV + Yahoo), data quality, sync scheduling, quotes; future AI engine | Serving the UI directly |
| **PostgreSQL** | Single source of truth | — |

## Key design decisions

1. **Python owns writes, Java owns reads.** Ingestion is pandas-shaped work and the
   Python service will grow into the AI engine, so it writes OHLCV. Spring Boot is the
   single API the UI talks to; it proxies quote/sync calls to Python. One writer per
   table avoids coordination problems.
2. **Flyway (in Spring Boot) owns the schema.** One migration source of truth. The
   Python SQLAlchemy models mirror the schema but never run DDL in production
   (ORM `create_all` is used only in unit tests against SQLite).
3. **Provider abstraction.** Yahoo is unofficial and may break. All external data goes
   through a `MarketDataProvider` interface (`providers/base.py`); swapping to Zerodha
   Kite or NSE bhavcopy later touches one package.
4. **Idempotent ingestion.** `ON CONFLICT (symbol_id, trade_date) DO NOTHING` — reruns
   and overlapping fetch windows are safe. Every run writes a `sync_audit` row.
5. **Multi-user seam without multi-user features.** No `user_id` anywhere in Phase 1
   (market data is global — shared across all future users by nature). Later per-user
   entities (portfolios, journals) will carry `user_id` when they are born. Spring
   Security is wired now (permit-all `local` profile) so adding auth is config, not surgery.
6. **Configuration-driven.** All URLs, credentials, cron schedules, throttle delays come
   from environment variables / Spring profiles. `.env.example` documents every knob.

## Folder structure

```
Trading/
├── docker-compose.yml          # PostgreSQL (dev infra)
├── .env.example                # every configurable value, documented
├── README.md                   # how to run everything
├── docs/ARCHITECTURE.md        # this file
├── backend/                    # Spring Boot 3 / Java 21 — domain API
│   └── src/main/java/com/tradingplatform/api/
│       ├── common/             #   config, security, error handling
│       ├── marketdata/         #   feature package: domain / repository / service / web
│       └── integration/        #   client for the Python service
├── market-data-service/        # Python 3.11+ / FastAPI — ingestion + future AI
│   ├── app/
│   │   ├── providers/          #   MarketDataProvider interface + Yahoo impl
│   │   ├── services/           #   csv_ingestion, sync, data quality
│   │   └── api/                #   FastAPI routes
│   └── tests/
└── frontend/                   # Angular 19 + Material + lightweight-charts
    └── src/app/
        ├── core/               #   API client services, models
        └── features/chart/     #   chart page + candlestick component
```

## Data flow examples

**Daily sync (scheduled 18:30 IST or manual):** APScheduler / `POST /internal/sync/daily`
→ for each active symbol: last stored date → fetch gap from Yahoo → validate rows
(`quality.py`) → bulk upsert → `sync_audit` row.

**Chart load:** UI `GET /api/v1/symbols/RELIANCE/candles?from=&to=` → Spring JPA query
→ JSON (arrays shaped for lightweight-charts).

**Quote:** UI → Spring `GET /api/v1/quotes/RELIANCE` → Python `GET /internal/quotes/RELIANCE.NS`
→ Yahoo (15-min delayed).

## Ports & config

| Thing | Value (default, overridable via .env) |
|---|---|
| PostgreSQL | `localhost:5432`, db `trading`, user `trading` |
| Spring Boot | `localhost:8080`, context `/api` |
| Python service | `localhost:8000` (internal — only Spring calls it) |
| Angular dev server | `localhost:4200`, proxies `/api` → 8080 |

## Phase 2 — Screener + Technical Analysis

**Requirements.** FR8: compute standard indicators (SMA 20/50/200, EMA 20, RSI 14,
MACD 12/26/9, Bollinger 20/2σ, ATR 14, 52-week high/low, 1M/3M/1Y returns, volume ratio)
from stored OHLCV. FR9: indicator series API for chart overlays. FR10: nightly (post-sync)
snapshot of latest indicator values per symbol for screening. FR11: screener API filtering
on any snapshot field with ops gt/gte/lt/lte/eq against a value **or another field**
(enables "close > sma_200", "sma_50 > sma_200"). FR12: screener UI with presets +
custom conditions + results table; row click opens the chart. FR13: chart overlays
(SMA/Bollinger) + RSI pane.

**Design decisions.**
1. *Indicators are pure pandas* (`app/indicators/core.py`) — no TA-Lib native dependency
   (painful on Windows), no pandas-ta. Each function is deterministic and unit-tested
   against hand-computed values. Wilder's smoothing for RSI/ATR.
2. *Screening happens in SQL, not pandas.* Python precomputes one `screener_snapshot`
   row per symbol (upsert after each daily sync); Spring translates the filter DSL into
   JPA Specifications against that table. Fast, and the DSL is whitelisted field-by-field
   so no injection or invalid-column risk.
3. *Series are computed on demand* (≤ ~500 rows/symbol) — no historical indicator storage
   until a future phase actually needs it (backtesting will recompute in-process anyway).
4. Derived ratios (`volume_ratio`, `pct_from_52w_high`) are precomputed columns so every
   preset stays expressible in the simple `field op value|ref` DSL.

**New endpoints.** `GET /api/v1/indicators/{ticker}?from&to` (proxy → Python),
`POST /api/v1/screener/run` (Spring/SQL), `GET /api/v1/screener/fields` (DSL metadata),
`POST /api/v1/sync/snapshot` (proxy → Python recompute).

## Phase 3 — Fundamental Analysis

**Requirements.** FR14: ingest key ratios per symbol (market cap, P/E, P/B, P/S, dividend
yield, ROE, D/E, margins, growth, EPS, beta) from Yahoo Finance. FR15: ingest annual +
quarterly financial statements (revenue, operating/net income, EPS, assets, liabilities,
equity, operating/free cash flow). FR16: fundamentals API per symbol (ratios + statements).
FR17: screener gains fundamental fields (pe_trailing, pb, roe_pct, debt_to_equity,
dividend_yield_pct, market_cap, profit_margin_pct, revenue_growth_pct). FR18: fundamentals
UI page — ratio cards, statements table, revenue/net-income trend. Refresh: weekly cron
(fundamentals change quarterly; configurable `FUNDAMENTALS_CRON`) + on demand.

**Design decisions.**
1. *Denormalize key ratios into `screener_snapshot`.* The screener stays a single-table
   SQL query (no joins in the Criteria code). The snapshot refresher copies current ratios
   from `fundamentals`. Full detail lives in `fundamentals` + `financial_statements`.
2. *Yahoo `info`/statement parsing is quarantined* in `app/services/fundamentals_mapping.py`
   — pure functions (dict/DataFrame → row dicts), unit-testable without yfinance installed.
   Yahoo renames statement line items regularly; `_line()` tries known label variants.
3. Statements are *upserted by (symbol, period_end, period_type)* — idempotent like OHLCV.
4. All monetary values NUMERIC(22,2) in INR — Indian large caps exceed 32-bit paise easily.

**New endpoints.** `GET /api/v1/fundamentals/{ticker}`, `POST /api/v1/sync/fundamentals`
(proxy → Python `/internal/fundamentals/refresh`).

## Phase 4 — Strategy Builder + Backtesting

**Requirements.** FR19: define strategies as JSON rule sets — entry rules (ANDed),
optional exit rules (ANDed), plus stop-loss %, take-profit %, max holding days (any one
triggers exit). Rules: `left op right` where left/right are series names
(close/open/high/low/volume, `sma_N`, `ema_N`, `rsi_N`, `macd`, `macd_signal`,
`macd_hist`, `bb_upper/mid/lower`, `atr_N`) or numeric literals; ops:
gt/gte/lt/lte/crosses_above/crosses_below. FR20: portfolio backtest over any subset of
symbols and dates: shared capital, max concurrent positions, equal-weight sizing,
commission per side. FR21: results = metric set (total/CAGR/max drawdown/Sharpe/win
rate/profit factor/exposure), daily equity curve, full trade list — persisted per run.
FR22: strategy CRUD + backtest history APIs. FR23: UI — strategy editor with rule rows,
run panel, metric cards, equity-curve chart, trades table.

**Design decisions.**
1. *No lookahead by construction:* signals are evaluated on bar T, execution happens at
   the OPEN of bar T+1. Stops/targets execute intra-bar off high/low with gap handling
   (exit at worse of stop price / open).
2. *Engine is pure* (`app/backtest/rules|engine|metrics.py`): DataFrames in, dataclasses
   out — fully unit-testable without DB/Yahoo. Persistence lives in `service.py` only.
3. *Ownership split:* Spring owns `strategies` (CRUD; definition validated by the Python
   engine via `/internal/strategies/validate` before save). Python owns `backtests` +
   `backtest_trades` (it produces them). One writer per table, as before.
4. *Synchronous runs.* 20 symbols × 2 years of dailies backtests in well under a second —
   no job queue until the universe grows (that would be overengineering today).
5. Indicator names are parsed dynamically (`sma_50` → SMA(50)), reusing Phase 2's
   `indicators/core.py` — one indicator implementation for charts, screener and backtests.

**New endpoints.** Spring: `POST/GET/PUT/DELETE /api/v1/strategies`,
`POST /api/v1/strategies/{id}/backtests` (run), `GET /api/v1/strategies/{id}/backtests`,
`GET /api/v1/backtests/{id}`. Python: `POST /internal/strategies/validate`,
`POST /internal/backtests/run`.

## Phase 5 — Paper Trading + Portfolio Tracking

**Requirements.** FR24: one virtual cash account (seeded ₹10,00,000; resettable). FR25:
market orders (BUY/SELL) fill immediately at a reference price — live delayed quote when
Yahoo is reachable, otherwise the latest stored close (source recorded on the order).
FR26: position tracking with average-cost basis; realized P&L on sells; commission per
side (configurable). FR27: rejections with reasons (insufficient cash, oversell, unknown
symbol) are stored as REJECTED orders — an audit trail of intent. FR28: portfolio API —
cash, equity, realized/unrealized P&L, positions marked to latest price. FR29: UI —
portfolio summary cards, positions table, order ticket, order history.

**Design decisions.**
1. *Spring owns all paper_* writes* — first exception to "Python writes"; this is pure
   transactional domain logic (no pandas), so it lives beside the API in Java.
   `@Transactional` order fill = insert order + update position + update cash atomically.
2. *Average-cost basis* (not FIFO lots): standard for Indian retail, far simpler, and
   sufficient until the Trade Journal phase needs lot detail (documented trade-off).
3. *Price fallback chain* (`PriceService`): Python quote → latest `ohlcv_daily` close.
   Paper trading therefore works fully offline on EOD data.
4. *account_id on every row* from day one — the multi-user seam again, but only one
   seeded account today. No account-management UI (YAGNI).

**New endpoints.** `GET /api/v1/paper/account`, `POST /api/v1/paper/orders`,
`GET /api/v1/paper/orders`, `POST /api/v1/paper/account/reset`.

## Phase 6 — Risk Management + Alerts

**Requirements.** FR30: configurable risk settings (max position % of equity, max sector
% of equity, risk per trade %, hard-block toggle) — single seeded row. FR31: position-size
calculator: `qty = floor(equity × risk% / (entry − stop))`, capped by the max-position
limit. FR32: risk report — per-position and per-sector exposure as % of equity, cash %,
and any limit breaches. FR33: paper BUY orders that would breach the max-position limit
are REJECTED (with reason) when hard-block is on. FR34: alerts on any screener-snapshot
field (`close`, `rsi_14`, `pe_trailing`, …) with gt/gte/lt/lte/eq vs a value; evaluated
automatically after each daily sync and on demand; one-shot TRIGGERED with the observed
value + timestamp, re-armable. In-app delivery only (email/Telegram = future phase).

**Design decisions.**
1. *Alerts table has two writers by design* (documented exception): Spring owns the
   definition columns (CRUD), Python owns the lifecycle columns (status/triggered_at/
   triggered_value) — it evaluates right after refreshing the snapshot it compares
   against. Disjoint column sets, no conflict.
2. *Risk checks use book-value equity* (cash + Σ qty×avg_cost) at fill time — no network
   calls inside the order transaction; marked-to-market exposure appears in the report.
3. Alert conditions reuse the screener field whitelist — one vocabulary everywhere.

**New endpoints.** `GET/PUT /api/v1/risk/settings`, `GET /api/v1/risk/report`,
`POST /api/v1/risk/position-size`, `GET/POST/DELETE /api/v1/alerts`,
`POST /api/v1/alerts/{id}/rearm`, `POST /api/v1/alerts/evaluate` (proxy → Python
`/internal/alerts/evaluate`).

## Phase 7 — Trade Journal + AI Analysis

**Requirements.** FR35: journal entries — title, free-text body, comma tags, optional
symbol and optional link to a paper order; full CRUD + filter by symbol/tag. FR36:
next-day return prediction per symbol from indicator features (lagged returns, RSI,
MACD histogram, volume ratio, SMA ratios, 52w-high distance) using a RandomForest;
honest out-of-sample evaluation (chronological 80/20 split — no shuffling, no leakage).
FR37: predictions persisted with their test-set quality metrics (directional accuracy,
MAE) so every number carries its own credibility label. FR38: retrain on demand; models
are NOT persisted — 500-row datasets retrain in seconds, keeping the system stateless.
FR39: UI — journal page; AI page with predictions table, quality metrics, train button,
and a prominent educational disclaimer.

**Design decisions.**
1. *Feature engineering is a pure module* (`app/ai/features.py`) — target is next-day
   return via `shift(-1)`, all features use only past data; tested for no-lookahead.
2. *sklearn is imported lazily* so the service runs (and tests pass) without it —
   only the AI endpoints require it.
3. Journal is Spring-owned (pure CRUD domain); `ai_predictions` is Python-owned. Same
   ownership rules as before.
4. Direction accuracy on the test window is stored per symbol; the UI shows it beside
   each prediction — a model that's 51% accurate should look exactly as weak as it is.

**New endpoints.** `GET/POST/PUT/DELETE /api/v1/journal`, `GET /api/v1/ai/predictions`,
`POST /api/v1/ai/train` (proxy → Python `/internal/ai/train`).

## Testing strategy

- **Python:** pytest unit tests (SQLite in-memory, mocked provider); E2E ingestion verified against real PostgreSQL.
- **Java:** JUnit 5 + Mockito unit tests; `@WebMvcTest` slices; Testcontainers integration test (auto-skips when Docker absent).
- **Angular:** component/service specs; production build as compile-time verification.
