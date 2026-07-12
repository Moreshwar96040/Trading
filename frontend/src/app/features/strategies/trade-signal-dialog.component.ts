import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { forkJoin } from 'rxjs';

import {
  AiRiskPlan, PositionSizeResult, RegimeInfo, SignalInfo,
} from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

export interface TradeDialogResult {
  placed: boolean;
  message: string;
}

/**
 * The discipline gate. Before any paper order goes through, the trader sees a
 * pre-flight checklist assembled from live data — signal, stop plan, risk-based
 * size, market regime — and must write down WHY. The reason becomes a journal
 * entry linked to the order, closing the plan→trade→review loop.
 */
@Component({
  selector: 'app-trade-signal-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, MatDialogModule, MatButtonModule, MatIconModule,
            MatFormFieldModule, MatInputModule, MatProgressSpinnerModule],
  template: `
    <div class="gate">
      <div class="gate-header">
        <div class="pulse-ring"><mat-icon>rocket_launch</mat-icon></div>
        <div>
          <h2>{{ data.signal.ticker }} <span class="side">BUY</span></h2>
          <p class="sub">{{ data.signal.strategyName }} · signal of {{ data.signal.asOfDate }}</p>
        </div>
      </div>

      @if (loading()) {
        <div class="loading"><mat-spinner diameter="30" /> Assembling pre-flight checks…</div>
      } @else {
        <div class="checklist">
          @for (c of checks(); track c.label; let i = $index) {
            <div class="check" [class.warn]="c.warn" [style.animation-delay.ms]="i * 110">
              <mat-icon>{{ c.warn ? 'warning_amber' : 'task_alt' }}</mat-icon>
              <div>
                <span class="check-label">{{ c.label }}</span>
                <span class="check-detail">{{ c.detail }}</span>
              </div>
            </div>
          }
        </div>

        @if (sizeError()) {
          <p class="size-error"><mat-icon>block</mat-icon> {{ sizeError() }}</p>
        } @else {
          <mat-form-field appearance="outline" class="reason-field">
            <mat-label>Why this trade? (goes to your journal)</mat-label>
            <textarea matInput rows="2" [(ngModel)]="reason"
                      placeholder="e.g. Golden cross + volume surge; regime supportive; risking 1% to make 2.4%"></textarea>
            <mat-hint align="end" [class.ok]="reasonValid()">
              {{ reason.trim().length }}/12 min chars — future-you will thank present-you
            </mat-hint>
          </mat-form-field>
        }
      }

      <div class="actions">
        <button mat-button (click)="ref.close()">Walk away</button>
        <button mat-flat-button color="primary" [disabled]="!canPlace() || placing()"
                (click)="place()">
          @if (placing()) { <mat-spinner diameter="18" /> } @else {
            <ng-container><mat-icon>bolt</mat-icon>
              Buy {{ size()?.quantity }} · risk ₹{{ size()?.riskAmount | number: '1.0-0' }}
            </ng-container>
          }
        </button>
      </div>
    </div>
  `,
  styles: `
    .gate { padding: 22px 24px; min-width: 460px; max-width: 560px; }
    .gate-header { display: flex; gap: 14px; align-items: center; margin-bottom: 14px; }
    .pulse-ring {
      width: 46px; height: 46px; border-radius: 14px; display: grid; place-items: center;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      animation: pulse 2.2s ease-in-out infinite;
    }
    .pulse-ring mat-icon { color: #061020; }
    @keyframes pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(56, 189, 248, 0.45); }
      50% { box-shadow: 0 0 0 12px rgba(56, 189, 248, 0); }
    }
    h2 { margin: 0; font-size: 20px; }
    .side { font-size: 12px; font-weight: 700; color: var(--up); letter-spacing: 0.08em;
            vertical-align: middle; margin-left: 6px; }
    .sub { margin: 2px 0 0; font-size: 12px; color: var(--text-dim); }

    .loading { display: flex; align-items: center; gap: 14px; padding: 28px 4px;
               color: var(--text-dim); }

    .checklist { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
    .check {
      display: flex; gap: 12px; align-items: flex-start; padding: 10px 12px;
      border-radius: 12px; border: 1px solid var(--card-border);
      background: rgba(56, 189, 248, 0.04);
      animation: slideIn 0.4s cubic-bezier(0.22, 0.9, 0.3, 1) both;
    }
    .check mat-icon { color: var(--up); font-size: 20px; width: 20px; height: 20px; margin-top: 1px; }
    .check.warn { border-color: rgba(255, 183, 77, 0.4); background: rgba(255, 183, 77, 0.06); }
    .check.warn mat-icon { color: #ffb74d; }
    .check-label { display: block; font-size: 13px; font-weight: 600; }
    .check-detail { display: block; font-size: 12px; color: var(--text-dim); line-height: 1.4; }
    @keyframes slideIn {
      from { opacity: 0; transform: translateX(-14px); }
      to { opacity: 1; transform: translateX(0); }
    }

    .reason-field { width: 100%; }
    .reason-field .ok { color: var(--up); }
    .size-error { display: flex; gap: 8px; align-items: center; color: var(--down);
                  font-size: 13px; }
    .actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 6px; }
    .actions button mat-spinner { display: inline-block; }
  `,
})
export class TradeSignalDialogComponent implements OnInit {
  readonly data = inject<{ signal: SignalInfo }>(MAT_DIALOG_DATA);
  readonly ref = inject(MatDialogRef<TradeSignalDialogComponent, TradeDialogResult>);
  private readonly api = inject(MarketDataService);

  readonly loading = signal(true);
  readonly placing = signal(false);
  readonly risk = signal<AiRiskPlan | null>(null);
  readonly regime = signal<RegimeInfo | null>(null);
  readonly size = signal<PositionSizeResult | null>(null);
  readonly sizeError = signal<string | null>(null);
  reason = '';

  ngOnInit(): void {
    forkJoin({
      risk: this.api.getAiRisk(this.data.signal.ticker),
      regime: this.api.getRegime(),
    }).subscribe({
      next: ({ risk, regime }) => {
        this.risk.set(risk);
        this.regime.set(regime);
        this.api.calcPositionSize(risk.as_of_price, risk.stop_price).subscribe({
          next: (s) => {
            this.loading.set(false);
            if (s.quantity < 1) {
              this.sizeError.set('Risk sizing produced 0 shares — stop too tight or capital too small.');
            } else {
              this.size.set(s);
            }
          },
          error: () => { this.loading.set(false); this.sizeError.set('Position sizing failed.'); },
        });
      },
      error: () => { this.loading.set(false); this.sizeError.set('Risk service unavailable.'); },
    });
  }

  readonly checks = computed(() => {
    const r = this.risk();
    const s = this.size();
    const reg = this.regime();
    if (!r) return [];
    const rows: { label: string; detail: string; warn: boolean }[] = [];

    rows.push({
      label: 'Signal confirmed', warn: false,
      detail: `${this.data.signal.strategyName} fired ENTRY on the latest bar (close ₹${r.as_of_price})`,
    });
    rows.push({
      label: 'Stop-loss attached', warn: false,
      detail: `Stop ₹${r.stop_price} (-${r.stop_pct}%, ${r.atr_stop_mult}× ATR${r.trail ? ', trailing' : ''})`
        + (r.take_profit_price ? ` · target ₹${r.take_profit_price} · R:R ${r.reward_risk}` : ''),
    });
    if (s) {
      rows.push({
        label: 'Size fits your risk rules', warn: s.cappedByPositionLimit,
        detail: `${s.quantity} shares ≈ ₹${Math.round(s.positionValue).toLocaleString('en-IN')}, `
          + `risking ₹${Math.round(s.riskAmount).toLocaleString('en-IN')} if the stop hits`
          + (s.cappedByPositionLimit ? ' (capped by max-position limit)' : ''),
      });
    }
    if (reg?.status === 'OK') {
      const against = reg.regime === 'RISK_OFF' || reg.regime === 'BEAR_RALLY' || reg.regime === 'CHOP';
      rows.push({
        label: against ? `Regime headwind: ${reg.label}` : `Regime tailwind: ${reg.label}`,
        warn: against,
        detail: reg.guidance ?? '',
      });
    }
    if (r.regime === 'DOWNTREND') {
      rows.push({
        label: 'Stock itself is in a downtrend', warn: true,
        detail: 'The adaptive-risk engine reads this symbol as trending down — a long here is counter-trend.',
      });
    }
    return rows;
  });

  reasonValid(): boolean {
    return this.reason.trim().length >= 12;
  }

  canPlace(): boolean {
    return !this.loading() && !this.sizeError() && !!this.size() && this.reasonValid();
  }

  place(): void {
    const r = this.risk()!;
    const s = this.size()!;
    const sig = this.data.signal;
    this.placing.set(true);
    this.api.placePaperOrder(sig.ticker, 'BUY', s.quantity, {
      strategyId: sig.strategyId,
      stopPrice: r.stop_price,
      targetPrice: r.take_profit_price,
    }).subscribe({
      next: (order) => {
        if (order.status !== 'FILLED') {
          this.placing.set(false);
          this.ref.close({ placed: false, message: `Order rejected: ${order.rejectReason}` });
          return;
        }
        // the reason becomes a journal entry linked to the order — the review loop
        this.api.createJournalEntry({
          ticker: sig.ticker,
          paperOrderId: order.id,
          title: `ENTRY ${sig.ticker} — ${sig.strategyName}`,
          body: `${this.reason.trim()}\n\n— plan: ${s.quantity} @ ₹${order.price}, `
            + `stop ₹${r.stop_price}, `
            + (r.take_profit_price ? `target ₹${r.take_profit_price}, R:R ${r.reward_risk}` : 'trailing stop')
            + ` · risk ₹${Math.round(s.riskAmount).toLocaleString('en-IN')}`,
          tags: 'entry,discipline-gate',
        }).subscribe({
          next: () => this.ref.close({
            placed: true,
            message: `Bought ${order.quantity} ${sig.ticker} @ ₹${order.price} — journaled ✓`,
          }),
          error: () => this.ref.close({
            placed: true,
            message: `Bought ${order.quantity} ${sig.ticker} @ ₹${order.price} (journal write failed)`,
          }),
        });
      },
      error: (err) => {
        this.placing.set(false);
        this.ref.close({ placed: false, message: err?.error?.message ?? 'Order failed' });
      },
    });
  }
}
