import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';

import { HoldingReview, PortfolioAlphaReview } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

/**
 * Portfolio Alpha Monitor: every stock you hold, re-scored through the Alpha
 * Stack, turned into an action — add / hold / trim / sell.
 *
 * Reused per tab via `source`: a Paper instance scores the paper book, a Real
 * instance scores live Upstox holdings, both from the one review endpoint
 * (fetched lazily when its tab is first shown). Collapses to a one-line summary
 * so it monitors without crowding the positions below it. Suggestions only —
 * it never places an order.
 */
@Component({
  selector: 'app-portfolio-alpha-monitor',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule, MatIconModule,
            MatProgressSpinnerModule, MatTooltipModule, RouterLink],
  template: `
    <mat-card appearance="outlined" class="monitor">
      <div class="head" (click)="expanded.set(!expanded())">
        <mat-icon class="head-icon">radar</mat-icon>
        <h3>Alpha Monitor@if (label()) { <span class="scope">· {{ label() }}</span> }</h3>

        @if (loading()) {
          <span class="status muted">scoring…</span>
        } @else if (actionNeeded() > 0) {
          <span class="need">{{ actionNeeded() }} need a decision</span>
          @if (counts().SELL) { <span class="pill sell">{{ counts().SELL }} sell</span> }
          @if (counts().TRIM) { <span class="pill trim">{{ counts().TRIM }} trim</span> }
          @if (counts().ADD)  { <span class="pill add">{{ counts().ADD }} add</span> }
        } @else if (scoped().length) {
          <span class="calm">all {{ scoped().length }} on track</span>
        }

        <button mat-icon-button class="resync" (click)="reload($event)"
                [disabled]="loading()" matTooltip="Re-score holdings" aria-label="Re-score">
          <mat-icon>refresh</mat-icon>
        </button>
        <mat-icon class="chevron" [class.open]="expanded()">expand_more</mat-icon>
      </div>

      @if (expanded()) {
        @if (loading()) {
          <div class="loading"><mat-spinner diameter="24" /> Scoring your holdings…</div>
        } @else if (errored()) {
          <p class="empty">Couldn't score — is the data service running?</p>
        } @else if (scoped().length) {
          <div class="rows">
            @for (r of scoped(); track r.ticker) {
              <div class="rev" [class]="'rev ' + r.action.toLowerCase()">
                <span class="act" [class]="'act ' + r.action.toLowerCase()">
                  <mat-icon>{{ actionIcon(r.action) }}</mat-icon>{{ r.action }}
                </span>
                <div class="who">
                  <div class="line1">
                    <a [routerLink]="['/alpha']" [queryParams]="{ ticker: r.ticker }"
                       class="tk">{{ r.ticker }}</a>
                    @if (r.pnl_pct !== null) {
                      <span class="pnl" [class.up]="r.pnl_pct > 0" [class.down]="r.pnl_pct < 0">
                        {{ r.pnl_pct > 0 ? '+' : '' }}{{ r.pnl_pct | number: '1.1-1' }}%
                      </span>
                    }
                    @if (r.conviction !== null) {
                      <span class="conv" matTooltip="Alpha Stack conviction">{{ r.conviction }}/100</span>
                    }
                    @if (r.trend === 'improving') { <mat-icon class="trend up">trending_up</mat-icon> }
                    @if (r.trend === 'deteriorating') { <mat-icon class="trend down">trending_down</mat-icon> }
                  </div>
                  <p class="why">{{ r.rationale }}</p>
                </div>
                <span class="qty">{{ r.quantity }} sh</span>
              </div>
            }
          </div>
          <p class="disclaimer">AI-assisted reads from your conviction model — not
            investment advice. No orders are placed automatically.</p>
        } @else {
          <p class="empty">{{ emptyCopy() }}</p>
        }
      }
    </mat-card>
  `,
  styles: `
    .monitor { padding: 14px 18px; margin-bottom: 16px; }
    .head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; cursor: pointer; }
    .head-icon { color: var(--accent); }
    .head h3 { margin: 0; font-weight: 600; }
    .scope { color: var(--text-dim); font-weight: 500; }
    .status { font-size: 12px; }
    .need { font-size: 11px; font-weight: 800; letter-spacing: 0.05em; padding: 3px 10px;
            border-radius: 999px; background: rgba(255,183,77,0.16); color: #ffb74d; }
    .calm { font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 999px;
            background: rgba(38,166,154,0.15); color: var(--up); }
    .pill { font-size: 10px; font-weight: 800; letter-spacing: 0.04em; padding: 2px 8px;
            border-radius: 999px; }
    .pill.sell { background: rgba(239,83,80,0.15); color: var(--down); }
    .pill.trim { background: rgba(255,183,77,0.15); color: #ffb74d; }
    .pill.add  { background: rgba(38,166,154,0.15); color: var(--up); }
    .resync { margin-left: auto; }
    .chevron { transition: transform 0.25s ease; opacity: 0.6; }
    .chevron.open { transform: rotate(180deg); }
    .loading { display: flex; align-items: center; gap: 12px; color: var(--text-dim);
               padding: 14px 0; }
    .empty { color: var(--text-dim); padding: 12px 0; font-size: 13px; }
    .rows { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
    .rev { display: flex; align-items: center; gap: 14px; padding: 10px 12px;
           border-radius: 12px; border: 1px solid var(--card-border);
           border-left-width: 3px; }
    .rev.sell { border-left-color: var(--down); }
    .rev.trim { border-left-color: #ffb74d; }
    .rev.add  { border-left-color: var(--up); }
    .rev.hold, .rev.unknown { border-left-color: var(--card-border); }
    .act { display: inline-flex; align-items: center; gap: 4px; flex-shrink: 0;
           width: 74px; font: 800 12px Inter, sans-serif; letter-spacing: 0.04em; }
    .act mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .act.sell { color: var(--down); }
    .act.trim { color: #ffb74d; }
    .act.add  { color: var(--up); }
    .act.hold, .act.unknown { color: var(--text-dim); }
    .who { flex: 1; min-width: 0; }
    .line1 { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .tk { font: 700 15px 'Space Grotesk', sans-serif; color: var(--mat-sys-on-surface);
          text-decoration: none; }
    .tk:hover { color: var(--accent); }
    .pnl { font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }
    .conv { font-size: 11px; color: var(--text-dim); font-family: 'JetBrains Mono', monospace; }
    .trend { font-size: 15px; width: 15px; height: 15px; }
    .trend.up { color: var(--up); }
    .trend.down { color: var(--down); }
    .why { margin: 3px 0 0; font-size: 12px; color: var(--text-dim); line-height: 1.45; }
    .qty { font-size: 11px; color: var(--text-dim); flex-shrink: 0;
           font-variant-numeric: tabular-nums; }
    .disclaimer { font-size: 11px; opacity: 0.5; margin: 12px 0 0; }
  `,
})
export class PortfolioAlphaMonitorComponent implements OnInit {
  private readonly api = inject(MarketDataService);

  /** Which book to score: 'PAPER', 'LIVE', or null for both (combined). */
  readonly source = input<'PAPER' | 'LIVE' | null>(null);

  readonly data = signal<PortfolioAlphaReview | null>(null);
  readonly loading = signal(false);
  readonly errored = signal(false);
  readonly expanded = signal(true);

  /** Reviews for this instance's book only. */
  readonly scoped = computed<HoldingReview[]>(() => {
    const reviews = this.data()?.reviews ?? [];
    const src = this.source();
    return src ? reviews.filter((r) => r.source === src) : reviews;
  });

  readonly counts = computed(() => {
    const c = { SELL: 0, TRIM: 0, HOLD: 0, ADD: 0, UNKNOWN: 0 };
    for (const r of this.scoped()) { c[r.action] = (c[r.action] ?? 0) + 1; }
    return c;
  });

  readonly actionNeeded = computed(() =>
    this.counts().SELL + this.counts().TRIM + this.counts().ADD);

  label(): string {
    const src = this.source();
    return src === 'PAPER' ? 'Paper' : src === 'LIVE' ? 'Real' : '';
  }

  emptyCopy(): string {
    const src = this.source();
    if (src === 'LIVE') return 'No real holdings to monitor — connect Upstox below.';
    if (src === 'PAPER') return 'No paper positions to monitor — place a trade below.';
    return 'No holdings to monitor yet.';
  }

  ngOnInit(): void {
    this.load();
  }

  reload(event: Event): void {
    event.stopPropagation();          // don't toggle the collapse when re-syncing
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.errored.set(false);
    this.api.getPortfolioAlphaReview().subscribe({
      next: (d) => { this.data.set(d); this.loading.set(false); },
      error: () => { this.errored.set(true); this.loading.set(false); },
    });
  }

  actionIcon(action: HoldingReview['action']): string {
    return { ADD: 'add_circle', HOLD: 'check_circle', TRIM: 'remove_circle',
             SELL: 'cancel', UNKNOWN: 'help' }[action] ?? 'circle';
  }
}
