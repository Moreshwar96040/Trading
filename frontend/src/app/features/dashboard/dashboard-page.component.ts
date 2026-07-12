import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';

import {
  AlertInfo, PaperAccount, SignalInfo, StrategyScore, TradeIdea,
} from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';
import { BriefingCardComponent } from './briefing-card.component';
import { GuardianPanelComponent } from './guardian-panel.component';
import { RegimeBannerComponent } from './regime-banner.component';

/** The "is everything okay?" screen: one look = account health, today's signals,
 *  best ideas, strategy drift, and anything that fired. */
@Component({
  selector: 'app-dashboard-page',
  standalone: true,
  imports: [CommonModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule,
            MatTooltipModule, RegimeBannerComponent, BriefingCardComponent,
            GuardianPanelComponent],
  template: `
    <h2>Trade Desk</h2>

    <!-- ============ market regime: what kind of tape is this? ============ -->
    <app-regime-banner />

    <!-- ============ the morning plan + the action queue ============ -->
    <app-briefing-card />
    <app-guardian-panel />

    <!-- ============ account health ============ -->
    @if (account(); as a) {
      <div class="metric-cards">
        <mat-card appearance="outlined" class="metric">
          <span class="metric-value">₹{{ a.equity | number: '1.0-0' }}</span>
          <span class="metric-label">Equity</span>
        </mat-card>
        <mat-card appearance="outlined" class="metric">
          <span class="metric-value">₹{{ a.cash | number: '1.0-0' }}</span>
          <span class="metric-label">Cash</span>
        </mat-card>
        <mat-card appearance="outlined" class="metric">
          <span class="metric-value" [class.up]="a.unrealizedPnl > 0"
                [class.down]="a.unrealizedPnl < 0">₹{{ a.unrealizedPnl | number: '1.0-0' }}</span>
          <span class="metric-label">Unrealized P&L</span>
        </mat-card>
        <mat-card appearance="outlined" class="metric">
          <span class="metric-value" [class.up]="a.realizedPnl > 0"
                [class.down]="a.realizedPnl < 0">₹{{ a.realizedPnl | number: '1.0-0' }}</span>
          <span class="metric-label">Realized P&L</span>
        </mat-card>
        <mat-card appearance="outlined" class="metric">
          <span class="metric-value">{{ a.positions.length }}</span>
          <span class="metric-label">Open positions</span>
        </mat-card>
      </div>
    }

    <div class="grid">
      <!-- ============ today's signals ============ -->
      <mat-card appearance="outlined" class="panel">
        <div class="panel-header">
          <h3>Today's signals</h3>
          <a mat-button routerLink="/strategies">All <mat-icon>chevron_right</mat-icon></a>
        </div>
        @if (signals().length) {
          @for (s of signals().slice(0, 8); track s.id) {
            <div class="row-line">
              <span class="chip" [class.entry]="s.signal === 'ENTRY'"
                    [class.exit]="s.signal === 'EXIT'">{{ s.signal }}</span>
              <b>{{ s.ticker }}</b>
              <span class="muted">{{ s.strategyName }}</span>
              <span class="spacer"></span>
              <span class="muted">{{ s.asOfDate }}</span>
            </div>
          }
        } @else {
          <p class="muted">No live signals. Evaluate them from the Strategies page.</p>
        }
      </mat-card>

      <!-- ============ top ideas ============ -->
      <mat-card appearance="outlined" class="panel">
        <div class="panel-header">
          <h3>Top trade ideas</h3>
          <a mat-button routerLink="/ai">All <mat-icon>chevron_right</mat-icon></a>
        </div>
        @if (ideas().length) {
          @for (idea of ideas(); track idea.ticker) {
            <div class="row-line">
              <span class="score">{{ idea.score }}</span>
              <b>{{ idea.ticker }}</b>
              <span class="muted idea-reason">{{ idea.reasons[0] }}</span>
              <span class="spacer"></span>
              @if (idea.risk_plan; as rp) {
                <span class="muted">stop ₹{{ rp.stop_price | number: '1.0-0' }}</span>
              }
            </div>
          }
        } @else {
          <p class="muted">No positive-confluence ideas right now.</p>
        }
      </mat-card>

      <!-- ============ strategy scoreboard ============ -->
      <mat-card appearance="outlined" class="panel">
        <div class="panel-header">
          <h3>Strategy scoreboard <span class="muted">live vs backtest</span></h3>
          <a mat-button routerLink="/strategies">Manage <mat-icon>chevron_right</mat-icon></a>
        </div>
        @if (scores().length) {
          @for (s of scores(); track s.strategyId) {
            <div class="row-line">
              <span class="chip" [class.entry]="s.verdict === 'ON_TRACK'"
                    [class.exit]="s.verdict === 'DECAYING'">{{ s.verdict.replaceAll('_', ' ') }}</span>
              <b>{{ s.name }}</b>
              <span class="muted">
                live {{ s.liveWinRatePct ?? '—' }}% ({{ s.liveTrades }} trades)
                · backtest {{ s.backtestWinRatePct ?? '—' }}%
              </span>
              <span class="spacer"></span>
              <span [class.up]="s.livePnl > 0" [class.down]="s.livePnl < 0">
                ₹{{ s.livePnl | number: '1.0-0' }}</span>
            </div>
          }
        } @else {
          <p class="muted">No strategies yet — build one and its live-vs-backtest record shows here.</p>
        }
      </mat-card>

      <!-- ============ triggered alerts ============ -->
      <mat-card appearance="outlined" class="panel">
        <div class="panel-header">
          <h3>Triggered alerts</h3>
          <a mat-button routerLink="/alerts">All <mat-icon>chevron_right</mat-icon></a>
        </div>
        @if (triggered().length) {
          @for (al of triggered().slice(0, 8); track al.id) {
            <div class="row-line">
              <mat-icon class="alert-icon">notifications_active</mat-icon>
              <b>{{ al.ticker }}</b>
              <span class="muted">{{ al.field }} {{ al.op }} {{ al.value }}
                @if (al.note) { · {{ al.note }} }</span>
            </div>
          }
        } @else {
          <p class="muted">Nothing has fired. Quiet is good.</p>
        }
      </mat-card>
    </div>
  `,
  styles: `
    h2 { font-weight: 600; margin-top: 0; }
    h3 { font-weight: 500; margin: 0; }
    .metric-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
                    gap: 12px; margin-bottom: 16px; }
    .metric { padding: 14px; display: flex; flex-direction: column; gap: 4px; }
    .metric-value { font-size: 22px; font-weight: 600; }
    .metric-label { font-size: 12px; opacity: 0.65; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 14px; }
    .panel { padding: 16px; }
    .panel-header { display: flex; justify-content: space-between; align-items: center;
                    margin-bottom: 8px; }
    .row-line { display: flex; gap: 10px; align-items: baseline; padding: 6px 0;
                border-bottom: 1px solid var(--card-border); }
    .row-line:last-child { border-bottom: none; }
    .spacer { flex: 1; }
    .chip { font-size: 10.5px; font-weight: 700; letter-spacing: 0.05em;
            padding: 2px 9px; border-radius: 999px; border: 1px solid var(--card-border); }
    .chip.entry { color: var(--up); border-color: rgba(38, 166, 154, 0.4);
                  background: rgba(38, 166, 154, 0.1); }
    .chip.exit { color: var(--down); border-color: rgba(239, 83, 80, 0.4);
                 background: rgba(239, 83, 80, 0.1); }
    .score { min-width: 30px; height: 30px; border-radius: 9px; display: grid;
             place-items: center; font-weight: 800; font-size: 13px;
             color: var(--on-gradient, #061020); align-self: center;
             background: linear-gradient(135deg, var(--accent), var(--accent-2)); }
    .idea-reason { max-width: 260px; overflow: hidden; text-overflow: ellipsis;
                   white-space: nowrap; }
    .alert-icon { color: #ffb74d; font-size: 18px; width: 18px; height: 18px;
                  align-self: center; }
  `,
})
export class DashboardPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);

  readonly account = signal<PaperAccount | null>(null);
  readonly signals = signal<SignalInfo[]>([]);
  readonly ideas = signal<TradeIdea[]>([]);
  readonly scores = signal<StrategyScore[]>([]);
  readonly triggered = signal<AlertInfo[]>([]);

  ngOnInit(): void {
    this.api.getPaperAccount().subscribe({ next: (a) => this.account.set(a), error: () => {} });
    this.api.listSignals().subscribe({ next: (s) => this.signals.set(s), error: () => {} });
    this.api.getAiIdeas(4).subscribe({ next: (r) => this.ideas.set(r.ideas), error: () => {} });
    this.api.getScoreboard().subscribe({ next: (s) => this.scores.set(s), error: () => {} });
    this.api.listAlerts().subscribe({
      next: (alerts) => this.triggered.set(alerts.filter((a) => a.status === 'TRIGGERED')),
      error: () => {},
    });
  }
}
