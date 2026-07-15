import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router, RouterLink } from '@angular/router';

import { MomentumBoard, MomentumStock } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

/**
 * The Momentum Engine: sector rotation heat + relative-strength leaders.
 * The classic play surfaced automatically: the strongest stocks in the
 * strongest sectors, near their highs, on above-average volume.
 */
@Component({
  selector: 'app-momentum-page',
  standalone: true,
  imports: [CommonModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule,
            MatProgressSpinnerModule, MatTooltipModule],
  template: `
    <h2>Momentum</h2>
    <p class="lede">Money rotates. This board shows where it's going —
      <em>leaders in leading sectors</em> — ranked by relative strength
      (weighted 1/3/6-month return percentile vs your whole universe).</p>

    @if (loading()) {
      <div class="spinner"><mat-spinner diameter="36" /></div>
    } @else if (board()) {
      @if (board(); as b) {
        @if (b.status === 'OK') {

          <!-- ============ sector rotation heat ============ -->
          <mat-card appearance="outlined" class="sector-card">
            <h3><mat-icon>donut_small</mat-icon> Sector rotation
              <span class="sub">· {{ b.universe }} stocks · {{ b.as_of }}</span></h3>
            <div class="sector-grid">
              @for (s of b.sectors; track s.sector; let i = $index) {
                <div class="sector" [style.animation-delay.ms]="i * 60"
                     [matTooltip]="s.stocks + ' stocks · avg 1M ' + (s.avg_1m_pct ?? '—') + '%'">
                  <div class="sector-head">
                    <span class="sector-name">{{ s.sector }}</span>
                    <span class="sector-rs" [class.hot]="s.avg_rs >= 65"
                          [class.cold]="s.avg_rs <= 35">{{ s.avg_rs }}</span>
                  </div>
                  <div class="sector-track">
                    <div class="sector-fill" [class.hot]="s.avg_rs >= 65"
                         [class.cold]="s.avg_rs <= 35"
                         [style.width.%]="animate() ? s.avg_rs : 0"></div>
                  </div>
                </div>
              }
            </div>
          </mat-card>

          <!-- ============ leaders ============ -->
          <mat-card appearance="outlined" class="list-card">
            <h3><mat-icon>local_fire_department</mat-icon> Leaders
              <span class="sub">· RS ≥ 80 · within 7% of 52-week high · volume interest</span></h3>
            @if (b.leaders?.length) {
              @for (s of b.leaders; track s.ticker; let i = $index) {
                <div class="stock-row" [style.animation-delay.ms]="i * 70">
                  <span class="rs-badge hot">{{ s.rs_rank | number: '1.0-0' }}</span>
                  <span class="ticker">{{ s.ticker }}</span>
                  <span class="name">{{ s.name }}@if (s.sector) { · {{ s.sector }} }</span>
                  <span class="stat" matTooltip="1-month return"
                        [class.up]="(s.return_1m_pct ?? 0) > 0">{{ fmtPct(s.return_1m_pct) }}</span>
                  <span class="stat" matTooltip="3-month return"
                        [class.up]="(s.return_3m_pct ?? 0) > 0">{{ fmtPct(s.return_3m_pct) }}</span>
                  <span class="stat dim" matTooltip="Distance from 52-week high">
                    {{ s.pct_from_52w_high }}%</span>
                  <span class="stat dim" matTooltip="Volume vs 20-day average">
                    {{ s.volume_ratio }}×</span>
                  <button mat-stroked-button class="analyze-btn" (click)="analyze(s)">
                    <mat-icon>query_stats</mat-icon> Analyze
                  </button>
                </div>
              }
            } @else {
              <p class="hint">No stocks currently clear the leader bar — that itself is a
                regime read: momentum is thin. Check the top-ranked list below.</p>
            }
          </mat-card>

          <!-- ============ top ranked ============ -->
          <mat-card appearance="outlined" class="list-card">
            <h3><mat-icon>trending_up</mat-icon> Top relative strength</h3>
            @for (s of b.top; track s.ticker) {
              <div class="stock-row compact">
                <span class="rs-badge" [class.hot]="s.rs_rank >= 80">{{ s.rs_rank | number: '1.0-0' }}</span>
                <span class="ticker">{{ s.ticker }}</span>
                <span class="name">{{ s.name }}</span>
                <span class="stat" [class.up]="(s.return_3m_pct ?? 0) > 0">
                  3M {{ fmtPct(s.return_3m_pct) }}</span>
                <button mat-button class="analyze-btn" (click)="analyze(s)">
                  <mat-icon>query_stats</mat-icon>
                </button>
              </div>
            }
            <p class="footnote">Backtest this edge yourself: add the rule
              <code>rs_rank gt 80</code> to any strategy in the
              <a routerLink="/strategies">Strategy Lab</a> — it's computed point-in-time,
              so the backtest is honest. Momentum's weakness is regime flips; the Alpha
              Stack already down-weights it in chop.</p>
          </mat-card>
        } @else {
          <mat-card appearance="outlined" class="empty">
            <mat-icon>speed</mat-icon><p>{{ b.note }}</p>
          </mat-card>
        }
      }
    }
  `,
  styles: `
    .lede { color: var(--text-dim); font-size: 13.5px; margin: -6px 0 18px; }
    .lede em { color: var(--accent); font-style: normal; font-weight: 600; }
    .spinner { display: flex; justify-content: center; padding: 40px; }
    h3 { display: flex; align-items: center; gap: 8px; margin: 0 0 12px; font-weight: 600; }
    h3 mat-icon { color: var(--accent); }
    .sub { font-size: 12px; color: var(--text-dim); font-weight: 400; }

    .sector-card, .list-card { padding: 16px 20px; margin-bottom: 14px; }
    .sector-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                   gap: 12px 20px; }
    .sector { animation: pageIn 0.4s cubic-bezier(0.22,0.9,0.3,1) both; }
    .sector-head { display: flex; justify-content: space-between; font-size: 12px;
                   margin-bottom: 4px; }
    .sector-name { color: var(--text-dim); }
    .sector-rs { font-weight: 700; font-variant-numeric: tabular-nums; }
    .sector-rs.hot { color: var(--up); } .sector-rs.cold { color: var(--down); }
    .sector-track { height: 7px; border-radius: 5px; background: var(--card-border);
                    overflow: hidden; }
    .sector-fill { height: 100%; border-radius: 5px;
                   background: linear-gradient(90deg, var(--accent-2), var(--accent));
                   transition: width 1s cubic-bezier(0.22,0.9,0.3,1) 0.2s; }
    .sector-fill.hot { background: linear-gradient(90deg, var(--accent), var(--up)); }
    .sector-fill.cold { background: linear-gradient(90deg, var(--down), #ff8a80); }

    .stock-row { display: flex; align-items: center; gap: 14px; padding: 9px 6px;
                 border-bottom: 1px solid var(--card-border); font-size: 13px;
                 animation: pageIn 0.4s cubic-bezier(0.22,0.9,0.3,1) both; }
    .stock-row:last-of-type { border-bottom: none; }
    .rs-badge { width: 38px; height: 26px; border-radius: 8px; display: grid;
                place-items: center; font: 700 12px 'Space Grotesk', sans-serif;
                background: var(--card-border); flex-shrink: 0; }
    .rs-badge.hot { background: rgba(38,166,154,0.16); color: var(--up); }
    .ticker { font: 700 14px 'Space Grotesk', sans-serif; min-width: 96px; }
    .name { flex: 1; color: var(--text-dim); font-size: 12px; overflow: hidden;
            text-overflow: ellipsis; white-space: nowrap; }
    .stat { font-variant-numeric: tabular-nums; min-width: 58px; text-align: right; }
    .stat.up { color: var(--up); }
    .stat.dim { color: var(--text-dim); }
    .analyze-btn { flex-shrink: 0; }
    .analyze-btn mat-icon { font-size: 16px; width: 16px; height: 16px; }

    .footnote { font-size: 12px; color: var(--text-dim); margin: 14px 0 0; line-height: 1.5; }
    .footnote code { background: var(--card-border); border-radius: 5px; padding: 1px 6px;
                     font-family: 'JetBrains Mono', monospace; font-size: 11px; }
    .footnote a { color: var(--accent); }
    .empty { display: flex; gap: 14px; align-items: center; padding: 22px;
             color: var(--text-dim); }
    .hint { color: var(--text-dim); font-size: 13px; }
    @keyframes pageIn { from { opacity: 0; transform: translateY(10px); }
                        to { opacity: 1; transform: translateY(0); } }
  `,
})
export class MomentumPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly router = inject(Router);

  readonly board = signal<MomentumBoard | null>(null);
  readonly loading = signal(true);
  readonly animate = signal(false);

  ngOnInit(): void {
    this.api.getMomentumBoard().subscribe({
      next: (b) => {
        this.board.set(b);
        this.loading.set(false);
        setTimeout(() => this.animate.set(true), 80);
      },
      error: () => { this.board.set(null); this.loading.set(false); },
    });
  }

  fmtPct(v: number | null): string {
    return v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v}%`;
  }

  analyze(s: MomentumStock): void {
    this.router.navigate(['/alpha'], { queryParams: { ticker: s.ticker } });
  }
}
