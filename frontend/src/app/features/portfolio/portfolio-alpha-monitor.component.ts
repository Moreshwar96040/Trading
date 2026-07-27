import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
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
 * Stack, turned into an action — add / hold / trim / sell. Closes the loop the
 * Alpha Stack opens (what to buy) with what to do about what you already own.
 * Suggestions only; it never places an order.
 */
@Component({
  selector: 'app-portfolio-alpha-monitor',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule, MatIconModule,
            MatProgressSpinnerModule, MatTooltipModule, RouterLink],
  template: `
    <mat-card appearance="outlined" class="monitor">
      <div class="head">
        <mat-icon class="head-icon">radar</mat-icon>
        <h3>Alpha Monitor</h3>
        @if (data(); as d) {
          @if (d.summary && d.summary.action_needed > 0) {
            <span class="need">{{ d.summary.action_needed }} need a decision</span>
          } @else if (d.status === 'OK') {
            <span class="calm">all holdings on track</span>
          }
        }
        <button mat-stroked-button (click)="load()" [disabled]="loading()" class="refresh">
          <mat-icon>refresh</mat-icon> {{ loading() ? 'Scoring…' : 'Re-score' }}
        </button>
      </div>
      <p class="lede">Each holding re-run through the Alpha Stack. Conviction fades —
        this catches a position that's quietly become one you'd never open today.</p>

      @if (loading()) {
        <div class="loading"><mat-spinner diameter="26" /> Scoring your holdings…</div>
      } @else if (data()) {
        <!-- the as alias binds only on a primary if, so read the signal into d here -->
        @if (data(); as d) {
        @if (d.status === 'NO_POSITIONS') {
          <p class="empty">{{ d.note }}</p>
        } @else {
          <div class="rows">
            @for (r of d.reviews; track r.ticker) {
              <div class="rev" [class]="'rev ' + r.action.toLowerCase()">
                <span class="act" [class]="'act ' + r.action.toLowerCase()">
                  <mat-icon>{{ actionIcon(r.action) }}</mat-icon>{{ r.action }}
                </span>
                <div class="who">
                  <div class="line1">
                    <a [routerLink]="['/alpha']" [queryParams]="{ ticker: r.ticker }"
                       class="tk">{{ r.ticker }}</a>
                    <span class="src" [class.live]="r.source === 'LIVE'">{{ r.source }}</span>
                    @if (r.pnl_pct !== null) {
                      <span class="pnl" [class.up]="r.pnl_pct > 0" [class.down]="r.pnl_pct < 0">
                        {{ r.pnl_pct > 0 ? '+' : '' }}{{ r.pnl_pct | number: '1.1-1' }}%
                      </span>
                    }
                    @if (r.conviction !== null) {
                      <span class="conv" [matTooltip]="'Alpha Stack conviction'">
                        {{ r.conviction }}/100</span>
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
          <p class="disclaimer">AI-assisted suggestions from your conviction model —
            not investment advice. No orders are placed automatically.</p>
        }
        }
      } @else if (errored()) {
        <p class="empty">Couldn't score the portfolio — is the data service running?</p>
      }
    </mat-card>
  `,
  styles: `
    .monitor { padding: 16px 20px; margin-bottom: 16px; }
    .head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .head-icon { color: var(--accent); }
    .head h3 { margin: 0; font-weight: 600; }
    .need { font-size: 11px; font-weight: 800; letter-spacing: 0.05em; padding: 3px 10px;
            border-radius: 999px; background: rgba(255,183,77,0.16); color: #ffb74d; }
    .calm { font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 999px;
            background: rgba(38,166,154,0.15); color: var(--up); }
    .refresh { margin-left: auto; }
    .lede { color: var(--text-dim); font-size: 12.5px; margin: 6px 0 14px; line-height: 1.5; }
    .loading { display: flex; align-items: center; gap: 12px; color: var(--text-dim);
               padding: 16px 0; }
    .empty { color: var(--text-dim); padding: 12px 0; }
    .rows { display: flex; flex-direction: column; gap: 8px; }
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
    .src { font-size: 9px; font-weight: 700; letter-spacing: 0.06em; padding: 1px 6px;
           border-radius: 999px; background: rgba(148,163,184,0.16); color: var(--text-dim); }
    .src.live { background: rgba(56,189,248,0.16); color: var(--accent); }
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
  readonly data = signal<PortfolioAlphaReview | null>(null);
  readonly loading = signal(false);
  readonly errored = signal(false);

  ngOnInit(): void {
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
