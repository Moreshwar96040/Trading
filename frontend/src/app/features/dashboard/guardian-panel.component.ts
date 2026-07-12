import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';

import { GuardianAction, GuardianReport } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

/**
 * Position Guardian: the action queue for your open book. Each card is a
 * decision the data says you should make today — with a one-click way to make
 * it (raise stop / exit) so managing positions is reviewing, not remembering.
 */
@Component({
  selector: 'app-guardian-panel',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule, MatIconModule,
            MatSnackBarModule, MatTooltipModule],
  template: `
    @if (report(); as rep) {
      <mat-card appearance="outlined" class="guardian">
        <div class="head">
          <div class="shield" [class.alert]="(rep.summary?.high_priority ?? 0) > 0">
            <mat-icon>{{ (rep.summary?.high_priority ?? 0) > 0 ? 'gpp_maybe' : 'verified_user' }}</mat-icon>
          </div>
          <div>
            <h3>Position Guardian</h3>
            @if (rep.status === 'OK') {
              <span class="sub">{{ rep.summary?.open_positions }} positions ·
                ₹{{ rep.summary?.portfolio_value | number: '1.0-0' }} at work ·
                {{ rep.summary?.high_priority }} need a decision</span>
            } @else {
              <span class="sub">{{ rep.note }}</span>
            }
          </div>
          <button mat-icon-button class="refresh" (click)="load()" matTooltip="Re-check now">
            <mat-icon>refresh</mat-icon>
          </button>
        </div>

        @if (rep.actions?.length) {
          <div class="queue">
            @for (a of rep.actions; track a.kind + (a.ticker ?? ''); let i = $index) {
              <div class="action" [class]="'action ' + a.severity"
                   [style.animation-delay.ms]="i * 90">
                <mat-icon>{{ icon(a) }}</mat-icon>
                <span class="action-text">{{ a.text }}</span>
                @if (a.kind === 'RAISE_STOP' && a.ticker && a.suggested_stop) {
                  <button mat-stroked-button class="act-btn"
                          [disabled]="busy() === a.ticker"
                          (click)="raiseStop(a.ticker!, a.suggested_stop!)">
                    <mat-icon>arrow_upward</mat-icon> Raise stop
                  </button>
                }
                @if ((a.kind === 'EXIT_SIGNAL' || a.kind === 'STOP_BREACHED') && a.ticker) {
                  <button mat-stroked-button class="act-btn exit"
                          [disabled]="busy() === a.ticker"
                          (click)="exit(a.ticker!)">
                    <mat-icon>logout</mat-icon> Exit
                  </button>
                }
              </div>
            }
          </div>
        } @else if (rep.status === 'OK') {
          <p class="all-clear"><mat-icon>task_alt</mat-icon>
            All positions inside their plan — nothing needs you today.</p>
        }
      </mat-card>
    }
  `,
  styles: `
    .guardian { padding: 16px 20px; margin-bottom: 16px; }
    .head { display: flex; align-items: center; gap: 12px; }
    .shield {
      width: 42px; height: 42px; border-radius: 13px; display: grid; place-items: center;
      background: rgba(38, 166, 154, 0.14);
    }
    .shield mat-icon { color: var(--up); }
    .shield.alert { background: rgba(239, 83, 80, 0.13); animation: alertPulse 2.4s infinite; }
    .shield.alert mat-icon { color: var(--down); }
    @keyframes alertPulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(239, 83, 80, 0.35); }
      50% { box-shadow: 0 0 0 10px rgba(239, 83, 80, 0); }
    }
    h3 { margin: 0; font-weight: 600; }
    .sub { font-size: 12px; color: var(--text-dim); }
    .refresh { margin-left: auto; }

    .queue { display: flex; flex-direction: column; gap: 8px; margin-top: 14px; }
    .action {
      display: flex; align-items: center; gap: 12px;
      padding: 10px 14px; border-radius: 12px; font-size: 13px; line-height: 1.45;
      border: 1px solid var(--card-border);
      animation: actionIn 0.45s cubic-bezier(0.22, 0.9, 0.3, 1) both;
    }
    @keyframes actionIn { from { opacity: 0; transform: translateX(-12px); }
                          to { opacity: 1; transform: translateX(0); } }
    .action mat-icon { font-size: 19px; width: 19px; height: 19px; flex-shrink: 0; }
    .action.high { border-color: rgba(239,83,80,0.4); background: rgba(239,83,80,0.06); }
    .action.high mat-icon { color: var(--down); }
    .action.medium { border-color: rgba(255,183,77,0.35); background: rgba(255,183,77,0.05); }
    .action.medium mat-icon { color: #ffb74d; }
    .action.info { border-color: var(--card-border); }
    .action.info mat-icon { color: var(--accent); }
    .action-text { flex: 1; }
    .act-btn { flex-shrink: 0; font-size: 12px; height: 32px; }
    .act-btn mat-icon { font-size: 15px; width: 15px; height: 15px; }
    .act-btn.exit { color: var(--down); border-color: rgba(239,83,80,0.4) !important; }

    .all-clear { display: flex; align-items: center; gap: 8px; color: var(--up);
                 font-size: 13px; margin: 14px 0 2px; }
  `,
})
export class GuardianPanelComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly snackBar = inject(MatSnackBar);
  readonly report = signal<GuardianReport | null>(null);
  readonly busy = signal<string | null>(null);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.api.getPortfolioHealth().subscribe({
      next: (r) => this.report.set(r),
      error: () => this.report.set(null),   // panel is additive — vanish quietly
    });
  }

  icon(a: GuardianAction): string {
    switch (a.kind) {
      case 'STOP_MISSING': return 'gpp_bad';
      case 'STOP_BREACHED': return 'crisis_alert';
      case 'NEAR_STOP': return 'warning_amber';
      case 'EXIT_SIGNAL': return 'logout';
      case 'RAISE_STOP': return 'moving';
      case 'NEAR_TARGET': return 'flag_circle';
      case 'TREND_FLIP': return 'south';
      case 'CONCENTRATION': return 'donut_large';
      default: return 'shield';
    }
  }

  raiseStop(ticker: string, stop: number): void {
    this.busy.set(ticker);
    this.api.updatePositionStop(ticker, stop).subscribe({
      next: (r) => {
        this.busy.set(null);
        this.snackBar.open(`${ticker} stop moved ₹${r.oldStop ?? '—'} → ₹${r.newStop}`,
                           undefined, { duration: 4000 });
        this.load();
      },
      error: (err) => {
        this.busy.set(null);
        this.snackBar.open(err?.error?.message ?? 'Stop update failed', 'Dismiss',
                           { duration: 5000 });
      },
    });
  }

  exit(ticker: string): void {
    const pos = this.report()?.positions?.find((p) => p.ticker === ticker);
    if (!pos) return;
    this.busy.set(ticker);
    this.api.placePaperOrder(ticker, 'SELL', pos.quantity).subscribe({
      next: (order) => {
        this.busy.set(null);
        this.snackBar.open(order.status === 'FILLED'
          ? `Exited ${order.quantity} ${ticker} @ ₹${order.price}`
          : `Exit rejected: ${order.rejectReason}`, undefined, { duration: 5000 });
        this.load();
      },
      error: (err) => {
        this.busy.set(null);
        this.snackBar.open(err?.error?.message ?? 'Exit failed', 'Dismiss', { duration: 5000 });
      },
    });
  }
}
