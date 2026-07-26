import { ScreenCondition } from '../../core/models/market-data.models';

export interface ScreenerPreset {
  name: string;
  description: string;
  conditions: ScreenCondition[];
}

/** Curated starting points — every one expressible in the plain field/op/value|ref DSL. */
export const SCREENER_PRESETS: ScreenerPreset[] = [
  {
    name: 'Oversold (RSI < 30)',
    description: 'Potential mean-reversion candidates',
    conditions: [{ field: 'rsi_14', op: 'lt', value: 30 }],
  },
  {
    name: 'Overbought (RSI > 70)',
    description: 'Extended stocks — caution or momentum',
    conditions: [{ field: 'rsi_14', op: 'gt', value: 70 }],
  },
  {
    name: 'Uptrend (price > SMA200)',
    description: 'Long-term trend filter',
    conditions: [{ field: 'close', op: 'gt', ref: 'sma_200' }],
  },
  {
    name: 'Golden alignment',
    description: 'Price > SMA50 > SMA200',
    conditions: [
      { field: 'close', op: 'gt', ref: 'sma_50' },
      { field: 'sma_50', op: 'gt', ref: 'sma_200' },
    ],
  },
  {
    name: 'Near 52-week high',
    description: 'Within 5% of the 52w high',
    conditions: [{ field: 'pct_from_52w_high', op: 'gte', value: -5 }],
  },
  {
    name: 'Volume surge',
    description: 'Volume ≥ 2× its 20-day average',
    conditions: [{ field: 'volume_ratio', op: 'gte', value: 2 }],
  },
  {
    name: 'MACD bullish',
    description: 'MACD above its signal line',
    conditions: [{ field: 'macd', op: 'gt', ref: 'macd_signal' }],
  },

  // ---- Ichimoku ----------------------------------------------------------
  // "Blue crossing red" is the Tenkan (9-period) crossing the Kijun (26-period).
  // On its own that's just a momentum flip; combined with price clearing the
  // cloud it's the classic Ichimoku breakout, which is what these screen for.
  {
    name: 'Ichimoku breakout (fresh TK cross)',
    description: 'Blue (Tenkan) crossed above red (Kijun) in the last 3 days AND price broke out above the cloud',
    conditions: [
      { field: 'ichimoku_bullish', op: 'gte', value: 1 },
      { field: 'tk_cross_age_days', op: 'lte', value: 3 },
    ],
  },
  {
    name: 'Ichimoku bullish (above cloud)',
    description: 'Blue above red and price clear of the cloud — the trend is already established',
    conditions: [{ field: 'ichimoku_bullish', op: 'gte', value: 1 }],
  },
  {
    name: 'TK cross — blue over red',
    description: 'Tenkan above Kijun, regardless of the cloud (earlier, weaker signal)',
    conditions: [{ field: 'tenkan_9', op: 'gt', ref: 'kijun_26' }],
  },

  // ---- Famous fundamental filters ---------------------------------------
  // Approximations of well-known published screens, expressed over the ratios
  // available on the snapshot. They are starting points, not exact reproductions
  // of the original multi-factor scores (e.g. full Piotroski F-Score needs data
  // we don't yet store) — read them as "in the spirit of".
  {
    name: 'Graham value',
    description: 'Benjamin Graham defensive value: cheap earnings & assets (P/E < 15, P/B < 1.5), positive dividend',
    conditions: [
      { field: 'pe_trailing', op: 'gt', value: 0 },
      { field: 'pe_trailing', op: 'lt', value: 15 },
      { field: 'pb', op: 'lt', value: 1.5 },
      { field: 'dividend_yield_pct', op: 'gt', value: 0 },
    ],
  },
  {
    name: 'Magic Formula (Greenblatt, approx.)',
    description: 'Good & cheap: high return on equity with a low earnings multiple',
    conditions: [
      { field: 'roe_pct', op: 'gte', value: 20 },
      { field: 'pe_trailing', op: 'gt', value: 0 },
      { field: 'pe_trailing', op: 'lt', value: 15 },
    ],
  },
  {
    name: 'Quality compounder (Buffett-style)',
    description: 'Durable quality: high ROE, healthy margins, low leverage',
    conditions: [
      { field: 'roe_pct', op: 'gte', value: 18 },
      { field: 'profit_margin_pct', op: 'gte', value: 12 },
      { field: 'debt_to_equity', op: 'lt', value: 0.7 },
    ],
  },
  {
    name: 'Growth (CANSLIM-style)',
    description: 'Strong revenue growth in a confirmed uptrend near its highs',
    conditions: [
      { field: 'revenue_growth_pct', op: 'gte', value: 20 },
      { field: 'close', op: 'gt', ref: 'sma_200' },
      { field: 'pct_from_52w_high', op: 'gte', value: -15 },
    ],
  },
  {
    name: 'Dividend income',
    description: 'Solid, profitable dividend payers (yield ≥ 3%, sustainable leverage)',
    conditions: [
      { field: 'dividend_yield_pct', op: 'gte', value: 3 },
      { field: 'profit_margin_pct', op: 'gt', value: 0 },
      { field: 'debt_to_equity', op: 'lt', value: 1.5 },
    ],
  },
  {
    name: 'Low-debt large caps',
    description: 'Large, financially sturdy companies with little leverage',
    conditions: [
      { field: 'market_cap', op: 'gte', value: 200000000000 },
      { field: 'debt_to_equity', op: 'lt', value: 0.5 },
    ],
  },
  {
    name: 'GARP (growth at a reasonable price)',
    description: 'Growth with valuation discipline: earnings growth ≥ P/E, modest multiple',
    conditions: [
      { field: 'revenue_growth_pct', op: 'gte', value: 12 },
      { field: 'pe_trailing', op: 'gt', value: 0 },
      { field: 'pe_trailing', op: 'lt', value: 25 },
      { field: 'roe_pct', op: 'gte', value: 15 },
    ],
  },
];
