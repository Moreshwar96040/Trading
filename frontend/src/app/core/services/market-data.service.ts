import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { shareReplay } from 'rxjs/operators';

import { environment } from '../../../environments/environment';
import {
  AiPredictionRow, AiRiskPlan, AiUsageSummary, AlertInfo, AlphaStack, BacktestDetail,
  BacktestRunParams, CandleSeries,
  DataHealth, EdgeGatesReport,
  FundamentalsData, GuardianReport, IndicatorSeries, InsightResponse, JournalEntry,
  LeaksReport, LiveHolding, MarketNewsResponse, MomentumBoard, MorningBriefing,
  NewsRefreshResult, NewsResponse, PaperAccount, PaperOrder, RegimeInfo,
  PositionSizeResult, Quote, RiskReport, RiskSettings, ScreenRequest, ScreenRow,
  ScreenerFieldsMeta, SignalInfo, StrategyDefinition, StrategyInfo, StrategyScore,
  SymbolInfo, SymbolLookupResult, TradeIdeasResponse, UpstoxStatus,
} from '../models/market-data.models';

/** Single gateway to the backend API — components never build URLs themselves. */
@Injectable({ providedIn: 'root' })
export class MarketDataService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBase;

  searchSymbols(query: string): Observable<SymbolInfo[]> {
    const params = query ? new HttpParams().set('query', query) : new HttpParams();
    return this.http.get<SymbolInfo[]>(`${this.base}/symbols`, { params });
  }

  seedSymbol(ticker: string): Observable<SymbolInfo> {
    return this.http.post<SymbolInfo>(`${this.base}/symbols/seed`, { ticker });
  }

  getCandles(ticker: string, from?: string, to?: string): Observable<CandleSeries> {
    let params = new HttpParams();
    if (from) params = params.set('from', from);
    if (to) params = params.set('to', to);
    return this.http.get<CandleSeries>(`${this.base}/symbols/${ticker}/candles`, { params });
  }

  getQuote(ticker: string): Observable<Quote> {
    return this.http.get<Quote>(`${this.base}/quotes/${ticker}`);
  }

  runScreen(request: ScreenRequest): Observable<ScreenRow[]> {
    return this.http.post<ScreenRow[]>(`${this.base}/screener/run`, request);
  }

  getScreenerFields(): Observable<ScreenerFieldsMeta> {
    return this.http.get<ScreenerFieldsMeta>(`${this.base}/screener/fields`);
  }

  getIndicators(ticker: string, from?: string, to?: string): Observable<IndicatorSeries> {
    let params = new HttpParams();
    if (from) params = params.set('from', from);
    if (to) params = params.set('to', to);
    return this.http.get<IndicatorSeries>(`${this.base}/indicators/${ticker}`, { params });
  }

  /** @param from optional ISO date — backfill history at least back to this date. */
  triggerDailySync(tickers: string[] = [], from?: string): Observable<unknown> {
    return this.http.post(`${this.base}/sync/daily`, from ? { tickers, from } : { tickers });
  }

  triggerIntradaySync(tickers: string[] = [], interval = '15m'): Observable<unknown> {
    return this.http.post(`${this.base}/sync/intraday`, { tickers, interval });
  }

  triggerCsvImport(): Observable<unknown> {
    return this.http.post(`${this.base}/sync/csv-import`, {});
  }

  triggerSnapshotRefresh(): Observable<unknown> {
    return this.http.post(`${this.base}/sync/snapshot`, {});
  }

  // ---- strategies & backtests -------------------------------------------
  listStrategies(): Observable<StrategyInfo[]> {
    return this.http.get<StrategyInfo[]>(`${this.base}/strategies`);
  }

  createStrategy(name: string, description: string | null,
                 definition: StrategyDefinition): Observable<StrategyInfo> {
    return this.http.post<StrategyInfo>(`${this.base}/strategies`, { name, description, definition });
  }

  updateStrategy(id: number, name: string, description: string | null,
                 definition: StrategyDefinition): Observable<StrategyInfo> {
    return this.http.put<StrategyInfo>(`${this.base}/strategies/${id}`, { name, description, definition });
  }

  deleteStrategy(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/strategies/${id}`);
  }

  getScoreboard(): Observable<StrategyScore[]> {
    return this.http.get<StrategyScore[]>(`${this.base}/strategies/scoreboard`);
  }

  runBacktest(strategyId: number, params: BacktestRunParams): Observable<{ backtest_id: number }> {
    return this.http.post<{ backtest_id: number }>(
      `${this.base}/strategies/${strategyId}/backtests`, params);
  }

  getBacktest(id: number): Observable<BacktestDetail> {
    return this.http.get<BacktestDetail>(`${this.base}/backtests/${id}`);
  }

  // ---- live strategy signals ----------------------------------------------
  listSignals(): Observable<SignalInfo[]> {
    return this.http.get<SignalInfo[]>(`${this.base}/signals`);
  }

  evaluateSignals(): Observable<{ signals: number }> {
    return this.http.post<{ signals: number }>(`${this.base}/signals/evaluate`, {});
  }

  // ---- paper trading ------------------------------------------------------
  getPaperAccount(): Observable<PaperAccount> {
    return this.http.get<PaperAccount>(`${this.base}/paper/account`);
  }

  placePaperOrder(ticker: string, side: 'BUY' | 'SELL', quantity: number,
                  riskPlan?: { strategyId?: number | null; stopPrice?: number | null;
                               targetPrice?: number | null; }): Observable<PaperOrder> {
    return this.http.post<PaperOrder>(`${this.base}/paper/orders`,
      { ticker, side, quantity, ...riskPlan });
  }

  getAiIdeas(limit = 10): Observable<TradeIdeasResponse> {
    return this.http.get<TradeIdeasResponse>(`${this.base}/ai/ideas`,
      { params: new HttpParams().set('limit', limit) });
  }

  getAiRisk(ticker: string, entryPrice?: number): Observable<AiRiskPlan> {
    const params = entryPrice ? new HttpParams().set('entryPrice', entryPrice) : new HttpParams();
    return this.http.get<AiRiskPlan>(`${this.base}/ai/risk/${ticker}`, { params });
  }

  listPaperOrders(): Observable<PaperOrder[]> {
    return this.http.get<PaperOrder[]>(`${this.base}/paper/orders`);
  }

  managePositions(autoExit: boolean): Observable<{
    positionsChecked: number; autoExit: boolean;
    actions: { ticker: string; action: string; detail: string }[];
  }> {
    return this.http.post<never>(`${this.base}/paper/manage`, { autoExit });
  }

  resetPaperAccount(initialCash?: number): Observable<PaperAccount> {
    return this.http.post<PaperAccount>(`${this.base}/paper/account/reset`,
      initialCash ? { initialCash } : {});
  }

  // ---- risk & alerts ------------------------------------------------------
  getRiskSettings(): Observable<RiskSettings> {
    return this.http.get<RiskSettings>(`${this.base}/risk/settings`);
  }

  updateRiskSettings(settings: RiskSettings): Observable<RiskSettings> {
    return this.http.put<RiskSettings>(`${this.base}/risk/settings`, settings);
  }

  getRiskReport(): Observable<RiskReport> {
    return this.http.get<RiskReport>(`${this.base}/risk/report`);
  }

  calcPositionSize(entryPrice: number, stopPrice: number,
                   equityOverride?: number): Observable<PositionSizeResult> {
    return this.http.post<PositionSizeResult>(`${this.base}/risk/position-size`,
      { entryPrice, stopPrice, equityOverride: equityOverride ?? null });
  }

  listAlerts(): Observable<AlertInfo[]> {
    return this.http.get<AlertInfo[]>(`${this.base}/alerts`);
  }

  createAlert(ticker: string, field: string, op: string, value: number,
              note?: string): Observable<AlertInfo> {
    return this.http.post<AlertInfo>(`${this.base}/alerts`, { ticker, field, op, value, note });
  }

  rearmAlert(id: number): Observable<AlertInfo> {
    return this.http.post<AlertInfo>(`${this.base}/alerts/${id}/rearm`, {});
  }

  deleteAlert(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/alerts/${id}`);
  }

  evaluateAlerts(): Observable<{ checked: number; triggered: number }> {
    return this.http.post<{ checked: number; triggered: number }>(`${this.base}/alerts/evaluate`, {});
  }

  // ---- journal & AI -------------------------------------------------------
  listJournal(ticker?: string): Observable<JournalEntry[]> {
    const params = ticker ? new HttpParams().set('ticker', ticker) : new HttpParams();
    return this.http.get<JournalEntry[]>(`${this.base}/journal`, { params });
  }

  createJournalEntry(entry: { ticker?: string | null; paperOrderId?: number | null;
                              title: string; body: string; tags?: string | null; }):
      Observable<JournalEntry> {
    return this.http.post<JournalEntry>(`${this.base}/journal`, entry);
  }

  updateJournalEntry(id: number, entry: { ticker?: string | null; title: string;
                                          body: string; tags?: string | null; }):
      Observable<JournalEntry> {
    return this.http.put<JournalEntry>(`${this.base}/journal/${id}`, entry);
  }

  deleteJournalEntry(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/journal/${id}`);
  }

  listAiPredictions(): Observable<AiPredictionRow[]> {
    return this.http.get<AiPredictionRow[]>(`${this.base}/ai/predictions`);
  }

  trainAi(tickers: string[] = []): Observable<{ status: string; trained: number }> {
    return this.http.post<{ status: string; trained: number }>(`${this.base}/ai/train`, { tickers });
  }

  getFundamentals(ticker: string): Observable<FundamentalsData> {
    return this.http.get<FundamentalsData>(`${this.base}/fundamentals/${ticker}`);
  }

  triggerFundamentalsRefresh(tickers: string[] = []): Observable<unknown> {
    return this.http.post(`${this.base}/sync/fundamentals`, { tickers });
  }

  getNews(ticker: string, refresh = false): Observable<NewsResponse> {
    return this.http.get<NewsResponse>(`${this.base}/news/${ticker}`,
                                       { params: { refresh } });
  }

  getFundamentalsInsights(ticker: string): Observable<InsightResponse> {
    return this.http.get<InsightResponse>(`${this.base}/fundamentals/${ticker}/insights`);
  }

  // Regime is fetched by several components per page (banner, briefing, trade
  // dialog) — share one request and cache it for 60s instead of refetching.
  private regimeCache$: Observable<RegimeInfo> | null = null;
  private regimeCacheAt = 0;

  getRegime(): Observable<RegimeInfo> {
    const now = Date.now();
    if (!this.regimeCache$ || now - this.regimeCacheAt > 60_000) {
      this.regimeCacheAt = now;
      this.regimeCache$ = this.http.get<RegimeInfo>(`${this.base}/regime`)
        .pipe(shareReplay({ bufferSize: 1, refCount: false }));
    }
    return this.regimeCache$;
  }

  getLeaksReport(): Observable<LeaksReport> {
    return this.http.get<LeaksReport>(`${this.base}/review/leaks`);
  }

  getAiUsage(): Observable<AiUsageSummary> {
    return this.http.get<AiUsageSummary>(`${this.base}/ai/usage`);
  }

  getMarketNews(refresh = false): Observable<MarketNewsResponse> {
    return this.http.get<MarketNewsResponse>(`${this.base}/news/market`,
                                             { params: { refresh } });
  }

  /** Re-pull market feeds, regenerate the macro digest and refresh per-stock
   *  news for signaled/held symbols (fixes a stale/absent macro layer). */
  refreshAllNews(): Observable<NewsRefreshResult> {
    return this.http.post<NewsRefreshResult>(`${this.base}/news/refresh`, {});
  }

  getDataHealth(): Observable<DataHealth> {
    return this.http.get<DataHealth>(`${this.base}/data/health`);
  }

  getEdgeGates(): Observable<EdgeGatesReport> {
    return this.http.get<EdgeGatesReport>(`${this.base}/edge/gates`);
  }

  getMomentumBoard(): Observable<MomentumBoard> {
    return this.http.get<MomentumBoard>(`${this.base}/momentum/board`);
  }

  lookupSymbols(query: string): Observable<{ results: SymbolLookupResult[] }> {
    return this.http.get<{ results: SymbolLookupResult[] }>(
      `${this.base}/symbols/lookup`, { params: new HttpParams().set('q', query) });
  }

  getAlphaStack(ticker?: string): Observable<AlphaStack> {
    const params = ticker ? new HttpParams().set('ticker', ticker) : new HttpParams();
    return this.http.get<AlphaStack>(`${this.base}/alpha/stack`, { params });
  }

  getPortfolioHealth(): Observable<GuardianReport> {
    return this.http.get<GuardianReport>(`${this.base}/portfolio/health`);
  }

  getBriefing(force = false): Observable<MorningBriefing> {
    return this.http.get<MorningBriefing>(`${this.base}/briefing`, { params: { force } });
  }

  // ---- Upstox (read-only) -------------------------------------------------
  getUpstoxStatus(): Observable<UpstoxStatus> {
    return this.http.get<UpstoxStatus>(`${this.base}/upstox/status`);
  }

  getUpstoxLoginUrl(): Observable<{ url: string }> {
    return this.http.get<{ url: string }>(`${this.base}/upstox/login-url`);
  }

  getUpstoxHoldings(): Observable<LiveHolding[]> {
    return this.http.get<LiveHolding[]>(`${this.base}/upstox/holdings`);
  }

  disconnectUpstox(): Observable<UpstoxStatus> {
    return this.http.post<UpstoxStatus>(`${this.base}/upstox/disconnect`, {});
  }

  updatePositionStop(ticker: string, stopPrice: number):
      Observable<{ ticker: string; oldStop: number | null; newStop: number }> {
    return this.http.post<{ ticker: string; oldStop: number | null; newStop: number }>(
      `${this.base}/paper/positions/${ticker}/stop`, { stopPrice });
  }
}
