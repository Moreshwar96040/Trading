import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';

import { AlphaSetup, AlphaStack, SignalInfo } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';
import { TradeSignalDialogComponent } from '../strategies/trade-signal-dialog.component';

/**
 * The Alpha Stack: every live setup ranked by conviction — the fusion of
 * technical trigger, fundamental quality, news sentiment, ML vote and market
 * regime. Size follows conviction; vetoed setups say why.
 */
@Component({
  selector: 'app-alpha-stack-page',
  standalone: true,
  imports: [CommonModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule,
            MatDialogModule, MatProgressSpinnerModule, MatSnackBarModule, MatTooltipModule],
  template: `
    <h2>Alpha Stack</h2>
    <p class="lede">Technical says <em>when</em> · fundamentals say <em>what's worth it</em> ·
      news says <em>not today?</em> · regime says <em>how much</em>. Conviction decides size.</p>

    @if (loading()) {
      <div class="spinner"><mat-spinner diameter="36" /></div>
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
                    <div class="layer" [matTooltip]="b.note"
                         [class.pos]="b.points > 0" [class.neg]="b.points < 0">
                      <mat-icon>{{ layerIcon(b.layer) }}</mat-icon>
                      <span>{{ b.points > 0 ? '+' : '' }}{{ b.points }}</span>
                    </div>
                  }
                  @if (s.quality) {
                    <span class="grade" [matTooltip]="'Business quality ' + s.quality.score + '/100'">
                      grade {{ s.quality.grade }}</span>
                  }
                </div>
                <p class="strategies">via {{ strategyNames(s) }}</p>
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
    .lede { color: var(--text-dim); font-size: 13.5px; margin: -6px 0 18px; }
    .lede em { color: var(--accent); font-style: normal; font-weight: 600; }
    .spinner { display: flex; justify-content: center; padding: 40px; }

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
    .layer.pos { color: var(--up); border-color: rgba(38,166,154,0.35); }
    .layer.neg { color: var(--down); border-color: rgba(239,83,80,0.35); }
    .grade { font-size: 11px; font-weight: 700; color: var(--accent-2); cursor: help; }
    .strategies { font-size: 12px; color: var(--text-dim); margin: 2px 0 0; }

    .act { display: flex; flex-direction: column; align-items: center; gap: 4px; flex-shrink: 0; }
    .size-hint { font-size: 11px; color: var(--text-dim); font-weight: 600; }

    .empty { display: flex; gap: 16px; align-items: center; padding: 22px;
             color: var(--text-dim); }
    .empty a { margin-top: 8px; }
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

  ngOnInit(): void {
    this.api.getAlphaStack().subscribe({
      next: (s) => { this.stack.set(s); this.loading.set(false); },
      error: () => {
        this.loading.set(false);
        this.snackBar.open('Alpha Stack unavailable — is the data service running?',
                           'Dismiss', { duration: 5000 });
      },
    });
  }

  layerIcon(layer: string): string {
    return { technical: 'candlestick_chart', quality: 'account_balance',
             news: 'newspaper', ml: 'psychology', regime: 'radar' }[layer] ?? 'circle';
  }

  strategyNames(s: AlphaSetup): string {
    return s.strategies.map((st) => st.name).join(', ');
  }

  trade(s: AlphaSetup): void {
    const first = s.strategies[0];
    const signal: SignalInfo = {
      id: 0, strategyId: first.id, strategyName: first.name, ticker: s.ticker,
      symbolName: s.name, signal: 'ENTRY', asOfDate: 'latest bar',
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
