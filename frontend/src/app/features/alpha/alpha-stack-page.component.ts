import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, RouterLink } from '@angular/router';

import {
  AlphaSetup, AlphaStack, NewsRefreshResult, SignalInfo, SymbolLookupResult,
} from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';
import { TradeSignalDialogComponent } from '../strategies/trade-signal-dialog.component';
import { StockNewsDialogComponent } from './stock-news-dialog.component';

/**
 * The Alpha Stack: every live setup ranked by conviction — the fusion of
 * technical trigger, fundamental quality, news sentiment, ML vote and market
 * regime. Size follows conviction; vetoed setups say why.
 */
@Component({
  selector: 'app-alpha-stack-page',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, MatAutocompleteModule, MatCardModule,
            MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule,
            MatDialogModule, MatProgressSpinnerModule, MatSnackBarModule, MatTooltipModule],
  template: `
    <h2>Alpha Stack</h2>
    <p class="lede">Technical says <em>when</em> · fundamentals say <em>what's worth it</em> ·
      news says <em>not today?</em> · regime says <em>how much</em>. Conviction decides size.</p>

    <!-- analyze any stock, signal or not -->
    <div class="search-row">
      <mat-form-field appearance="outline" class="search-field">
        <mat-label>Analyze any stock</mat-label>
        <input matInput [(ngModel)]="query" (ngModelChange)="onQueryChange($event)"
               (keydown.enter)="analyze()" [matAutocomplete]="auto"
               placeholder="e.g. TCS, RELIANCE, INFY" autocomplete="off" />
        <mat-icon matSuffix>query_stats</mat-icon>
        <mat-autocomplete #auto="matAutocomplete" (optionSelected)="analyze()">
          @for (s of suggestions(); track s.ticker) {
            <mat-option [value]="s.ticker">
              <span class="sugg-ticker">{{ s.ticker }}</span>
              <span class="sugg-name">{{ s.name }}@if (s.sector) { · {{ s.sector }} }</span>
              <span class="sugg-badge" [class.new]="!s.in_db">
                {{ s.in_db ? 'tracked' : 'Yahoo · will be added' }}
              </span>
            </mat-option>
          }
        </mat-autocomplete>
      </mat-form-field>
      <button mat-flat-button color="primary" (click)="analyze()"
              [disabled]="loading() || seeding() || !query.trim()">
        <mat-icon>bolt</mat-icon> Analyze
      </button>
      @if (analyzed()) {
        <button mat-stroked-button (click)="showAll()">
          <mat-icon>layers</mat-icon> Back to live setups
        </button>
      }
      <button mat-flat-button class="refresh-news" (click)="refreshNews()"
              [disabled]="refreshingNews() || loading() || seeding()"
              matTooltip="Re-pull market feeds, regenerate the macro digest and
                          refresh news for these stocks">
        @if (refreshingNews()) {
          <mat-spinner diameter="18" />
        } @else {
          <mat-icon>newspaper</mat-icon>
        }
        {{ refreshingNews() ? 'Refreshing news…' : 'Refresh news' }}
      </button>
    </div>

    @if (seeding()) {
      <mat-card appearance="outlined" class="empty seeding">
        <mat-spinner diameter="28" />
        <div>
          <p><strong>{{ query.toUpperCase() }}</strong> isn't in your database yet —
            adding it from Yahoo Finance and downloading its history…</p>
          <p class="dim">First time takes ~10-20 seconds (price history + snapshot).</p>
        </div>
      </mat-card>
    } @else if (loading()) {
      <div class="spinner">
        <mat-spinner diameter="36" />
        @if (analyzed()) {
          <p class="loading-note">Scoring {{ query.toUpperCase() }} — first analysis
            also pulls its latest news and builds the AI digest (10-30s)…</p>
        }
      </div>
    } @else if (stack()) {
      @if (stack(); as st) {
      @if (st.setups.length) {
        <div class="stack">
          @for (s of st.setups; track s.ticker; let i = $index) {
            <mat-card appearance="outlined" class="setup" [style.animation-delay.ms]="i * 80">
              <!-- conviction meter -->
              <div class="meter-zone">
                <svg viewBox="0 0 80 80" class="meter">
                  <circle cx="40" cy="40" r="34" class="meter-track" />
                  <circle cx="40" cy="40" r="34"
                          [class]="'meter-fill ' + s.verdict.toLowerCase()"
                          [style.stroke-dasharray]="213.6"
                          [style.stroke-dashoffset]="213.6 * (1 - s.conviction / 100)" />
                  <text x="40" y="46" text-anchor="middle" class="meter-num">{{ s.conviction }}</text>
                </svg>
                <span class="verdict-tag" [class]="'verdict-tag ' + s.verdict.toLowerCase()">
                  {{ s.verdict === 'VETOED' ? 'NEWS VETO' : s.verdict.replace('_', ' ') }}
                </span>
              </div>

              <!-- identity + layers -->
              <div class="body">
                <div class="row1">
                  <span class="ticker">{{ s.ticker }}</span>
                  <span class="name">{{ s.name }}@if (s.sector) { · {{ s.sector }} }</span>
                  @if (s.close !== null) { <span class="price">₹{{ s.close | number: '1.2-2' }}</span> }
                </div>
                <div class="layers">
                  @for (b of s.breakdown; track b.layer) {
                    <div class="layer" [matTooltip]="layerTooltip(b)"
                         [class.pos]="b.strength >= 0.6" [class.neg]="b.strength <= 0.4">
                      <mat-icon>{{ layerIcon(b.layer) }}</mat-icon>
                      <span>{{ b.points }}<span class="of-max">/{{ b.max }}</span></span>
                    </div>
                  }
                  @if (s.quality) {
                    <span class="grade" [matTooltip]="'Business quality ' + s.quality.score + '/100'">
                      grade {{ s.quality.grade }}</span>
                  }
                  @if (s.news_score !== null && s.news_score !== undefined) {
                    <button type="button" class="news-score" [class]="'news-score ' + newsScoreClass(s.news_score)"
                            (click)="openNews(s)"
                            matTooltip="News sentiment score /10 — click to read the headlines">
                      <mat-icon>newspaper</mat-icon>
                      <span>{{ s.news_score | number: '1.1-1' }}/10</span>
                    </button>
                  }
                </div>
                <p class="strategies">
                  @if (s.strategies.length) { via {{ strategyNames(s) }} }
                  @else { snapshot posture read — no live signal fired }
                </p>
              </div>

              <!-- act -->
              <div class="act">
                <span class="size-hint">{{ s.risk_multiplier }}× size</span>
                <button mat-flat-button color="primary" [disabled]="s.risk_multiplier === 0"
                        (click)="trade(s)"
                        [matTooltip]="s.news_veto ? 'Blocked by negative news' :
                                      s.risk_multiplier === 0 ? 'Conviction too low to size' : ''">
                  <mat-icon>rocket_launch</mat-icon> Trade
                </button>
              </div>
            </mat-card>
          }
        </div>
      } @else {
        <mat-card appearance="outlined" class="empty">
          <mat-icon>layers_clear</mat-icon>
          <div>
            <p>{{ st.note }}</p>
            <a mat-stroked-button routerLink="/strategies">Go to Strategy Lab</a>
          </div>
        </mat-card>
      }
      }
    }
  `,
  styles: `
    .search-row { display: flex; gap: 12px; align-items: center; margin-bottom: 6px;
                  flex-wrap: wrap; }
    .search-field { min-width: 300px; }
    .refresh-news { margin-left: auto; background: rgba(129,140,248,0.16);
                    color: var(--accent-2); font-weight: 600; }
    .refresh-news:not(:disabled):hover { background: rgba(129,140,248,0.28); }
    .refresh-news mat-spinner { display: inline-block; margin-right: 6px;
                                vertical-align: middle; }
    .lede { color: var(--text-dim); font-size: 13.5px; margin: -6px 0 18px; }
    .lede em { color: var(--accent); font-style: normal; font-weight: 600; }
    .spinner { display: flex; flex-direction: column; align-items: center; gap: 14px;
               padding: 40px; }
    .loading-note { color: var(--text-dim); font-size: 13px; margin: 0; }

    .stack { display: flex; flex-direction: column; gap: 12px; }
    .setup {
      display: flex; align-items: center; gap: 20px; padding: 14px 20px;
      animation: pageIn 0.45s cubic-bezier(0.22, 0.9, 0.3, 1) both;
    }
    .meter-zone { display: flex; flex-direction: column; align-items: center; gap: 4px;
                  flex-shrink: 0; }
    .meter { width: 76px; height: 76px; transform: rotate(-90deg); }
    .meter-track { fill: none; stroke: var(--card-border); stroke-width: 7; }
    .meter-fill { fill: none; stroke-width: 7; stroke-linecap: round;
                  transition: stroke-dashoffset 1s cubic-bezier(0.22, 0.9, 0.3, 1); }
    .meter-fill.high { stroke: var(--up); }
    .meter-fill.normal { stroke: var(--accent); }
    .meter-fill.small { stroke: #ffb74d; }
    .meter-fill.stand_aside, .meter-fill.vetoed { stroke: var(--down); }
    .meter-num { font: 700 20px 'Space Grotesk', sans-serif; fill: var(--mat-sys-on-surface);
                 transform: rotate(90deg); transform-origin: 40px 40px; }
    .verdict-tag { font-size: 9px; font-weight: 800; letter-spacing: 0.08em;
                   padding: 2px 8px; border-radius: 999px; }
    .verdict-tag.high { background: rgba(38,166,154,0.15); color: var(--up); }
    .verdict-tag.normal { background: rgba(56,189,248,0.15); color: var(--accent); }
    .verdict-tag.small { background: rgba(255,183,77,0.15); color: #ffb74d; }
    .verdict-tag.stand_aside, .verdict-tag.vetoed { background: rgba(239,83,80,0.14);
                                                    color: var(--down); }

    .body { flex: 1; min-width: 0; }
    .row1 { display: flex; align-items: baseline; gap: 10px; }
    .ticker { font: 700 17px 'Space Grotesk', sans-serif; }
    .name { font-size: 12px; color: var(--text-dim); overflow: hidden;
            text-overflow: ellipsis; white-space: nowrap; }
    .price { margin-left: auto; font-variant-numeric: tabular-nums; font-weight: 600; }

    .layers { display: flex; gap: 8px; align-items: center; margin: 8px 0 4px; flex-wrap: wrap; }
    .layer {
      display: flex; align-items: center; gap: 4px; cursor: help;
      font: 600 12px Inter, sans-serif; padding: 3px 9px; border-radius: 999px;
      border: 1px solid var(--card-border); color: var(--text-dim);
    }
    .layer mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .of-max { opacity: 0.5; font-weight: 500; }
    .layer.pos { color: var(--up); border-color: rgba(38,166,154,0.35); }
    .layer.neg { color: var(--down); border-color: rgba(239,83,80,0.35); }
    .grade { font-size: 11px; font-weight: 700; color: var(--accent-2); cursor: help; }
    .news-score {
      display: inline-flex; align-items: center; gap: 4px; cursor: pointer;
      font: 700 12px Inter, sans-serif; padding: 3px 9px; border-radius: 999px;
      border: 1px solid var(--card-border); background: transparent; color: var(--text-dim);
      transition: background 0.15s, color 0.15s;
    }
    .news-score:hover { background: rgba(128,128,128,0.12); }
    .news-score mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .news-score.good { color: var(--up); border-color: rgba(38,166,154,0.4); }
    .news-score.mid { color: #ffb74d; border-color: rgba(255,183,77,0.4); }
    .news-score.bad { color: var(--down); border-color: rgba(239,83,80,0.4); }
    .strategies { font-size: 12px; color: var(--text-dim); margin: 2px 0 0; }

    .act { display: flex; flex-direction: column; align-items: center; gap: 4px; flex-shrink: 0; }
    .size-hint { font-size: 11px; color: var(--text-dim); font-weight: 600; }

    .empty { display: flex; gap: 16px; align-items: center; padding: 22px;
             color: var(--text-dim); }
    .empty a { margin-top: 8px; }
    .empty.seeding p { margin: 2px 0; }
    .empty.seeding .dim { font-size: 12px; opacity: 0.7; }
    .sugg-ticker { font-weight: 600; margin-right: 8px; }
    .sugg-name { opacity: 0.6; font-size: 12px; }
    .sugg-badge {
      float: right; font-size: 9px; font-weight: 700; letter-spacing: 0.06em;
      padding: 2px 8px; border-radius: 999px; margin-top: 4px;
      background: rgba(38, 166, 154, 0.15); color: var(--up);
    }
    .sugg-badge.new { background: rgba(129, 140, 248, 0.15); color: var(--accent-2); }
    @keyframes pageIn { from { opacity: 0; transform: translateY(14px); }
                        to { opacity: 1; transform: translateY(0); } }
  `,
})
export class AlphaStackPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);

  readonly stack = signal<AlphaStack | null>(null);
  readonly loading = signal(true);
  readonly analyzed = signal(false);
  readonly seeding = signal(false);
  readonly refreshingNews = signal(false);
  readonly suggestions = signal<SymbolLookupResult[]>([]);
  query = '';
  private suggestTimer: ReturnType<typeof setTimeout> | null = null;
  /** Whatever view we're on, so a news refresh reloads the same thing. */
  private currentTicker: string | undefined;

  private readonly route = inject(ActivatedRoute);

  ngOnInit(): void {
    // deep-link support: /alpha?ticker=TCS analyzes immediately (Momentum page uses this)
    const ticker = this.route.snapshot.queryParamMap.get('ticker');
    if (ticker) {
      this.query = ticker.toUpperCase();
      this.analyze();
    } else {
      this.showAll();
    }
  }

  onQueryChange(q: string): void {
    if (this.suggestTimer) clearTimeout(this.suggestTimer);
    const term = q.trim();
    if (term.length < 1) { this.suggestions.set([]); return; }
    this.suggestTimer = setTimeout(() => {
      // global lookup: local DB matches + every NSE stock Yahoo knows
      this.api.lookupSymbols(term).subscribe({
        next: (r) => this.suggestions.set(r.results),
        error: () => this.suggestions.set([]),
      });
    }, 250);
  }

  showAll(): void {
    this.analyzed.set(false);
    this.query = '';
    this.suggestions.set([]);
    this.load(undefined);
  }

  analyze(): void {
    const ticker = this.query.trim().toUpperCase();
    if (!ticker) return;
    this.analyzed.set(true);
    this.load(ticker);
  }

  /** Refresh every news input the conviction engine reads, then re-score.
   *  Scoring itself never calls an LLM — this is what makes the cached digests
   *  it reads current. */
  refreshNews(): void {
    this.refreshingNews.set(true);
    this.api.refreshAllNews().subscribe({
      next: (r) => {
        this.refreshingNews.set(false);
        this.snackBar.open(this.refreshMessage(r), 'Dismiss', { duration: 6000 });
        this.load(this.currentTicker);          // re-score with the fresh news
      },
      error: () => {
        this.refreshingNews.set(false);
        this.snackBar.open('News refresh failed — is the data service running?',
                           'Dismiss', { duration: 5000 });
      },
    });
  }

  private refreshMessage(r: NewsRefreshResult): string {
    const parts = [`${r.market.inserted} new headlines`];
    if (r.macro_sentiment) {
      parts.push(`macro tone ${r.macro_sentiment}`);
    } else if (r.macro_error) {
      parts.push(`macro digest failed: ${r.macro_error}`);
    } else {
      parts.push('no macro digest (set ANTHROPIC_API_KEY?)');
    }
    if (r.signal_news.processed) {
      parts.push(`${r.signal_news.processed} stocks re-read`);
    }
    if (r.market.failures.length) {
      parts.push(`${r.market.failures.length} feed(s) unreachable`);
    }
    return parts.join(' · ');
  }

  private load(ticker: string | undefined): void {
    this.currentTicker = ticker;
    this.loading.set(true);
    this.api.getAlphaStack(ticker).subscribe({
      next: (s) => {
        // Not in our DB yet? Seed it from Yahoo (validates + downloads history),
        // refresh the snapshot so the posture read has data, then analyze again.
        if (ticker && s.status === 'UNKNOWN_SYMBOL') {
          this.seedAndRetry(ticker);
          return;
        }
        this.stack.set(s);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.snackBar.open('Alpha Stack unavailable — is the data service running?',
                           'Dismiss', { duration: 5000 });
      },
    });
  }

  private seedAndRetry(ticker: string): void {
    this.loading.set(false);
    this.seeding.set(true);
    this.api.seedSymbol(ticker).subscribe({
      next: (sym) => {
        // fundamentals give the quality layer real data; snapshot powers the
        // posture read — then analyze. Failures degrade to neutral scores.
        this.api.triggerFundamentalsRefresh([ticker]).subscribe({
          complete: () => this.finishSeed(sym.ticker, sym.name),
          error: () => this.finishSeed(sym.ticker, sym.name),
        });
      },
      error: (err) => {
        this.seeding.set(false);
        this.stack.set({
          status: 'UNKNOWN_SYMBOL', regime: { code: null, label: null }, setups: [],
          note: err?.error?.message
            ?? `${ticker} not found on Yahoo Finance either — check the ticker spelling`,
        });
      },
    });
  }

  private finishSeed(ticker: string, name: string): void {
    this.api.triggerSnapshotRefresh().subscribe({
      complete: () => {
        this.seeding.set(false);
        this.snackBar.open(`${ticker} added — ${name}`, undefined, { duration: 4000 });
        this.load(ticker);
      },
      error: () => { this.seeding.set(false); this.load(ticker); },
    });
  }

  /** Name the layer and its weight, so "12.6/18" is self-explaining. */
  layerTooltip(b: AlphaSetup['breakdown'][number]): string {
    const label = { technical: 'Technical (timing)', quality: 'Fundamentals (quality)',
                    news: 'News sentiment', momentum: 'Relative strength',
                    ml: 'ML vote', macro: 'Market-wide news', regime: 'Market regime',
                  }[b.layer] ?? b.layer;
    return `${label} — ${b.points} of ${b.max} points\n${b.note}`;
  }

  layerIcon(layer: string): string {
    return { technical: 'candlestick_chart', quality: 'account_balance',
             news: 'newspaper', momentum: 'speed', macro: 'public',
             ml: 'psychology', regime: 'radar' }[layer] ?? 'circle';
  }

  strategyNames(s: AlphaSetup): string {
    return s.strategies.map((st) => st.name).join(', ');
  }

  newsScoreClass(score: number): string {
    return score >= 6.5 ? 'good' : score >= 4 ? 'mid' : 'bad';
  }

  openNews(s: AlphaSetup): void {
    this.dialog.open(StockNewsDialogComponent, {
      data: { ticker: s.ticker, name: s.name, score: s.news_score },
      autoFocus: false, width: '560px',
    });
  }

  trade(s: AlphaSetup): void {
    const first = s.strategies[0];    // absent for posture-only analyses
    const signal: SignalInfo = {
      id: 0, strategyId: first?.id ?? 0,
      strategyName: first?.name ?? 'Alpha Stack analysis',
      ticker: s.ticker, symbolName: s.name, signal: 'ENTRY', asOfDate: 'latest bar',
      close: s.close, evaluatedAt: '',
    };
    this.dialog.open(TradeSignalDialogComponent, { data: { signal }, autoFocus: false })
      .afterClosed().subscribe((result) => {
        if (result?.message) {
          this.snackBar.open(result.message, result.placed ? undefined : 'Dismiss',
                             { duration: 6000 });
        }
      });
  }
}
