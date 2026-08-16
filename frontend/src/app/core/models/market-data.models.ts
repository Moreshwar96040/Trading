/** Shapes returned by the backend API (see backend web/dto records). */

export interface SymbolInfo {
  id: number;
  ticker: string;
  name: string;
  sector: string | null;
  exchange: string;
  currency: string;
}

export interface Candle {
  time: string; // ISO yyyy-MM-dd — matches lightweight-charts' expected format
  open: number;
  high: number;
  low: number;
  close: number;
  adjClose: number | null;
  volume: number;
}

export interface CandleSeries {
  ticker: string;
  from: string;
  to: string;
  candles: Candle[];
}

export interface ScreenCondition {
  field: string;
  op: 'gt' | 'gte' | 'lt' | 'lte' | 'eq';
  value?: number | string | null;
  ref?: string | null;
}

export interface ScreenRequest {
  conditions: ScreenCondition[];
  sortBy?: string;
  sortDir?: 'asc' | 'desc';
  limit?: number;
}

export interface ScreenRow {
  ticker: string;
  name: string;
  sector: string | null;
  asOfDate: string;
  close: number;
  change1dPct: number | null;
  volumeRatio: number | null;
  rsi14: number | null;
  sma50: number | null;
  sma200: number | null;
  pctFrom52wHigh: number | null;
  return1mPct: number | null;
  return3mPct: number | null;
  return1yPct: number | null;
  /** Ichimoku: bars since Tenkan (blue) crossed above Kijun (red) — null while
   *  bearish. `ichimokuBullish` is 1 when that cross holds AND price has broken
   *  out above the cloud. */
  tkCrossAgeDays: number | null;
  pctAboveCloud: number | null;
  ichimokuBullish: number | null;
  /** Major swing support level and price's % distance above it (negative = broken). */
  support: number | null;
  pctFromSupport: number | null;
}

export interface ScreenerFieldsMeta {
  numeric: string[];
  string: string[];
  ops: string[];
}

export interface IndicatorSeries {
  ticker: string;
  dates: string[];
  series: Record<string, (number | null)[]>;
}

export interface FundamentalRatios {
  marketCap: number | null;
  peTrailing: number | null;
  peForward: number | null;
  pb: number | null;
  ps: number | null;
  dividendYieldPct: number | null;
  roePct: number | null;
  debtToEquity: number | null;
  profitMarginPct: number | null;
  operatingMarginPct: number | null;
  revenueGrowthPct: number | null;
  earningsGrowthPct: number | null;
  epsTrailing: number | null;
  bookValue: number | null;
  beta: number | null;
  computedAt: string | null;
}

export interface StatementRow {
  periodEnd: string;
  revenue: number | null;
  operatingIncome: number | null;
  netIncome: number | null;
  eps: number | null;
  totalAssets: number | null;
  totalLiabilities: number | null;
  shareholdersEquity: number | null;
  operatingCashFlow: number | null;
  freeCashFlow: number | null;
}

export interface FundamentalsData {
  ticker: string;
  name: string;
  sector: string | null;
  ratios: FundamentalRatios | null;
  annual: StatementRow[];
  quarterly: StatementRow[];
}

export interface StrategyRule {
  left: string;
  op: 'gt' | 'gte' | 'lt' | 'lte' | 'crosses_above' | 'crosses_below';
  right: string | number;
}

export interface StrategyDefinition {
  entry: StrategyRule[];
  exit?: StrategyRule[];
  stop_loss_pct?: number | null;
  take_profit_pct?: number | null;
  max_holding_days?: number | null;
  atr_stop_mult?: number | null;   // self-adjusting stop: entry − mult×ATR
  atr_trail?: boolean | null;      // ratchet the ATR stop up as price rises
}

export interface StrategyInfo {
  id: number;
  name: string;
  description: string | null;
  definition: StrategyDefinition;
  createdAt: string;
  updatedAt: string;
}

export interface BacktestRunParams {
  tickers?: string[];
  from?: string;
  to?: string;
  initial_capital?: number;
  max_positions?: number;
  commission_pct?: number;
  timeframe?: '15m' | 'daily' | 'weekly' | 'monthly';
}

export interface BacktestMetrics {
  total_return_pct: number;
  cagr_pct: number | null;
  max_drawdown_pct: number;
  sharpe: number | null;
  trades: number;
  win_rate_pct: number | null;
  profit_factor: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  final_equity: number;
  data_coverage_note?: string;
  robustness?: RobustnessReport;
}

export interface RobustnessReport {
  score: number;
  verdict: 'ROBUST' | 'PROMISING' | 'FRAGILE' | 'OVERFIT_RISK';
  components: { sample_size: number; monte_carlo: number; holdout: number };
  reasons: string[];
  monte_carlo: {
    resamples: number;
    return_p5: number; return_p25: number; return_p50: number;
    return_p75: number; return_p95: number;
    drawdown_p50: number; drawdown_p95: number;
    prob_loss_pct: number;
    histogram: { min: number; max: number; counts: number[] };
  } | null;
  holdout: {
    in_sample_return_pct: number | null;
    out_sample_return_pct: number | null;
    in_sample_trades: number;
    out_sample_trades: number;
  } | null;
}

export interface RegimeInfo {
  status: 'OK' | 'NO_DATA';
  regime?: 'RISK_ON' | 'PULLBACK' | 'CHOP' | 'BEAR_RALLY' | 'RISK_OFF';
  label?: string;
  guidance?: string;
  volatility?: 'LOW' | 'NORMAL' | 'HIGH' | null;
  breadth?: {
    pct_above_sma200: number;
    pct_above_sma50: number;
    avg_rsi: number | null;
    avg_atr_pct: number | null;
    avg_return_1m_pct: number | null;
    symbols: number;
  };
  as_of?: string;
  note?: string;
}

export interface MacroDigest {
  sentiment?: 'positive' | 'negative' | 'neutral' | 'mixed';
  stance?: string;
  key_events?: string[];
  risk_flags?: string[];
}

export interface MarketNewsResponse {
  llm_enabled: boolean;
  headlines: { source: string; title: string; link: string | null;
               published_at: string | null }[];
  digest: { insight?: MacroDigest; error?: string; cached?: boolean } | null;
}

/** Result of POST /news/refresh — feeds re-pulled, macro digest regenerated,
 *  per-stock news refreshed for signaled/held symbols. */
export interface NewsRefreshResult {
  market: { fetched: number; inserted: number; failures: string[] };
  macro_sentiment: 'positive' | 'negative' | 'neutral' | 'mixed' | null;
  macro_error: string | null;
  signal_news: { processed: number; failures: number };
}

export interface DataHealth {
  symbols_active: number;
  daily: { last_bar: string; first_bar: string; rows: number };
  snapshot: { as_of: string };
  fundamentals: { symbols: number; oldest: string };
  intraday: { last_bar: string; rows: number };
  signals: { as_of: string };
  last_sync: { status: string | null; finished_at: string };
}

export interface EdgeGate {
  status: 'PASS' | 'FAIL' | 'PENDING';
  detail: string;
}

export interface EdgeGatesReport {
  status: 'OK' | 'NO_STRATEGIES';
  note?: string;
  thresholds: { backtest_trades: number; robustness: number; paper_trades: number };
  strategies: {
    strategy_id: number;
    name: string;
    description: string | null;
    verdict: 'VALIDATED' | 'IN_PROGRESS' | 'UNTESTED' | 'FAILED';
    gates: { sample: EdgeGate; robustness: EdgeGate; paper: EdgeGate; live_edge: EdgeGate };
  }[];
}

export interface MomentumStock {
  ticker: string;
  name: string;
  sector: string | null;
  close: number;
  rs_rank: number;
  return_1m_pct: number | null;
  return_3m_pct: number | null;
  pct_from_52w_high: number | null;
  volume_ratio: number | null;
}

export interface MomentumBoard {
  status: 'OK' | 'NO_DATA';
  note?: string;
  as_of?: string;
  universe?: number;
  sectors?: { sector: string; avg_rs: number; avg_1m_pct: number | null; stocks: number }[];
  leaders?: MomentumStock[];
  top?: MomentumStock[];
  laggards?: MomentumStock[];
}

export interface SymbolLookupResult {
  ticker: string;
  name: string;
  sector: string | null;
  in_db: boolean;
}

export interface QualityScore {
  score: number;
  grade: 'A' | 'B' | 'C' | 'D';
  components: { profitability: number; growth: number; balance_sheet: number;
                valuation: number };
}

export interface AlphaSetup {
  ticker: string;
  name: string;
  sector: string | null;
  close: number | null;
  strategies: { id: number; name: string }[];
  has_live_signal?: boolean;
  conviction: number;
  /** How SURE we are of the conviction estimate (0–1), as distinct from how good
   *  the setup looks. Drives size; conviction drives ranking. */
  confidence?: number;
  /** 1 = layers agree, 0 = the score is the average of a fight. */
  consensus?: number;
  dispersion?: number;
  regime_support?: number;
  conflicts?: { bullish_layer: string; bullish_strength: number;
                bearish_layer: string; bearish_strength: number; note: string }[];
  /** Deterministic explanation derived from the arithmetic — never LLM-invented. */
  rationale?: {
    headline: string; verdict: string; conviction: number; confidence: number;
    drivers: string[]; detractors: string[]; conflicts: string[];
    confidence_notes: string[]; veto_reason: string | null;
    action_hint: string | null;
  };
  risk_multiplier: number;
  /** Sizing detail: base multiplier tilted by volatility (inverse-ATR) and a
   *  data-completeness haircut. `size_note` explains the arithmetic. */
  atr_pct?: number | null;
  vol_factor?: number;
  data_quality?: number;
  size_note?: string;
  news_veto: boolean;
  news_score: number | null;
  quality: QualityScore | null;
  sentiment: string | null;
  verdict: 'HIGH' | 'NORMAL' | 'SMALL' | 'STAND_ASIDE' | 'VETOED';
  /** Each layer contributes `points` out of `max` (the layer's weight); the
   *  maxes sum to 100, so conviction is a literal percentage. `strength` is the
   *  0-1 normalized read, where 0.5 means neutral/unknown. */
  breakdown: {
    layer: string; points: number; max: number; strength: number;
    score_out_of_10?: number | null; note: string;
  }[];
}

export interface AlphaStack {
  status: 'OK' | 'NO_SIGNALS' | 'UNKNOWN_SYMBOL';
  regime: { code: string | null; label: string | null };
  setups: AlphaSetup[];
  note: string | null;
}

export interface GuardianAction {
  severity: 'high' | 'medium' | 'info';
  kind: string;
  ticker: string | null;
  text: string;
  suggested_stop?: number;
  source?: 'PAPER' | 'LIVE';
}

export interface UpstoxStatus {
  configured: boolean;
  connected: boolean;
  connectedAt: string | null;
  note: string;
}

export interface LiveHolding {
  ticker: string;
  quantity: number;
  avg_cost: number | null;
  last_price: number | null;
  pnl: number | null;
}

export interface GuardianReport {
  status: 'OK' | 'NO_POSITIONS';
  note?: string;
  positions?: {
    ticker: string; name: string; sector: string | null; quantity: number;
    avg_cost: number; close: number | null; stop_price: number | null;
    target_price: number | null; pnl_pct: number | null; checks: string[];
  }[];
  actions?: GuardianAction[];
  summary?: { open_positions: number; portfolio_value: number; equity: number;
              high_priority: number };
}

export interface HoldingReview {
  ticker: string;
  name: string;
  sector: string | null;
  quantity: number;
  avg_cost: number;
  source: 'LIVE' | 'PAPER';
  close: number | null;
  conviction: number | null;
  verdict?: 'HIGH' | 'NORMAL' | 'SMALL' | 'STAND_ASIDE' | 'VETOED';
  news_veto?: boolean;
  news_score?: number | null;
  trend?: 'improving' | 'deteriorating' | 'stable' | null;
  rsi?: number | null;
  action: 'ADD' | 'HOLD' | 'TRIM' | 'SELL' | 'UNKNOWN';
  rationale: string;
  pnl_pct: number | null;
  /** Proactive management: stop-loss / profit-booking prompts, and a swap idea. */
  alerts?: { kind: 'STOP' | 'PROFIT'; text: string; urgent?: boolean }[];
  replacement?: { ticker: string; name: string; sector: string | null;
                  conviction: number; same_sector: boolean } | null;
}

export interface PortfolioAlphaReview {
  status: 'OK' | 'NO_POSITIONS';
  note?: string;
  reviews?: HoldingReview[];
  summary?: { holdings: number; sell: number; trim: number; hold: number; add: number;
              alerts: number; action_needed: number };
}

/** Exness / MetaTrader 5 FX-crypto account (read-only). */
export interface FxPosition {
  ticket: number | null;
  symbol: string;
  side: 'BUY' | 'SELL';
  volume: number;
  price_open: number;
  price_current: number;
  stop_loss: number | null;
  take_profit: number | null;
  profit: number;
  swap: number;
  pnl_pct: number | null;
  comment: string | null;
}

export interface FxAccountReport {
  status: 'OK' | 'UNAVAILABLE' | 'NOT_CONNECTED' | 'ERROR';
  note?: string;
  account?: {
    login: number | null; server: string | null; currency: string | null;
    balance: number; equity: number; margin: number; margin_free: number;
    margin_level: number; profit: number; leverage: number | null;
  };
  positions?: FxPosition[];
  actions?: { severity: 'high' | 'medium' | 'info'; kind: string;
              symbol: string | null; text: string }[];
  summary?: { open_positions: number; high_priority: number;
              without_stop: number; floating_pnl: number };
}

/** Closed FX/crypto trade analysis from the MT5 deal history. */
export interface FxTradeReview {
  status: 'OK' | 'NO_TRADES' | 'UNAVAILABLE' | 'NOT_CONNECTED' | 'ERROR';
  note?: string;
  days?: number;
  stats?: {
    trades: number; wins: number; losses: number; win_rate_pct: number;
    net: number; gross_profit: number; gross_loss: number;
    profit_factor: number | null; expectancy: number;
    avg_win: number | null; avg_loss: number | null; payoff_ratio: number | null;
    swap_total: number; commission_total: number;
    avg_hold_hours_win: number | null; avg_hold_hours_loss: number | null;
    best: number; worst: number;
  };
  symbols?: { symbol: string; trades: number; net: number;
              win_rate_pct: number; volume: number }[];
  leaks?: { severity: 'high' | 'medium' | 'info'; kind: string; text: string }[];
  trades?: { position_id: number; symbol: string; side: 'BUY' | 'SELL';
             volume: number; price_open: number; price_close: number;
             profit: number; commission: number; swap: number; net: number;
             opened_at: string | null; closed_at: string | null;
             hold_hours: number | null }[];
}

export interface MorningBriefing {
  date: string;
  actions: GuardianAction[];
  summary: GuardianReport['summary'] | null;
  regime: RegimeInfo;
  signals: { strategy: string; ticker: string; signal: 'ENTRY' | 'EXIT'; close: number | null }[];
  llm_enabled: boolean;
  narrative: {
    insight?: {
      headline?: string;
      market_read?: string;
      position_plans?: { ticker: string; plan: string }[];
      opportunities?: string[];
      discipline_note?: string;
    };
    error?: string;
    cached?: boolean;
  } | null;
}

/** Adaptive conviction: has the Alpha Stack's own history validated its weights? */
export interface ConvictionCalibration {
  status: 'OK' | 'COLLECTING';
  note?: string;
  n: number;
  needed?: number;
  horizon?: string;
  date_from?: string;
  date_to?: string;
  conviction_ic?: number | null;
  layer_ic?: { layer: string; ic: number | null; n: number; t_stat?: number | null;
               significant: boolean; note?: string | null }[];
  calibration?: { band: string; n: number; avg_return: number | null;
                  median_return?: number; hit_rate: number | null }[];
  veto_audit?: { n: number; avg_return_vetoed?: number; avg_return_other?: number | null;
                 verdict?: string; note?: string };
  weights?: {
    status: 'OK' | 'INSUFFICIENT' | 'NO_SIGNAL';
    n: number; needed?: number; oos_ic?: number | null; shrinkage?: number; note?: string;
    weights?: { layer: string; current: number; learned_raw: number;
                suggested: number; delta: number; coefficient: number }[];
  };
  generated_at?: string;
}

/** One validation gate's verdict. A rejection must always name its gate. */
export interface GateVerdict {
  gate: string;
  passed: boolean;
  reason: string;
  detail?: Record<string, unknown>;
}

/** Result of fitting candidate weights and running them past every gate.
 *  A PASSED candidate is registered as SHADOW — watched, not traded. */
export interface WeightProposal {
  status: 'PASSED' | 'REJECTED';
  n: number;
  horizon?: string;
  candidate?: Record<string, number>;
  oos_ic?: number | null;
  champion_oos_ic?: number | null;
  passed?: boolean;
  failed?: string[];
  gates?: GateVerdict[];
  summary?: string;
  registered_version_id?: number;
  note?: string;
}

/** Partially-pooled weights per regime bucket. */
export interface RegimeWeights {
  status: 'OK' | 'COLLECTING' | 'INSUFFICIENT';
  n: number;
  note?: string;
  shrink_k?: number;
  horizon?: string;
  global_weights?: Record<string, number>;
  buckets?: { bucket: string; n: number; shrink: number;
              status: 'OK' | 'USING_GLOBAL';
              weights: { layer: string; weight: number; drift: number }[] }[];
}

/** What the Alpha Stack changed about itself, and what governs each regime. */
export interface AdaptationScope {
  scope: 'global' | 'risk_on' | 'neutral' | 'risk_off';
  label: string;
  weights: Record<string, number>;
  version_id: number | null;
  anchor_label: string | null;
  is_anchor: boolean;
  cooldown_days_left: number | null;
}

export interface AdaptationEvent {
  id: number;
  scope: string;
  action: 'PROMOTED' | 'REJECTED' | 'SKIPPED' | 'ROLLED_BACK';
  reason: string;
  occurred_at: string | null;
  samples: number | null;
  oos_ic: number | null;
  max_drift: number | null;
  weights: Record<string, number> | null;
  gates: { gate: string; passed: boolean; reason: string }[] | null;
  triggered_by: string;
}

export interface AdaptationHistory {
  scopes: AdaptationScope[];
  events: AdaptationEvent[];
  regime_code: string | null;
  current_scope: string;
  note?: string;
}

export interface AdaptationRun {
  status: 'OK' | 'DISABLED' | 'HALTED';
  dry_run?: boolean;
  promoted?: number;
  note?: string;
  scopes?: { scope: string; action: string; reason?: string; summary?: string;
             n?: number; max_drift?: number | null;
             candidate?: Record<string, number>; failed?: string[] }[];
}

/** One challenger replayed against the champion on identical history. */
export interface ShadowResult {
  status: 'OK' | 'NOT_FOUND' | 'UNSUPPORTED' | 'IS_CHAMPION';
  version_id: number;
  label?: string;
  version_status?: string;
  n?: number;
  champion_label?: string;
  champion_ic?: number | null;
  candidate_ic?: number | null;
  ic_gain?: number | null;
  rank_agreement?: number | null;
  candidate_weights?: Record<string, number>;
  verdict?: 'CHALLENGER_AHEAD' | 'CHAMPION_AHEAD' | 'TIE' | 'UNCLEAR'
          | 'NO_DATA' | 'INSUFFICIENT';
  note?: string;
}

export interface ShadowBoard {
  champion: { id: number; label: string } | null;
  horizon: string;
  shadows: ShadowResult[];
  promotable: number;
  note?: string;
}

/** Conditions under which the autopilot must stop opening new positions. */
export interface CircuitBreakerReport {
  halted: boolean;
  halt_reasons: string[];
  warnings: string[];
  breakers: { breaker: string; tripped: boolean; severity: 'HALT' | 'WARN' | 'OK';
              reason: string; detail?: Record<string, unknown> }[];
  summary: string;
  note?: string;
}

/** A ranked candidate list turned into a book under hard constraints. */
export interface PortfolioPlan {
  allocations: { ticker: string; symbol_id: number; conviction: number;
                 quantity: number; entry_price: number; stop: number;
                 risk_amount: number; risk_share: number;
                 sector: string | null; note: string }[];
  rejected: { ticker: string; reason: string }[];
  risk_deployed: number;
  risk_budget: number;
  risk_used_pct: number;
  sector_risk: Record<string, number>;
  positions: number;
  note: string;
}

/** Paper autopilot: the Alpha Stack trading its own signals, graded on money. */
export interface AutopilotStatus {
  enabled: boolean;
  min_conviction: number;
  max_positions: number;
  open: { ticker: string; entry_date: string; entry_price: number | null;
          quantity: number; conviction: number; stop_price: number | null }[];
  closed_count: number;
  net: number;
  by_band: { band: string; trades: number; net: number; win_rate_pct: number | null;
             avg_return_pct: number | null; expectancy?: number }[];
  generated_at?: string;
}

export interface AiUsageBucket {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  cost_inr: number;
}

export interface AiUsageSummary {
  month: AiUsageBucket;
  total: AiUsageBucket;
  by_kind: ({ kind: string } & AiUsageBucket)[];
  usd_to_inr: number;
}

export interface LeakItem {
  kind: string;
  count: number;
  severity: 'high' | 'medium' | 'low';
  text: string;
}

export interface LeaksReport {
  status: 'OK' | 'NO_TRADES';
  note?: string;
  orders?: number;
  closed_trades?: number;
  stats?: {
    total_pnl: number;
    expectancy_per_trade: number | null;
    win_rate_pct: number | null;
    avg_win: number | null;
    avg_loss: number | null;
    payoff_ratio: number | null;
  };
  by_weekday?: { day: string; trades: number; pnl: number }[];
  leaks?: LeakItem[];
  journal_coverage_pct?: number | null;
  narrative?: {
    insight?: {
      headline?: string;
      habits_working?: string[];
      habits_costing_you?: string[];
      one_change?: string;
    };
    error?: string;
    cached?: boolean;
  } | null;
}

export interface BacktestTradeRow {
  ticker: string;
  entryDate: string;
  entryPrice: number;
  exitDate: string | null;
  exitPrice: number | null;
  quantity: number;
  pnl: number | null;
  pnlPct: number | null;
  exitReason: string | null;
}

export interface BacktestDetail {
  id: number;
  strategyId: number;
  status: string;
  startedAt: string;
  finishedAt: string | null;
  params: BacktestRunParams;
  metrics: BacktestMetrics | null;
  equityCurve: { d: string; v: number }[] | null;
  error: string | null;
  trades: BacktestTradeRow[];
}

export interface SignalInfo {
  id: number;
  strategyId: number;
  strategyName: string;
  ticker: string;
  symbolName: string;
  signal: 'ENTRY' | 'EXIT';
  asOfDate: string;
  close: number | null;
  evaluatedAt: string;
}

export interface AiRiskPlan {
  ticker?: string;
  as_of_price: number;
  atr: number;
  atr_pct: number;
  regime: 'STRONG_UPTREND' | 'UPTREND' | 'NEUTRAL' | 'DOWNTREND';
  stop_price: number;
  stop_pct: number;
  atr_stop_mult: number;
  trail: boolean;
  take_profit_price: number | null;
  take_profit_pct: number | null;
  reward_risk: number | null;
  rationale: string;
}

export interface PaperPosition {
  ticker: string;
  name: string;
  quantity: number;
  avgCost: number;
  lastPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  strategyId: number | null;
  strategyName: string | null;
  stopPrice: number | null;
  targetPrice: number | null;
}

export interface PaperAccount {
  name: string;
  initialCash: number;
  cash: number;
  equity: number;
  realizedPnl: number;
  unrealizedPnl: number;
  positions: PaperPosition[];
}

export interface PaperOrder {
  id: number;
  ticker: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  price: number | null;
  priceSource: string | null;
  commission: number | null;
  realizedPnl: number | null;
  status: 'FILLED' | 'REJECTED';
  rejectReason: string | null;
  placedAt: string;
  strategyId: number | null;
  stopPrice: number | null;
  targetPrice: number | null;
}

export interface RiskSettings {
  maxPositionPct: number;
  maxSectorPct: number;
  riskPerTradePct: number;
  blockOnBreach: boolean;
}

export interface RiskExposure {
  name: string;
  value: number;
  pct: number;
}

export interface RiskReport {
  equity: number;
  cash: number;
  cashPct: number;
  positions: RiskExposure[];
  sectors: RiskExposure[];
  breaches: string[];
  maxPositionPct: number;
  maxSectorPct: number;
}

export interface PositionSizeResult {
  quantity: number;
  riskAmount: number;
  perShareRisk: number;
  positionValue: number;
  cappedByPositionLimit: boolean;
}

export interface AlertInfo {
  id: number;
  ticker: string;
  field: string;
  op: string;
  value: number;
  note: string | null;
  status: 'ACTIVE' | 'TRIGGERED' | 'DISABLED';
  createdAt: string;
  triggeredAt: string | null;
  triggeredValue: number | null;
}

export interface JournalEntry {
  id: number;
  ticker: string | null;
  paperOrderId: number | null;
  title: string;
  body: string;
  tags: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AiPredictionRow {
  ticker: string;
  name: string;
  asOfDate: string;
  predictedReturnPct: number;
  direction: 'UP' | 'DOWN' | 'FLAT';
  testDirectionAccuracy: number | null;
  testMaePct: number | null;
  trainRows: number | null;
  modelName: string | null;
  trainedAt: string;
}

export interface StrategyScore {
  strategyId: number;
  name: string;
  liveTrades: number;
  liveWins: number;
  liveWinRatePct: number | null;
  livePnl: number;
  backtestWinRatePct: number | null;
  backtestTotalReturnPct: number | null;
  verdict: 'ON_TRACK' | 'DECAYING' | 'NO_BACKTEST' | 'NOT_ENOUGH_DATA';
}

export interface TradeIdea {
  ticker: string;
  name: string;
  score: number;
  reasons: string[];
  close: number | null;
  as_of_date: string | null;
  entry_strategies: string[];
  risk_plan: AiRiskPlan | null;
}

export interface TradeIdeasResponse {
  ideas: TradeIdea[];
  symbols_scanned: number;
  disclaimer: string;
}

export interface Quote {
  ticker: string;
  yahoo_symbol: string;
  price: number;
  prev_close: number | null;
  change: number | null;
  change_pct: number | null;
  as_of: string;
}

// ---- news & AI insights ----------------------------------------------------

export interface NewsArticle {
  title: string;
  publisher: string | null;
  link: string | null;
  published_at: string | null;
}

export interface NewsCatalyst {
  type: string;
  direction: 'positive' | 'negative' | 'neutral';
}

export interface NewsInsight {
  summary?: string;
  sentiment?: 'positive' | 'negative' | 'neutral' | 'mixed';
  key_points?: string[];
  watch_for?: string[];
  catalysts?: NewsCatalyst[];
  error?: string;
}

export interface NewsResponse {
  ticker: string;
  fetched_new: number;
  /** Why the Yahoo fetch produced nothing, when it did — shown instead of an
   *  unexplained empty feed. */
  fetch_error?: string | null;
  llm_enabled: boolean;
  articles: NewsArticle[];
  insight: { insight: NewsInsight; generated_at: string | null; cached: boolean }
    | NewsInsight | null;
}

export interface FundamentalsInsight {
  headline?: string;
  verdict?: 'strong' | 'good' | 'mixed' | 'weak';
  summary?: string;
  strengths?: string[];
  concerns?: string[];
  metrics_explained?: { metric: string; value: string; meaning: string }[];
  error?: string;
}

export interface InsightResponse {
  ticker: string;
  llm_enabled: boolean;
  insight: { insight: FundamentalsInsight; generated_at: string | null; cached: boolean }
    | FundamentalsInsight | null;
}
