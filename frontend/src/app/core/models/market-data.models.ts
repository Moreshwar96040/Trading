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
  timeframe?: 'daily' | 'weekly' | 'monthly';
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

export interface NewsInsight {
  summary?: string;
  sentiment?: 'positive' | 'negative' | 'neutral' | 'mixed';
  key_points?: string[];
  watch_for?: string[];
  error?: string;
}

export interface NewsResponse {
  ticker: string;
  fetched_new: number;
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
