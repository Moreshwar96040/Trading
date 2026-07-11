import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import { PositionSizeResult, RiskReport, RiskSettings } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

@Component({
  selector: 'app-risk-page',
  standalone: true,
  imports: [CommonModule, FormsModule, MatCardModule, MatButtonModule, MatFormFieldModule,
            MatInputModule, MatIconModule, MatSlideToggleModule, MatProgressBarModule,
            MatSnackBarModule],
  template: `
    <h2>Risk Management</h2>

    <div class="grid">
      <!-- ============ settings ============ -->
      <mat-card appearance="outlined" class="panel">
        <h3>Limits</h3>
        @if (settings(); as s) {
          <mat-form-field appearance="outline">
            <mat-label>Max position % of equity</mat-label>
            <input matInput type="number" [(ngModel)]="s.maxPositionPct">
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Max sector % of equity</mat-label>
            <input matInput type="number" [(ngModel)]="s.maxSectorPct">
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Risk per trade %</mat-label>
            <input matInput type="number" [(ngModel)]="s.riskPerTradePct">
          </mat-form-field>
          <mat-slide-toggle [(ngModel)]="s.blockOnBreach">
            Block paper orders that breach limits
          </mat-slide-toggle>
          <div class="actions">
            <button mat-flat-button color="primary" (click)="saveSettings()">
              <mat-icon>save</mat-icon> Save limits
            </button>
          </div>
        }
      </mat-card>

      <!-- ============ position size calculator ============ -->
      <mat-card appearance="outlined" class="panel">
        <h3>Position size calculator</h3>
        <mat-form-field appearance="outline">
          <mat-label>Entry price (₹)</mat-label>
          <input matInput type="number" [(ngModel)]="entryPrice">
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Stop-loss price (₹)</mat-label>
          <input matInput type="number" [(ngModel)]="stopPrice">
        </mat-form-field>
        <div class="actions">
          <button mat-flat-button color="primary" (click)="calculate()">
            <mat-icon>calculate</mat-icon> Calculate
          </button>
        </div>
        @if (sizeResult(); as r) {
          <div class="size-result">
            <p class="qty">{{ r.quantity }} shares</p>
            <p class="muted">Risk: ₹{{ r.riskAmount | number: '1.0-0' }}
              (₹{{ r.perShareRisk | number: '1.2-2' }}/share) ·
              Position value: ₹{{ r.positionValue | number: '1.0-0' }}</p>
            @if (r.cappedByPositionLimit) {
              <p class="warn">Capped by the max-position limit.</p>
            }
          </div>
        }
      </mat-card>
    </div>

    <!-- ============ exposure report ============ -->
    <h3>Exposure report</h3>
    @if (report(); as r) {
      @if (r.breaches.length) {
        <mat-card appearance="outlined" class="breach-card">
          <mat-icon>warning</mat-icon>
          <div>
            @for (b of r.breaches; track b) { <p>{{ b }}</p> }
          </div>
        </mat-card>
      }
      <p class="muted">Equity ₹{{ r.equity | number: '1.0-0' }} ·
        Cash ₹{{ r.cash | number: '1.0-0' }} ({{ r.cashPct | number: '1.1-1' }}%)</p>

      @for (p of r.positions; track p.name) {
        <div class="exposure-row">
          <span class="exp-name">{{ p.name }}</span>
          <mat-progress-bar mode="determinate"
                            [value]="barValue(p.pct, r.maxPositionPct)"
                            [color]="p.pct > r.maxPositionPct ? 'warn' : 'primary'" />
          <span class="exp-pct" [class.down]="p.pct > r.maxPositionPct">
            {{ p.pct | number: '1.1-1' }}%</span>
        </div>
      }
      @if (!r.positions.length) {
        <p class="muted">No open positions — exposure report is empty.</p>
      }
    }
  `,
  styles: `
    h2, h3 { font-weight: 500; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 16px; margin-bottom: 20px; }
    .panel { padding: 16px; display: flex; flex-direction: column; gap: 4px; }
    .actions { margin-top: 12px; }
    .size-result { margin-top: 12px; }
    .qty { font-size: 26px; font-weight: 600; margin: 0; }
    .warn { color: #ffb74d; }
    .breach-card { padding: 12px 16px; display: flex; gap: 12px; align-items: center;
                   color: #ef5350; margin-bottom: 12px; }
    .exposure-row { display: grid; grid-template-columns: 140px 1fr 70px; gap: 12px;
                    align-items: center; margin-bottom: 8px; }
    .exp-name { font-weight: 500; }
    .exp-pct { text-align: right; }
    .down { color: #ef5350; }
    .muted { opacity: 0.6; }
  `,
})
export class RiskPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly snackBar = inject(MatSnackBar);

  readonly settings = signal<RiskSettings | null>(null);
  readonly report = signal<RiskReport | null>(null);
  readonly sizeResult = signal<PositionSizeResult | null>(null);

  entryPrice: number | null = null;
  stopPrice: number | null = null;

  ngOnInit(): void {
    this.api.getRiskSettings().subscribe({ next: (s) => this.settings.set(s) });
    this.loadReport();
  }

  loadReport(): void {
    this.api.getRiskReport().subscribe({
      next: (r) => this.report.set(r),
      error: () => this.snackBar.open('Failed to load risk report', 'Dismiss', { duration: 4000 }),
    });
  }

  saveSettings(): void {
    const s = this.settings();
    if (!s) return;
    this.api.updateRiskSettings(s).subscribe({
      next: (saved) => {
        this.settings.set(saved);
        this.snackBar.open('Limits saved', undefined, { duration: 2500 });
        this.loadReport();
      },
      error: (err) => this.snackBar.open(err?.error?.message ?? 'Save failed', 'Dismiss', { duration: 5000 }),
    });
  }

  calculate(): void {
    if (!this.entryPrice || !this.stopPrice) {
      this.snackBar.open('Enter entry and stop prices', 'Dismiss', { duration: 3000 });
      return;
    }
    this.api.calcPositionSize(this.entryPrice, this.stopPrice).subscribe({
      next: (r) => this.sizeResult.set(r),
      error: (err) => this.snackBar.open(err?.error?.message ?? 'Calculation failed', 'Dismiss', { duration: 5000 }),
    });
  }

  barValue(pct: number, limit: number): number {
    return Math.min(100, (pct / Math.max(limit, 1)) * 100);
  }
}
