import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { EdgeGatesReport } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

/**
 * Edge Gates: the honest scoreboard. Every strategy walks four gates —
 * sample size, robustness, paper record, live expectancy — and the panel
 * says in plain words which of your strategies is a proven edge, which is a
 * work in progress, and which is a hypothesis wearing a costume.
 */
@Component({
  selector: 'app-edge-gates-panel',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatIconModule, MatTooltipModule],
  template: `
    @if (report(); as rep) {
      @if (rep.status === 'OK') {
        <mat-card appearance="outlined" class="gates-card">
          <div class="head">
            <mat-icon>flag_circle</mat-icon>
            <div>
              <h3>Edge Gates</h3>
              <span class="sub">A strategy earns real risk by passing all four gates —
                everything else is a hypothesis. No exceptions, including your favourites.</span>
            </div>
          </div>

          <div class="gate-legend">
            <span>1 · Sample ({{ rep.thresholds.backtest_trades }}+ trades)</span>
            <span>2 · Robustness ({{ rep.thresholds.robustness }}+ & OOS positive)</span>
            <span>3 · Paper ({{ rep.thresholds.paper_trades }}+ fills)</span>
            <span>4 · Live edge (expectancy > 0)</span>
          </div>

          @for (s of rep.strategies; track s.strategy_id; let i = $index) {
            <div class="strat-row" [style.animation-delay.ms]="i * 80">
              <span class="verdict" [class]="'verdict ' + s.verdict.toLowerCase()">
                {{ verdictLabel(s.verdict) }}</span>
              <span class="strat-name">{{ s.name }}</span>
              <div class="gate-chips">
                @for (g of gateList(s); track g.key) {
                  <div class="gate-chip" [class]="'gate-chip ' + g.status.toLowerCase()"
                       [matTooltip]="g.detail">
                    <mat-icon>{{ g.status === 'PASS' ? 'check_circle'
                                : g.status === 'FAIL' ? 'cancel' : 'schedule' }}</mat-icon>
                    <span>{{ g.label }}</span>
                  </div>
                }
              </div>
            </div>
          }
        </mat-card>
      }
    }
  `,
  styles: `
    .gates-card { padding: 16px 20px; margin-bottom: 16px; }
    .head { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 10px; }
    .head mat-icon { color: var(--accent); margin-top: 2px; }
    .head h3 { margin: 0; font-weight: 600; }
    .sub { font-size: 12px; color: var(--text-dim); line-height: 1.5; }

    .gate-legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: 10.5px;
                   color: var(--text-dim); margin-bottom: 10px; letter-spacing: 0.02em; }

    .strat-row {
      display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
      padding: 10px 4px; border-top: 1px solid var(--card-border);
      animation: rowIn 0.4s cubic-bezier(0.22,0.9,0.3,1) both;
    }
    @keyframes rowIn { from { opacity: 0; transform: translateY(6px); }
                       to { opacity: 1; transform: translateY(0); } }
    .verdict { font-size: 10px; font-weight: 800; letter-spacing: 0.08em;
               padding: 3px 10px; border-radius: 999px; white-space: nowrap; }
    .verdict.validated { background: rgba(38,166,154,0.18); color: var(--up); }
    .verdict.in_progress { background: rgba(56,189,248,0.15); color: var(--accent); }
    .verdict.untested { background: var(--card-border); color: var(--text-dim); }
    .verdict.failed { background: rgba(239,83,80,0.15); color: var(--down); }
    .strat-name { font-weight: 600; font-size: 13.5px; min-width: 160px; }

    .gate-chips { display: flex; gap: 6px; margin-left: auto; flex-wrap: wrap; }
    .gate-chip {
      display: flex; align-items: center; gap: 4px; cursor: help;
      font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 999px;
      border: 1px solid var(--card-border); color: var(--text-dim);
    }
    .gate-chip mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .gate-chip.pass { color: var(--up); border-color: rgba(38,166,154,0.4); }
    .gate-chip.fail { color: var(--down); border-color: rgba(239,83,80,0.4); }
    .gate-chip.pending { opacity: 0.75; }
  `,
})
export class EdgeGatesPanelComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  readonly report = signal<EdgeGatesReport | null>(null);

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.api.getEdgeGates().subscribe({
      next: (r) => this.report.set(r),
      error: () => this.report.set(null),   // panel is additive — vanish quietly
    });
  }

  verdictLabel(v: string): string {
    return v === 'VALIDATED' ? 'PROVEN EDGE' : v.replace('_', ' ');
  }

  gateList(s: EdgeGatesReport['strategies'][number]) {
    return [
      { key: 'sample', label: 'Sample', ...s.gates.sample },
      { key: 'robustness', label: 'Robust', ...s.gates.robustness },
      { key: 'paper', label: 'Paper', ...s.gates.paper },
      { key: 'live_edge', label: 'Live', ...s.gates.live_edge },
    ];
  }
}
