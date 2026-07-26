import { CommonModule } from '@angular/common';
import { Component, ElementRef, OnInit, ViewChild, computed, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatAutocompleteModule, MatAutocompleteSelectedEvent } from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { debounceTime, distinctUntilChanged, filter, switchMap } from 'rxjs';
import { toSignal } from '@angular/core/rxjs-interop';

import {
  FundamentalsData, FundamentalsInsight, NewsArticle, NewsInsight, StatementRow, SymbolInfo,
} from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

interface RatioCard {
  label: string;
  value: string;
  hint?: string;
}

const CRORE = 1e7;

@Component({
  selector: 'app-fundamentals-page',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, MatFormFieldModule, MatInputModule,
            MatAutocompleteModule, MatCardModule, MatButtonModule, MatIconModule,
            MatProgressSpinnerModule, MatSnackBarModule, MatTableModule,
            MatButtonToggleModule, MatTooltipModule, RouterLink],
  template: `
    <div class="controls">
      <mat-form-field appearance="outline" class="search">
        <mat-label>Search symbol</mat-label>
        <input matInput placeholder="e.g. TCS" [formControl]="searchControl"
               [matAutocomplete]="auto">
        <mat-icon matSuffix>search</mat-icon>
        <mat-autocomplete #auto="matAutocomplete" (optionSelected)="onSymbolSelected($event)">
          @for (s of suggestions(); track s.id) {
            <mat-option [value]="s.ticker">
              <span class="ticker">{{ s.ticker }}</span>
              <span class="name">{{ s.name }} · {{ s.sector }}</span>
            </mat-option>
          }
        </mat-autocomplete>
      </mat-form-field>

      @if (data(); as d) {
        <a mat-stroked-button [routerLink]="['/chart']" [queryParams]="{ ticker: d.ticker }">
          <mat-icon>show_chart</mat-icon> Chart
        </a>
        <button mat-stroked-button (click)="refresh()" [disabled]="refreshing()">
          <mat-icon>cloud_download</mat-icon>
          {{ refreshing() ? 'Fetching from Yahoo…' : 'Refresh fundamentals' }}
        </button>
      }
    </div>

    @if (loading()) {
      <div class="spinner"><mat-spinner diameter="36" /></div>
    }

    @if (data(); as d) {
      <h2>{{ d.name }} <span class="sector-tag">{{ d.sector }}</span></h2>

      <!-- ======= overall news sentiment, in short =======
           Always rendered: an absent digest is a state to explain, not to hide. -->
      @if (newsLoading()) {
        <div class="sentiment-strip loading">
          <mat-spinner diameter="16" /> Reading the news for {{ d.ticker }}…
        </div>
      } @else {
        <!-- The "as" alias binds only on a primary @if, so the digest check
             nests here rather than riding on an @else if. -->
        @if (newsInsight(); as ni) {
          <div class="sentiment-strip" (click)="scrollToNews()"
               matTooltip="Jump to the full news digest">
            <mat-icon>newspaper</mat-icon>
            @if (ni.sentiment) {
              <span class="verdict" [class]="'verdict sentiment-' + ni.sentiment">{{ ni.sentiment }}</span>
            }
            <span class="sentiment-line">{{ shortSentiment(ni) }}</span>
          </div>
        } @else {
          <div class="sentiment-strip empty">
            <mat-icon>newspaper</mat-icon>
            <span class="sentiment-line">{{ noSentimentReason() }}</span>
            @if (news().length || newsFetchError()) {
              <button mat-stroked-button class="strip-action" (click)="refreshNews()">
                <mat-icon>refresh</mat-icon> Retry
              </button>
            } @else {
              <button mat-flat-button class="strip-action" (click)="refreshNews()">
                <mat-icon>cloud_download</mat-icon> Fetch news
              </button>
            }
          </div>
        }
      }

      @if (d.ratios; as r) {
        <div class="cards">
          @for (card of ratioCards(); track card.label) {
            <mat-card appearance="outlined" class="ratio-card">
              <span class="ratio-value">{{ card.value }}</span>
              <span class="ratio-label">{{ card.label }}</span>
            </mat-card>
          }
        </div>
        <p class="asof">Ratios as of {{ r.computedAt | date: 'medium' }} (Yahoo Finance)</p>

        <!-- ============ AI insight: what the numbers mean ============ -->
        @if (insight(); as ins) {
          <mat-card appearance="outlined" class="insight-card">
            <div class="insight-header">
              <mat-icon>auto_awesome</mat-icon>
              <h3>What these numbers mean</h3>
              @if (ins.verdict) {
                <span class="verdict" [class]="'verdict verdict-' + ins.verdict">{{ ins.verdict }}</span>
              }
            </div>
            @if (ins.headline) { <p class="insight-headline">{{ ins.headline }}</p> }
            @if (ins.summary) { <p class="insight-summary">{{ ins.summary }}</p> }
            <div class="pro-con">
              @if (ins.strengths?.length) {
                <div>
                  <h4 class="good">Strengths</h4>
                  <ul>@for (s of ins.strengths; track s) { <li>{{ s }}</li> }</ul>
                </div>
              }
              @if (ins.concerns?.length) {
                <div>
                  <h4 class="bad">Concerns</h4>
                  <ul>@for (c of ins.concerns; track c) { <li>{{ c }}</li> }</ul>
                </div>
              }
            </div>
            @if (ins.metrics_explained?.length) {
              <table class="metric-table">
                @for (m of ins.metrics_explained; track m.metric) {
                  <tr>
                    <td class="metric-name">{{ m.metric }}</td>
                    <td class="metric-value">{{ m.value }}</td>
                    <td class="metric-meaning">{{ m.meaning }}</td>
                  </tr>
                }
              </table>
            }
            <p class="disclaimer">AI-generated explanation for education, not investment advice.</p>
          </mat-card>
        } @else if (insightLoading()) {
          <mat-card appearance="outlined" class="insight-card">
            <div class="insight-loading"><mat-spinner diameter="22" /> Reading the numbers…</div>
          </mat-card>
        } @else if (llmDisabled()) {
          <p class="asof">Set ANTHROPIC_API_KEY in .env to get plain-language AI explanations
            of these numbers.</p>
        }
      } @else {
        <mat-card appearance="outlined" class="empty-card">
          <p>No fundamentals stored yet for {{ d.ticker }}.</p>
          <button mat-flat-button color="primary" (click)="refresh()" [disabled]="refreshing()">
            {{ refreshing() ? 'Fetching…' : 'Fetch now' }}
          </button>
        </mat-card>
      }

      @if (d.annual.length || d.quarterly.length) {
        <div class="stmt-header">
          <h3>Financial statements <span class="crore-hint">(₹ crore)</span></h3>
          <mat-button-toggle-group [value]="periodType()" (change)="periodType.set($event.value)">
            <mat-button-toggle value="annual">Annual</mat-button-toggle>
            <mat-button-toggle value="quarterly">Quarterly</mat-button-toggle>
          </mat-button-toggle-group>
        </div>

        <table mat-table [dataSource]="statements()" class="stmt-table">
          <ng-container matColumnDef="periodEnd">
            <th mat-header-cell *matHeaderCellDef>Period</th>
            <td mat-cell *matCellDef="let s">{{ s.periodEnd | date: 'MMM yyyy' }}</td>
          </ng-container>
          @for (col of stmtCols; track col.key) {
            <ng-container [matColumnDef]="col.key">
              <th mat-header-cell *matHeaderCellDef>{{ col.label }}</th>
              <td mat-cell *matCellDef="let s"
                  [class.down]="col.signed && s[col.key] < 0">
                {{ toCrore(s[col.key]) }}
              </td>
            </ng-container>
          }
          <tr mat-header-row *matHeaderRowDef="stmtColumnKeys"></tr>
          <tr mat-row *matRowDef="let s; columns: stmtColumnKeys"></tr>
        </table>
      } @else if (d.ratios) {
        <div class="stmt-header">
          <h3>Financial statements</h3>
        </div>
        <p class="hint">No statements stored for {{ d.ticker }} — Yahoo sometimes
          returns none on the first pull. Hit "Refresh fundamentals" above to retry;
          if it stays empty, Yahoo has no statement data for this listing.</p>
      }

      <!-- ============ news & AI digest ============ -->
      <div class="stmt-header news-header" #newsSection>
        <h3>Latest news</h3>
        <button mat-stroked-button (click)="refreshNews()" [disabled]="newsLoading()">
          <mat-icon>refresh</mat-icon>
          {{ newsLoading() ? 'Fetching…' : 'Refresh news' }}
        </button>
      </div>
      @if (newsInsight(); as ni) {
        <mat-card appearance="outlined" class="insight-card">
          <div class="insight-header">
            <mat-icon>auto_awesome</mat-icon>
            <h3>News digest</h3>
            @if (ni.sentiment) {
              <span class="verdict" [class]="'verdict sentiment-' + ni.sentiment">{{ ni.sentiment }}</span>
            }
          </div>
          @if (ni.summary) { <p class="insight-summary">{{ ni.summary }}</p> }
          @if (ni.key_points?.length) {
            <ul>@for (p of ni.key_points; track p) { <li>{{ p }}</li> }</ul>
          }
          @if (ni.catalysts?.length) {
            <div class="catalysts">
              @for (c of ni.catalysts; track c.type) {
                <span class="catalyst" [class]="'catalyst catalyst-' + c.direction">
                  {{ c.type.replace('_', ' ') }}
                </span>
              }
            </div>
          }
          @if (ni.watch_for?.length) {
            <p class="watch-for"><strong>Watch for:</strong> {{ ni.watch_for!.join(' · ') }}</p>
          }
        </mat-card>
      }
      @if (news().length) {
        <div class="news-list">
          @for (a of news(); track a.title) {
            <a class="news-item" [href]="a.link" target="_blank" rel="noopener">
              <span class="news-title">{{ a.title }}</span>
              <span class="news-meta">{{ a.publisher }} · {{ a.published_at | date: 'MMM d, y' }}</span>
            </a>
          }
        </div>
      } @else if (!newsLoading()) {
        @if (newsFetchError(); as err) {
          <p class="hint fetch-error"><mat-icon>error_outline</mat-icon>
            News fetch from Yahoo failed: {{ err }}</p>
        } @else {
          <p class="hint">No stored news yet — hit "Refresh news".</p>
        }
      }
    } @else if (!loading()) {
      <p class="hint">Search for a symbol to see its fundamentals.</p>
    }
  `,
  styles: `
    .controls { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
    .search { min-width: 320px; }
    .ticker { font-weight: 600; margin-right: 8px; }
    .name { opacity: 0.6; font-size: 12px; }
    h2 { font-weight: 500; margin: 8px 0 16px; }
    .sector-tag { font-size: 13px; opacity: 0.6; font-weight: 400; margin-left: 8px; }
    .sentiment-strip { display: flex; align-items: center; gap: 10px; cursor: pointer;
                       padding: 8px 12px; margin: 0 0 16px; border-radius: 10px;
                       border: 1px solid rgba(128,128,128,0.18); }
    .sentiment-strip:hover { background: rgba(128,128,128,0.06); }
    .sentiment-strip.loading { cursor: default; opacity: 0.7; font-size: 13px; }
    .sentiment-strip.empty { cursor: default; }
    .sentiment-strip.empty:hover { background: none; }
    .strip-action { margin-left: auto; flex-shrink: 0; }
    .sentiment-strip mat-icon { font-size: 18px; width: 18px; height: 18px; opacity: 0.7; }
    .sentiment-line { font-size: 13.5px; line-height: 1.4; }
    .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
             gap: 12px; }
    .ratio-card { padding: 14px; display: flex; flex-direction: column; gap: 4px; }
    .ratio-value { font-size: 20px; font-weight: 600; }
    .ratio-label { font-size: 12px; opacity: 0.65; }
    .asof { font-size: 12px; opacity: 0.5; margin: 10px 0 20px; }
    .empty-card { padding: 20px; display: flex; gap: 16px; align-items: center; }
    .stmt-header { display: flex; align-items: center; gap: 16px; margin-top: 8px; }
    .crore-hint { font-size: 12px; opacity: 0.6; font-weight: 400; }
    .stmt-table { width: 100%; margin-top: 8px; }
    .down { color: #ef5350; }
    .spinner { display: flex; justify-content: center; padding: 24px; }
    .hint { opacity: 0.6; margin-top: 16px; }
    .fetch-error { display: flex; align-items: center; gap: 6px; color: #ef5350;
                   opacity: 0.9; font-size: 13px; }
    .fetch-error mat-icon { font-size: 17px; width: 17px; height: 17px; }
    .insight-card { padding: 16px 20px; margin: 16px 0; }
    .insight-loading { display: flex; align-items: center; gap: 12px; opacity: 0.7; }
    .insight-header { display: flex; align-items: center; gap: 8px; }
    .insight-header h3 { margin: 0; font-weight: 500; }
    .insight-headline { font-weight: 500; margin: 10px 0 4px; }
    .insight-summary { margin: 8px 0; line-height: 1.5; }
    .verdict { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
               padding: 3px 10px; border-radius: 12px; font-weight: 600; }
    .verdict-strong, .sentiment-positive { background: #1b5e2033; color: #66bb6a; }
    .verdict-good { background: #33691e33; color: #9ccc65; }
    .verdict-mixed, .sentiment-mixed, .sentiment-neutral { background: #f57f1733; color: #ffb74d; }
    .verdict-weak, .sentiment-negative { background: #b71f1f33; color: #ef5350; }
    .pro-con { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
               gap: 0 24px; }
    .pro-con h4 { margin: 8px 0 2px; font-weight: 600; font-size: 13px; }
    .pro-con h4.good { color: #66bb6a; }
    .pro-con h4.bad { color: #ef5350; }
    .pro-con ul, .insight-card ul { margin: 4px 0; padding-left: 20px; }
    .pro-con li, .insight-card li { margin: 3px 0; line-height: 1.4; }
    .metric-table { margin-top: 12px; border-collapse: collapse; width: 100%; }
    .metric-table td { padding: 6px 12px 6px 0; vertical-align: top; font-size: 13px; }
    .metric-name { font-weight: 600; white-space: nowrap; }
    .metric-value { white-space: nowrap; opacity: 0.9; }
    .metric-meaning { opacity: 0.75; line-height: 1.4; }
    .disclaimer { font-size: 11px; opacity: 0.45; margin: 12px 0 0; }
    .watch-for { font-size: 13px; opacity: 0.85; }
    .catalysts { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
    .catalyst { font-size: 11px; text-transform: capitalize; padding: 2px 8px;
      border-radius: 10px; background: #ffffff14; }
    .catalyst-positive { background: #1b5e2033; color: #66bb6a; }
    .catalyst-negative { background: #b71f1f33; color: #ef5350; }
    .catalyst-neutral { background: #f57f1733; color: #ffb74d; }
    .news-header { margin-top: 24px; }
    .news-list { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }
    .news-item { display: flex; flex-direction: column; padding: 10px 12px; border-radius: 8px;
                 text-decoration: none; color: inherit; }
    .news-item:hover { background: rgba(128, 128, 128, 0.08); }
    .news-title { line-height: 1.4; }
    .news-meta { font-size: 12px; opacity: 0.55; margin-top: 2px; }
  `,
})
export class FundamentalsPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);

  @ViewChild('newsSection') newsSection?: ElementRef<HTMLElement>;

  readonly searchControl = new FormControl('', { nonNullable: true });
  readonly data = signal<FundamentalsData | null>(null);
  readonly loading = signal(false);
  readonly refreshing = signal(false);
  readonly periodType = signal<'annual' | 'quarterly'>('annual');

  readonly insight = signal<FundamentalsInsight | null>(null);
  readonly insightLoading = signal(false);
  readonly llmDisabled = signal(false);
  readonly news = signal<NewsArticle[]>([]);
  readonly newsInsight = signal<NewsInsight | null>(null);
  readonly newsLoading = signal(false);
  readonly newsFetchError = signal<string | null>(null);
  readonly newsLlmEnabled = signal(true);
  readonly newsInsightError = signal<string | null>(null);

  readonly stmtCols = [
    { key: 'revenue', label: 'Revenue', signed: false },
    { key: 'operatingIncome', label: 'Op. income', signed: true },
    { key: 'netIncome', label: 'Net income', signed: true },
    { key: 'eps', label: 'EPS (₹)', signed: true },
    { key: 'totalAssets', label: 'Assets', signed: false },
    { key: 'shareholdersEquity', label: 'Equity', signed: false },
    { key: 'operatingCashFlow', label: 'Op. CF', signed: true },
    { key: 'freeCashFlow', label: 'FCF', signed: true },
  ] as const;
  readonly stmtColumnKeys = ['periodEnd', ...this.stmtCols.map((c) => c.key)];

  readonly statements = computed<StatementRow[]>(() => {
    const d = this.data();
    if (!d) return [];
    return this.periodType() === 'annual' ? d.annual : d.quarterly;
  });

  readonly ratioCards = computed<RatioCard[]>(() => {
    const r = this.data()?.ratios;
    if (!r) return [];
    const n = (v: number | null, digits = 2, suffix = '') =>
      v === null || v === undefined ? '—' : `${v.toFixed(digits)}${suffix}`;
    const cap = r.marketCap === null ? '—' : `₹${(r.marketCap / CRORE).toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr`;
    return [
      { label: 'Market cap', value: cap },
      { label: 'P/E (trailing)', value: n(r.peTrailing) },
      { label: 'P/E (forward)', value: n(r.peForward) },
      { label: 'P/B', value: n(r.pb) },
      { label: 'P/S', value: n(r.ps) },
      { label: 'Dividend yield', value: n(r.dividendYieldPct, 2, '%') },
      { label: 'ROE', value: n(r.roePct, 1, '%') },
      { label: 'Debt / Equity', value: n(r.debtToEquity) },
      { label: 'Profit margin', value: n(r.profitMarginPct, 1, '%') },
      { label: 'Operating margin', value: n(r.operatingMarginPct, 1, '%') },
      { label: 'Revenue growth', value: n(r.revenueGrowthPct, 1, '%') },
      { label: 'Earnings growth', value: n(r.earningsGrowthPct, 1, '%') },
      { label: 'EPS (trailing)', value: n(r.epsTrailing, 2, ' ₹') },
      { label: 'Book value', value: n(r.bookValue, 0, ' ₹') },
      { label: 'Beta', value: n(r.beta) },
    ];
  });

  readonly suggestions = toSignal(
    this.searchControl.valueChanges.pipe(
      debounceTime(250),
      distinctUntilChanged(),
      filter((q) => q.length >= 1),
      switchMap((q) => this.api.searchSymbols(q)),
    ),
    { initialValue: [] as SymbolInfo[] },
  );

  ngOnInit(): void {
    const ticker = this.route.snapshot.queryParamMap.get('ticker');
    if (ticker) {
      this.searchControl.setValue(ticker, { emitEvent: false });
      this.load(ticker.toUpperCase());
    }
  }

  onSymbolSelected(event: MatAutocompleteSelectedEvent): void {
    const ticker = event.option.value as string;
    this.router.navigate([], { queryParams: { ticker }, queryParamsHandling: 'merge' });
    this.load(ticker);
  }

  refresh(): void {
    const ticker = this.data()?.ticker;
    if (!ticker) return;
    this.refreshing.set(true);
    this.api.triggerFundamentalsRefresh([ticker]).subscribe({
      next: () => { this.refreshing.set(false); this.load(ticker); },
      error: () => {
        this.refreshing.set(false);
        this.snackBar.open('Fundamentals refresh failed (Yahoo reachable?)', 'Dismiss', { duration: 5000 });
      },
    });
  }

  toCrore(value: number | null): string {
    if (value === null || value === undefined) return '—';
    if (Math.abs(value) < 1000) return value.toFixed(2);   // per-share figures like EPS
    return (value / CRORE).toLocaleString('en-IN', { maximumFractionDigits: 0 });
  }

  refreshNews(): void {
    const ticker = this.data()?.ticker;
    if (ticker) this.loadNews(ticker, true);
  }

  /** Why there's no sentiment line — each case has a different fix, so name it
   *  rather than showing an empty space. */
  noSentimentReason(): string {
    const llmErr = this.newsInsightError();
    if (llmErr) return `AI digest failed — ${llmErr}`;
    const err = this.newsFetchError();
    if (err) return `Couldn't fetch news — ${err}`;
    if (!this.newsLlmEnabled()) {
      return this.news().length
        ? 'Headlines below, but AI sentiment is off — set ANTHROPIC_API_KEY in .env.'
        : 'No headlines stored yet, and AI sentiment is off (set ANTHROPIC_API_KEY).';
    }
    if (!this.news().length) return 'No headlines stored for this stock yet.';
    return 'Headlines are stored but the AI digest has not been generated yet.';
  }

  /** A one-line overall read for the top strip: prefer the digest summary, else
   *  fall back to a plain sentence built from the sentiment. */
  shortSentiment(ni: NewsInsight): string {
    if (ni.summary) {
      const first = ni.summary.split(/(?<=[.!?])\s/)[0].trim();
      return first.length > 160 ? first.slice(0, 157).trimEnd() + '…' : first;
    }
    const map: Record<string, string> = {
      positive: 'Recent news reads positive overall.',
      negative: 'Recent news reads negative overall.',
      neutral: 'Recent news is broadly neutral.',
      mixed: 'Recent news is mixed.',
    };
    return map[ni.sentiment ?? ''] ?? 'News digest available below.';
  }

  scrollToNews(): void {
    this.newsSection?.nativeElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  private load(ticker: string): void {
    this.loading.set(true);
    this.api.getFundamentals(ticker).subscribe({
      next: (d) => {
        this.data.set(d);
        this.loading.set(false);
        if (d.ratios) this.loadInsight(ticker);
        this.loadNews(ticker, false);
      },
      error: () => {
        this.loading.set(false);
        this.snackBar.open(`Failed to load fundamentals for ${ticker}`, 'Dismiss', { duration: 4000 });
      },
    });
  }

  private loadInsight(ticker: string): void {
    this.insight.set(null);
    this.llmDisabled.set(false);
    this.insightLoading.set(true);
    this.api.getFundamentalsInsights(ticker).subscribe({
      next: (resp) => {
        this.insightLoading.set(false);
        this.llmDisabled.set(!resp.llm_enabled);
        this.insight.set(this.unwrap<FundamentalsInsight>(resp.insight));
      },
      error: () => this.insightLoading.set(false),   // insight is optional — fail quietly
    });
  }

  private loadNews(ticker: string, refresh: boolean): void {
    this.newsLoading.set(true);
    if (refresh) { this.newsInsight.set(null); }
    this.api.getNews(ticker, refresh).subscribe({
      next: (resp) => {
        this.newsLoading.set(false);
        this.news.set(resp.articles);
        this.newsFetchError.set(resp.fetch_error ?? null);
        this.newsLlmEnabled.set(resp.llm_enabled);
        this.newsInsightError.set(this.insightError(resp.insight));
        this.newsInsight.set(this.unwrap<NewsInsight>(resp.insight));
      },
      error: () => {
        this.newsLoading.set(false);
        this.news.set([]);
        this.newsFetchError.set('news service unreachable');
        this.newsInsight.set(null);
      },
    });
  }

  /** Pull the failure reason out of an insight envelope. `unwrap` deliberately
   *  returns null for these, which previously made a real LLM failure look
   *  identical to "no digest yet" — the reason must reach the user. */
  private insightError(raw: unknown): string | null {
    if (!raw || typeof raw !== 'object') return null;
    const obj = raw as Record<string, unknown>;
    const inner = obj['insight'];
    const err = obj['error']
      ?? (inner && typeof inner === 'object'
          ? (inner as Record<string, unknown>)['error'] : undefined);
    return typeof err === 'string' ? err : null;
  }

  /** The API wraps cached insights as {insight, generated_at, cached}; errors as {error}. */
  private unwrap<T>(raw: unknown): T | null {
    if (!raw || typeof raw !== 'object') return null;
    const obj = raw as Record<string, unknown>;
    if ('error' in obj) return null;
    if ('insight' in obj && obj['insight']) return obj['insight'] as T;
    return obj as T;
  }
}
