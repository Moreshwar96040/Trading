import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { RegimeInfo } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

/**
 * "What kind of tape is this?" — breadth-based market regime, always visible on
 * the trade desk. The single most ignored input in retail trading: whether the
 * market as a whole supports your strategy style today.
 */
@Component({
  selector: 'app-regime-banner',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatIconModule, MatTooltipModule],
  template: `
    @if (regime(); as r) {
      @if (r.status === 'OK') {
        <mat-card appearance="outlined" class="banner" [class]="'banner ' + regimeClass()">
          <div class="left">
            <div class="beacon" [class]="'beacon ' + regimeClass()">
              <mat-icon>{{ icon() }}</mat-icon>
            </div>
            <div class="text">
              <div class="row1">
                <span class="label">{{ r.label }}</span>
                @if (r.volatility === 'HIGH') {
                  <span class="vol-chip">HIGH VOL</span>
                }
              </div>
              <span class="guidance">{{ r.guidance }}</span>
            </div>
          </div>

          <div class="gauges">
            <div class="gauge" matTooltip="Share of stocks above their 200-day average — the long-term health of the market">
              <div class="gauge-head">
                <span>&gt; 200-day avg</span><span class="num">{{ r.breadth!.pct_above_sma200 }}%</span>
              </div>
              <div class="track">
                <div class="fill long" [style.width.%]="animate() ? r.breadth!.pct_above_sma200 : 0"></div>
                <div class="mid-mark"></div>
              </div>
            </div>
            <div class="gauge" matTooltip="Share of stocks above their 50-day average — the short-term pulse">
              <div class="gauge-head">
                <span>&gt; 50-day avg</span><span class="num">{{ r.breadth!.pct_above_sma50 }}%</span>
              </div>
              <div class="track">
                <div class="fill short" [style.width.%]="animate() ? r.breadth!.pct_above_sma50 : 0"></div>
                <div class="mid-mark"></div>
              </div>
            </div>
            <div class="mini-stats">
              <span matTooltip="Average RSI across the universe">RSI {{ r.breadth!.avg_rsi ?? '—' }}</span>
              <span matTooltip="Average 1-month return">1M {{ fmtPct(r.breadth!.avg_return_1m_pct) }}</span>
              <span class="dim">{{ r.breadth!.symbols }} stocks · {{ r.as_of }}</span>
            </div>
          </div>
        </mat-card>
      }
    }
  `,
  styles: `
    .banner {
      display: flex; justify-content: space-between; align-items: center; gap: 24px;
      padding: 14px 20px; margin-bottom: 16px; position: relative; overflow: hidden;
    }
    .banner::before {
      content: ''; position: absolute; inset: 0 0 auto 0; height: 2.5px; opacity: 0.9;
    }
    .banner.on::before { background: linear-gradient(90deg, var(--up), transparent 70%); }
    .banner.pullback::before,
    .banner.chop::before { background: linear-gradient(90deg, #ffb74d, transparent 70%); }
    .banner.off::before,
    .banner.rally::before { background: linear-gradient(90deg, var(--down), transparent 70%); }

    .left { display: flex; align-items: center; gap: 14px; min-width: 0; }
    .beacon {
      width: 44px; height: 44px; border-radius: 13px; display: grid; place-items: center;
      flex-shrink: 0;
    }
    .beacon.on { background: rgba(38,166,154,0.15); animation: glowUp 2.6s ease-in-out infinite; }
    .beacon.on mat-icon { color: var(--up); }
    .beacon.pullback, .beacon.chop { background: rgba(255,183,77,0.14); }
    .beacon.pullback mat-icon, .beacon.chop mat-icon { color: #ffb74d; }
    .beacon.off, .beacon.rally { background: rgba(239,83,80,0.14);
                                 animation: glowDown 2.6s ease-in-out infinite; }
    .beacon.off mat-icon, .beacon.rally mat-icon { color: var(--down); }
    @keyframes glowUp {
      0%, 100% { box-shadow: 0 0 0 0 rgba(38,166,154,0.35); }
      50% { box-shadow: 0 0 0 10px rgba(38,166,154,0); }
    }
    @keyframes glowDown {
      0%, 100% { box-shadow: 0 0 0 0 rgba(239,83,80,0.35); }
      50% { box-shadow: 0 0 0 10px rgba(239,83,80,0); }
    }

    .row1 { display: flex; align-items: center; gap: 8px; }
    .label { font-weight: 700; font-size: 15px; letter-spacing: -0.01em; }
    .vol-chip { font-size: 9px; font-weight: 800; letter-spacing: 0.1em; color: #ffb74d;
                border: 1px solid rgba(255,183,77,0.5); padding: 2px 7px; border-radius: 999px; }
    .guidance { display: block; font-size: 12.5px; color: var(--text-dim); margin-top: 2px;
                line-height: 1.45; max-width: 520px; }

    .gauges { display: flex; flex-direction: column; gap: 7px; min-width: 280px; }
    .gauge-head { display: flex; justify-content: space-between; font-size: 11px;
                  color: var(--text-dim); margin-bottom: 3px; }
    .gauge-head .num { font-weight: 700; color: var(--mat-sys-on-surface);
                       font-variant-numeric: tabular-nums; }
    .track { position: relative; height: 8px; border-radius: 5px;
             background: var(--card-border); overflow: hidden; }
    .fill { height: 100%; border-radius: 5px;
            transition: width 1.1s cubic-bezier(0.22, 0.9, 0.3, 1) 0.15s; }
    .fill.long { background: linear-gradient(90deg, var(--down), #ffb74d 45%, var(--up) 70%); }
    .fill.short { background: linear-gradient(90deg, var(--accent-2), var(--accent)); }
    .mid-mark { position: absolute; left: 50%; top: 0; bottom: 0; width: 0;
                border-left: 1px dashed rgba(255,255,255,0.3); }
    .mini-stats { display: flex; gap: 12px; font-size: 11px; color: var(--text-dim);
                  font-variant-numeric: tabular-nums; }
    .mini-stats .dim { opacity: 0.7; margin-left: auto; }

    @media (max-width: 900px) {
      .banner { flex-direction: column; align-items: stretch; }
      .gauges { min-width: 0; }
    }
  `,
})
export class RegimeBannerComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  readonly regime = signal<RegimeInfo | null>(null);
  readonly animate = signal(false);

  ngOnInit(): void {
    this.api.getRegime().subscribe({
      next: (r) => {
        this.regime.set(r);
        setTimeout(() => this.animate.set(true), 80);
      },
      error: () => this.regime.set(null),   // banner is additive — vanish quietly
    });
  }

  regimeClass(): string {
    switch (this.regime()?.regime) {
      case 'RISK_ON': return 'on';
      case 'PULLBACK': return 'pullback';
      case 'CHOP': return 'chop';
      case 'BEAR_RALLY': return 'rally';
      default: return 'off';
    }
  }

  icon(): string {
    switch (this.regime()?.regime) {
      case 'RISK_ON': return 'trending_up';
      case 'PULLBACK': return 'trending_flat';
      case 'CHOP': return 'waves';
      case 'BEAR_RALLY': return 'u_turn_right';
      default: return 'trending_down';
    }
  }

  fmtPct(v: number | null | undefined): string {
    return v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`;
  }
}
