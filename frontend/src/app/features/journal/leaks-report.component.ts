import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { LeaksReport } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

/**
 * The Leaks Report: your trading habits, quantified. Expectancy, win rate,
 * payoff, weekday P&L, and the discipline leaks (no-stop orders, unjournaled
 * buys, oversized losers) — plus an AI coach's read when the API key is set.
 */
@Component({
  selector: 'app-leaks-report',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatIconModule, MatTooltipModule],
  template: `
    @if (report(); as rep) {
      @if (rep.status === 'OK') {
        <mat-card appearance="outlined" class="leaks-card">
          <div class="head">
            <mat-icon>query_stats</mat-icon>
            <h3>Your edge report</h3>
            <span class="sub">{{ rep.closed_trades }} closed trades ·
              journal coverage {{ rep.journal_coverage_pct ?? 0 }}%</span>
          </div>

          <!-- stat strip -->
          <div class="stats">
            @for (s of statCards(); track s.label) {
              <div class="stat" [matTooltip]="s.tip">
                <span class="stat-value" [class.up]="s.tone === 'up'"
                      [class.down]="s.tone === 'down'">{{ s.value }}</span>
                <span class="stat-label">{{ s.label }}</span>
              </div>
            }
          </div>

          <!-- weekday P&L -->
          @if (weekBars().length) {
            <div class="week">
              @for (w of weekBars(); track w.day) {
                <div class="week-col" [matTooltip]="w.trades + ' exits, ₹' + w.pnl">
                  <div class="week-track">
                    <div class="week-bar" [class.neg]="w.pnl < 0"
                         [style.height.%]="animate() ? w.pct : 0"></div>
                  </div>
                  <span class="week-day">{{ w.day }}</span>
                </div>
              }
              <span class="week-hint">P&L by exit weekday</span>
            </div>
          }

          <!-- leaks -->
          @if (rep.leaks?.length) {
            <div class="leak-list">
              @for (l of rep.leaks; track l.kind; let i = $index) {
                <div class="leak" [class.high]="l.severity === 'high'"
                     [style.animation-delay.ms]="i * 120">
                  <mat-icon>{{ l.severity === 'high' ? 'water_drop' : 'opacity' }}</mat-icon>
                  <span>{{ l.text }}</span>
                </div>
              }
            </div>
          } @else {
            <p class="clean"><mat-icon>verified</mat-icon> No discipline leaks detected — keep it up.</p>
          }

          <!-- AI coach -->
          @if (coach(); as c) {
            <div class="coach">
              <div class="coach-head"><mat-icon>sports</mat-icon> Coach's read</div>
              @if (c.headline) { <p class="coach-headline">“{{ c.headline }}”</p> }
              <div class="coach-cols">
                @if (c.habits_working?.length) {
                  <div>
                    <h5 class="good">Working</h5>
                    <ul>@for (h of c.habits_working; track h) { <li>{{ h }}</li> }</ul>
                  </div>
                }
                @if (c.habits_costing_you?.length) {
                  <div>
                    <h5 class="bad">Costing you</h5>
                    <ul>@for (h of c.habits_costing_you; track h) { <li>{{ h }}</li> }</ul>
                  </div>
                }
              </div>
              @if (c.one_change) {
                <p class="one-change"><strong>One change for next month:</strong> {{ c.one_change }}</p>
              }
            </div>
          }
        </mat-card>
      } @else if (rep.status === 'NO_TRADES') {
        <mat-card appearance="outlined" class="leaks-card empty">
          <mat-icon>query_stats</mat-icon>
          <p>{{ rep.note }}</p>
        </mat-card>
      }
    }
  `,
  styles: `
    .leaks-card { padding: 18px 22px; margin-bottom: 20px; }
    .head { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
    .head mat-icon { color: var(--accent); }
    .head h3 { margin: 0; font-weight: 600; }
    .sub { font-size: 12px; color: var(--text-dim); margin-left: auto; }

    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
             gap: 10px; margin-bottom: 16px; }
    .stat { padding: 10px 12px; border-radius: 12px; border: 1px solid var(--card-border);
            display: flex; flex-direction: column; gap: 2px; }
    .stat-value { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
    .stat-label { font-size: 11px; color: var(--text-dim); }

    .week { display: flex; gap: 10px; align-items: flex-end; margin: 4px 0 16px;
            position: relative; padding-bottom: 4px; }
    .week-col { display: flex; flex-direction: column; align-items: center; gap: 4px; }
    .week-track { height: 64px; width: 26px; display: flex; align-items: flex-end;
                  border-radius: 6px; background: var(--card-border); overflow: hidden; }
    .week-bar { width: 100%; background: linear-gradient(180deg, var(--up), rgba(38,166,154,0.35));
                transition: height 0.9s cubic-bezier(0.22, 0.9, 0.3, 1) 0.2s; border-radius: 6px 6px 0 0; }
    .week-bar.neg { background: linear-gradient(180deg, var(--down), rgba(239,83,80,0.35)); }
    .week-day { font-size: 10px; color: var(--text-dim); }
    .week-hint { position: absolute; right: 0; top: -2px; font-size: 11px; color: var(--text-dim); }

    .leak-list { display: flex; flex-direction: column; gap: 8px; }
    .leak { display: flex; gap: 10px; align-items: flex-start; font-size: 13px;
            padding: 10px 12px; border-radius: 12px; line-height: 1.45;
            border: 1px solid rgba(255,183,77,0.35); background: rgba(255,183,77,0.06);
            animation: drip 0.5s cubic-bezier(0.22, 0.9, 0.3, 1) both; }
    .leak mat-icon { font-size: 18px; width: 18px; height: 18px; color: #ffb74d; }
    .leak.high { border-color: rgba(239,83,80,0.4); background: rgba(239,83,80,0.07); }
    .leak.high mat-icon { color: var(--down); }
    @keyframes drip { from { opacity: 0; transform: translateY(-8px); }
                      to { opacity: 1; transform: translateY(0); } }
    .clean { display: flex; align-items: center; gap: 8px; color: var(--up); font-size: 13px; }

    .coach { margin-top: 16px; padding: 14px 16px; border-radius: 14px;
             border: 1px solid var(--card-border);
             background: linear-gradient(135deg, rgba(56,189,248,0.05), rgba(129,140,248,0.05)); }
    .coach-head { display: flex; align-items: center; gap: 6px; font-weight: 600; font-size: 13px; }
    .coach-head mat-icon { color: var(--accent-2); font-size: 18px; width: 18px; height: 18px; }
    .coach-headline { font-size: 15px; font-weight: 500; margin: 8px 0; font-style: italic; }
    .coach-cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0 20px; }
    .coach-cols h5 { margin: 6px 0 2px; font-size: 12px; }
    .coach-cols h5.good { color: var(--up); } .coach-cols h5.bad { color: var(--down); }
    .coach-cols ul { margin: 2px 0; padding-left: 18px; font-size: 13px; }
    .coach-cols li { margin: 3px 0; line-height: 1.4; }
    .one-change { font-size: 13px; margin: 10px 0 0; }

    .empty { display: flex; align-items: center; gap: 12px; color: var(--text-dim);
             font-size: 13px; }
    .up { color: var(--up); } .down { color: var(--down); }
  `,
})
export class LeaksReportComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  readonly report = signal<LeaksReport | null>(null);
  readonly animate = signal(false);

  ngOnInit(): void {
    this.api.getLeaksReport().subscribe({
      next: (r) => {
        this.report.set(r);
        setTimeout(() => this.animate.set(true), 80);
      },
      error: () => this.report.set(null),   // report is additive — vanish quietly
    });
  }

  readonly statCards = computed(() => {
    const s = this.report()?.stats;
    if (!s) return [];
    const money = (v: number | null) =>
      v === null ? '—' : `₹${Math.round(v).toLocaleString('en-IN')}`;
    return [
      { label: 'Total P&L', value: money(s.total_pnl),
        tone: s.total_pnl > 0 ? 'up' : s.total_pnl < 0 ? 'down' : '',
        tip: 'Sum of realized P&L on closed paper trades' },
      { label: 'Expectancy / trade', value: money(s.expectancy_per_trade),
        tone: (s.expectancy_per_trade ?? 0) > 0 ? 'up' : 'down',
        tip: 'Average ₹ you make (or lose) every time you take a trade — the number that decides everything' },
      { label: 'Win rate', value: s.win_rate_pct === null ? '—' : `${s.win_rate_pct}%`,
        tone: '', tip: 'Winning trades / closed trades' },
      { label: 'Payoff ratio', value: s.payoff_ratio === null ? '—' : `${s.payoff_ratio}×`,
        tone: (s.payoff_ratio ?? 0) >= 1.5 ? 'up' : '',
        tip: 'Average win ÷ average loss. Above 1.5× you can be profitable even at a 45% win rate' },
      { label: 'Avg win / loss', value: `${money(s.avg_win)} / ${money(s.avg_loss)}`,
        tone: '', tip: 'The cut-losers-ride-winners scoreboard' },
    ];
  });

  readonly weekBars = computed(() => {
    const days = this.report()?.by_weekday ?? [];
    if (!days.length) return [];
    const maxAbs = Math.max(...days.map((d) => Math.abs(d.pnl)), 1);
    return days.map((d) => ({ ...d, pct: Math.abs(d.pnl) / maxAbs * 100 }));
  });

  coach() {
    return this.report()?.narrative?.insight ?? null;
  }
}
