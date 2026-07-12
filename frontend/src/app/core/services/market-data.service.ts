import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  AiPredictionRow, AiRiskPlan, AlertInfo, BacktestDetail, BacktestRunParams, CandleSeries,
  FundamentalsData, IndicatorSeries, JournalEntry, PaperAccount, PaperOrder,
  PositionSizeResult, Quote, RiskReport, RiskSettings, ScreenRequest, ScreenRow,
  ScreenerFieldsMeta, SignalInfo, StrategyDefinition, StrategyInfo, StrategyScore,
  SymbolInfo, TradeIdeasResponse,
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

  triggerDailySync(tickers: string[] = []): Observable<unknown> {
    return this.http.post(`${this.base}/sync/daily`, { tickers });
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
}
