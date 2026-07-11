import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatListModule } from '@angular/material/list';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';

import {
  BacktestDetail, StrategyDefinition, StrategyInfo, StrategyRule,
} from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';
import { EquityChartComponent } from './equity-chart.component';
import { STRATEGY_PRESETS, StrategyPreset } from './strategy-presets';

const SERIES_HINTS = ['close', 'open', 'high', 'low', 'volume', 'sma_20', 'sma_50',
  'sma_200', 'ema_20', 'rsi_14', 'macd', 'macd_signal', 'macd_hist', 'bb_upper',
  'bb_mid', 'bb_lower', 'atr_14', 'ichimoku_tenkan', 'ichimoku_kijun',
  'ichimoku_senkou_a', 'ichimoku_senkou_b', 'ichimoku_cloud_top',
  'ichimoku_cloud_bottom', 'support', 'resistance'];
const OPS = ['gt', 'gte', 'lt', 'lte', 'crosses_above', 'crosses_below'] as const;
const TIMEFRAMES = ['daily', 'weekly', 'monthly'] as const;

interface RuleDraft { left: string; op: string; right: string; }

@Component({
  selector: 'app-strategies-page',
  standalone: true,
  imports: [CommonModule, FormsModule, MatCardModule, MatListModule, MatButtonModule,
            MatIconModule, MatFormFieldModule, MatInputModule, MatSelectModule,
            MatCheckboxModule, MatTableModule, MatProgressSpinnerModule, MatSnackBarModule,
            MatTooltipModule, EquityChartComponent],
  template: `
    <div class="layout">
      <!-- ============ strategy list ============ -->
      <mat-card appearance="outlined" class="list-card">
        <div class="list-header">
          <h3>Strategies</h3>
          <button mat-icon-button (click)="newStrategy()" matTooltip="New strategy">
            <mat-icon>add</mat-icon>
          </button>
        </div>
        <mat-nav-list>
          @for (s of strategies(); track s.id) {
            <a mat-list-item [class.selected]="selected()?.id === s.id" (click)="select(s)">
              <span matListItemTitle>{{ s.name }}</span>
              <span matListItemLine class="muted">{{ s.description || '—' }}</span>
            </a>
          }
          @if (!strategies().length) {
            <p class="muted pad">No strategies yet — create one.</p>
          }
        </mat-nav-list>
      </mat-card>

      <!-- ============ editor ============ -->
      <mat-card appearance="outlined" class="editor-card">
        <h3>{{ selected() ? 'Edit strategy' : 'New strategy' }}</h3>

        <mat-form-field appearance="outline" class="preset-field">
          <mat-label>Load a preset strategy</mat-label>
          <mat-select [(ngModel)]="presetName" (selectionChange)="applyPreset($event.value)">
            @for (p of presets; track p.name) {
              <mat-option [value]="p.name">{{ p.name }}</mat-option>
            }
          </mat-select>
          @if (selectedPreset(); as p) {
            <mat-hint>{{ p.description }}</mat-hint>
          }
        </mat-form-field>

        <div class="row">
          <mat-form-field appearance="outline" class="grow">
            <mat-label>Name</mat-label>
            <input matInput [(ngModel)]="name" placeholder="Golden Cross Rider">
          </mat-form-field>
          <mat-form-field appearance="outline" class="grow">
            <mat-label>Description</mat-label>
            <input matInput [(ngModel)]="description">
          </mat-form-field>
        </div>

        <h4>Entry rules <span class="muted">(all must hold)</span></h4>
        @for (r of entryRules(); track $index) {
          <div class="rule-row">
            <mat-form-field appearance="outline" class="w-series">
              <mat-label>Left</mat-label>
              <input matInput [(ngModel)]="r.left" [attr.list]="'series-hints'">
            </mat-form-field>
            <mat-form-field appearance="outline" class="w-op">
              <mat-label>Op</mat-label>
              <mat-select [(ngModel)]="r.op">
                @for (o of ops; track o) { <mat-option [value]="o">{{ o }}</mat-option> }
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline" class="w-series">
              <mat-label>Right (series or number)</mat-label>
              <input matInput [(ngModel)]="r.right" [attr.list]="'series-hints'">
            </mat-form-field>
            <button mat-icon-button (click)="removeRule(entryRules, $index)">
              <mat-icon>close</mat-icon>
            </button>
          </div>
        }
        <button mat-stroked-button (click)="addRule(entryRules)">
          <mat-icon>add</mat-icon> Entry rule
        </button>

        <h4>Exit rules <span class="muted">(optional; all must hold)</span></h4>
        @for (r of exitRules(); track $index) {
          <div class="rule-row">
            <mat-form-field appearance="outline" class="w-series">
              <mat-label>Left</mat-label>
              <input matInput [(ngModel)]="r.left" [attr.list]="'series-hints'">
            </mat-form-field>
            <mat-form-field appearance="outline" class="w-op">
              <mat-label>Op</mat-label>
              <mat-select [(ngModel)]="r.op">
                @for (o of ops; track o) { <mat-option [value]="o">{{ o }}</mat-option> }
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline" class="w-series">
              <mat-label>Right (series or number)</mat-label>
              <input matInput [(ngModel)]="r.right" [attr.list]="'series-hints'">
            </mat-form-field>
            <button mat-icon-button (click)="removeRule(exitRules, $index)">
              <mat-icon>close</mat-icon>
            </button>
          </div>
        }
        <button mat-stroked-button (click)="addRule(exitRules)">
          <mat-icon>add</mat-icon> Exit rule
        </button>

        <div class="row risk-row">
          <mat-form-field appearance="outline">
            <mat-label>Stop loss %</mat-label>
            <input matInput type="number" [(ngModel)]="stopLossPct">
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Take profit %</mat-label>
            <input matInput type="number" [(ngModel)]="takeProfitPct">
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Max holding days</mat-label>
            <input matInput type="number" [(ngModel)]="maxHoldingDays">
          </mat-form-field>
        </div>
        <div class="row risk-row">
          <mat-form-field appearance="outline"
                          matTooltip="Self-adjusting stop = entry − (multiplier × ATR). Scales to the stock's own volatility.">
            <mat-label>ATR stop ×</mat-label>
            <input matInput type="number" [(ngModel)]="atrStopMult" placeholder="e.g. 2.5">
          </mat-form-field>
          <mat-checkbox [(ngModel)]="atrTrail" [disabled]="!atrStopMult"
                        matTooltip="Ratchet the ATR stop upward as price rises — locks in gains automatically.">
            Trail the ATR stop
          </mat-checkbox>
        </div>

        <div class="row">
          <button mat-flat-button color="primary" (click)="save()" [disabled]="busy()">
            <mat-icon>save</mat-icon> {{ selected() ? 'Update' : 'Create' }}
          </button>
          @if (selected()) {
            <button mat-stroked-button color="warn" (click)="remove()" [disabled]="busy()">
              <mat-icon>delete</mat-icon> Delete
            </button>
          }
        </div>

        <datalist id="series-hints">
          @for (s of seriesHints; track s) { <option [value]="s"></option> }
        </datalist>
      </mat-card>
    </div>

    <!-- ============ run panel ============ -->
    @if (selected()) {
      <mat-card appearance="outlined" class="run-card">
        <h3>Backtest “{{ selected()!.name }}”</h3>
        <div class="row">
          <mat-form-field appearance="outline">
            <mat-label>From</mat-label>
            <input matInput [(ngModel)]="fromDate" placeholder="2024-07-01">
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>To</mat-label>
            <input matInput [(ngModel)]="toDate" placeholder="2026-06-30">
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Capital (₹)</mat-label>
            <input matInput type="number" [(ngModel)]="capital">
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Max positions</mat-label>
            <input matInput type="number" [(ngModel)]="maxPositions">
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Commission %/side</mat-label>
            <input matInput type="number" [(ngModel)]="commissionPct">
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Timeframe</mat-label>
            <mat-select [(ngModel)]="timeframe">
              @for (t of timeframes; track t) { <mat-option [value]="t">{{ t }}</mat-option> }
            </mat-select>
          </mat-form-field>
          <button mat-stroked-button class="run-btn" (click)="refreshData()"
                  [disabled]="busy()" matTooltip="Fetch the latest prices from the internet before testing">
            <mat-icon>cloud_download</mat-icon> Sync latest
          </button>
          <button mat-flat-button color="primary" class="run-btn" (click)="run()"
                  [disabled]="busy()">
            <mat-icon>play_arrow</mat-icon> Run
          </button>
        </div>
        <p class="muted">Weekly/monthly aggregate the daily bars for higher-timeframe
          swing testing — stop-loss, take-profit and “max holding days” then count in
          those bars.</p>
      </mat-card>
    }

    @if (busy()) {
      <div class="spinner"><mat-spinner diameter="36" /></div>
    }

    <!-- ============ results ============ -->
    @if (result(); as r) {
      @if (r.metrics; as m) {
        <div class="metric-cards">
          <mat-card appearance="outlined" class="metric">
            <span class="metric-value" [class.up]="m.total_return_pct > 0"
                  [class.down]="m.total_return_pct < 0">{{ m.total_return_pct }}%</span>
            <span class="metric-label">Total return</span>
          </mat-card>
          <mat-card appearance="outlined" class="metric">
            <span class="metric-value">{{ m.cagr_pct ?? '—' }}%</span>
            <span class="metric-label">CAGR</span>
          </mat-card>
          <mat-card appearance="outlined" class="metric">
            <span class="metric-value down">{{ m.max_drawdown_pct }}%</span>
            <span class="metric-label">Max drawdown</span>
          </mat-card>
          <mat-card appearance="outlined" class="metric">
            <span class="metric-value">{{ m.sharpe ?? '—' }}</span>
            <span class="metric-label">Sharpe</span>
          </mat-card>
          <mat-card appearance="outlined" class="metric">
            <span class="metric-value">{{ m.trades }}</span>
            <span class="metric-label">Trades</span>
          </mat-card>
          <mat-card appearance="outlined" class="metric">
            <span class="metric-value">{{ m.win_rate_pct ?? '—' }}%</span>
            <span class="metric-label">Win rate</span>
          </mat-card>
          <mat-card appearance="outlined" class="metric">
            <span class="metric-value">{{ m.profit_factor ?? '—' }}</span>
            <span class="metric-label">Profit factor</span>
          </mat-card>
        </div>

        @if (r.equityCurve?.length) {
          <mat-card appearance="outlined" class="chart-card">
            <app-equity-chart [points]="r.equityCurve!" />
          </mat-card>
        }

        <h3>Trades ({{ r.trades.length }})</h3>
        <table mat-table [dataSource]="r.trades" class="trades-table">
          <ng-container matColumnDef="ticker">
            <th mat-header-cell *matHeaderCellDef>Ticker</th>
            <td mat-cell *matCellDef="let t">{{ t.ticker }}</td>
          </ng-container>
          <ng-container matColumnDef="entryDate">
            <th mat-header-cell *matHeaderCellDef>Entry</th>
            <td mat-cell *matCellDef="let t">{{ t.entryDate }} &#64; ₹{{ t.entryPrice | number: '1.2-2' }}</td>
          </ng-container>
          <ng-container matColumnDef="exitDate">
            <th mat-header-cell *matHeaderCellDef>Exit</th>
            <td mat-cell *matCellDef="let t">{{ t.exitDate }} &#64; ₹{{ t.exitPrice | number: '1.2-2' }}</td>
          </ng-container>
          <ng-container matColumnDef="quantity">
            <th mat-header-cell *matHeaderCellDef>Qty</th>
            <td mat-cell *matCellDef="let t">{{ t.quantity }}</td>
          </ng-container>
          <ng-container matColumnDef="pnl">
            <th mat-header-cell *matHeaderCellDef>P&L (₹)</th>
            <td mat-cell *matCellDef="let t" [class.up]="t.pnl > 0" [class.down]="t.pnl < 0">
              {{ t.pnl | number: '1.0-0' }} ({{ t.pnlPct | number: '1.1-1' }}%)
            </td>
          </ng-container>
          <ng-container matColumnDef="exitReason">
            <th mat-header-cell *matHeaderCellDef>Reason</th>
            <td mat-cell *matCellDef="let t">{{ t.exitReason }}</td>
          </ng-container>
          <tr mat-header-row *matHeaderRowDef="tradeColumns"></tr>
          <tr mat-row *matRowDef="let t; columns: tradeColumns"></tr>
        </table>
      } @else if (r.error) {
        <mat-card appearance="outlined" class="error-card">Backtest failed: {{ r.error }}</mat-card>
      }
    }
  `,
  styles: `
    h3 { font-weight: 500; margin: 0 0 8px; }
    h4 { font-weight: 500; margin: 16px 0 8px; }
    .layout { display: grid; grid-template-columns: 280px 1fr; gap: 16px; }
    .list-card { padding: 12px; }
    .list-header { display: flex; justify-content: space-between; align-items: center; }
    .selected { background: var(--mat-sys-surface-container-highest); border-radius: 8px; }
    .editor-card { padding: 16px; }
    .preset-field { width: 100%; margin-bottom: 4px; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
    .grow { flex: 1; min-width: 200px; }
    .rule-row { display: flex; gap: 12px; align-items: center; }
    .w-series { width: 230px; }
    .w-op { width: 170px; }
    .risk-row { margin-top: 8px; }
    .run-card { padding: 16px; margin-top: 16px; }
    .run-btn { height: 48px; }
    .metric-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
                    gap: 12px; margin: 16px 0; }
    .metric { padding: 14px; display: flex; flex-direction: column; gap: 4px; }
    .metric-value { font-size: 20px; font-weight: 600; }
    .metric-label { font-size: 12px; opacity: 0.65; }
    .chart-card { padding: 8px; margin-bottom: 16px; }
    .trades-table { width: 100%; }
    .error-card { padding: 16px; color: #ef5350; margin-top: 16px; }
    .up { color: #26a69a; }
    .down { color: #ef5350; }
    .muted { opacity: 0.6; font-size: 12px; }
    .pad { padding: 12px; }
    .spinner { display: flex; justify-content: center; padding: 24px; }
  `,
})
export class StrategiesPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly snackBar = inject(MatSnackBar);

  readonly seriesHints = SERIES_HINTS;
  readonly ops = OPS;
  readonly timeframes = TIMEFRAMES;
  readonly presets = STRATEGY_PRESETS;
  readonly tradeColumns = ['ticker', 'entryDate', 'exitDate', 'quantity', 'pnl', 'exitReason'];

  readonly strategies = signal<StrategyInfo[]>([]);
  readonly selected = signal<StrategyInfo | null>(null);
  readonly busy = signal(false);
  readonly result = signal<BacktestDetail | null>(null);

  readonly entryRules = signal<RuleDraft[]>([{ left: 'sma_20', op: 'crosses_above', right: 'sma_50' }]);
  readonly exitRules = signal<RuleDraft[]>([]);

  name = '';
  description = '';
  stopLossPct: number | null = 5;
  takeProfitPct: number | null = null;
  maxHoldingDays: number | null = null;
  atrStopMult: number | null = null;
  atrTrail = false;

  fromDate = '';
  toDate = '';
  capital = 1_000_000;
  maxPositions = 5;
  commissionPct = 0.05;
  timeframe: 'daily' | 'weekly' | 'monthly' = 'daily';
  presetName = '';

  ngOnInit(): void {
    this.reload();
  }

  selectedPreset(): StrategyPreset | undefined {
    return this.presets.find((p) => p.name === this.presetName);
  }

  applyPreset(name: string): void {
    const preset = this.presets.find((p) => p.name === name);
    if (!preset) return;
    this.selected.set(null);
    this.result.set(null);
    this.name = preset.name;
    this.description = preset.description;
    this.entryRules.set(preset.definition.entry.map(this.toDraft));
    this.exitRules.set((preset.definition.exit ?? []).map(this.toDraft));
    this.stopLossPct = preset.definition.stop_loss_pct ?? null;
    this.takeProfitPct = preset.definition.take_profit_pct ?? null;
    this.maxHoldingDays = preset.definition.max_holding_days ?? null;
    this.atrStopMult = preset.definition.atr_stop_mult ?? null;
    this.atrTrail = preset.definition.atr_trail ?? false;
  }

  refreshData(): void {
    this.busy.set(true);
    this.api.triggerDailySync().subscribe({
      next: () => {
        this.busy.set(false);
        this.snackBar.open('Latest prices synced from the internet', undefined, { duration: 3000 });
      },
      error: () => {
        this.busy.set(false);
        this.snackBar.open('Sync failed — check the data service', 'Dismiss', { duration: 5000 });
      },
    });
  }

  reload(selectId?: number): void {
    this.api.listStrategies().subscribe({
      next: (list) => {
        this.strategies.set(list);
        if (selectId) {
          const found = list.find((s) => s.id === selectId);
          if (found) this.select(found);
        }
      },
      error: () => this.snackBar.open('Failed to load strategies', 'Dismiss', { duration: 4000 }),
    });
  }

  newStrategy(): void {
    this.selected.set(null);
    this.result.set(null);
    this.presetName = '';
    this.name = '';
    this.description = '';
    this.entryRules.set([{ left: 'sma_20', op: 'crosses_above', right: 'sma_50' }]);
    this.exitRules.set([]);
    this.stopLossPct = 5;
    this.takeProfitPct = null;
    this.maxHoldingDays = null;
    this.atrStopMult = null;
    this.atrTrail = false;
  }

  select(s: StrategyInfo): void {
    this.selected.set(s);
    this.result.set(null);
    this.name = s.name;
    this.description = s.description ?? '';
    this.entryRules.set(s.definition.entry.map(this.toDraft));
    this.exitRules.set((s.definition.exit ?? []).map(this.toDraft));
    this.stopLossPct = s.definition.stop_loss_pct ?? null;
    this.takeProfitPct = s.definition.take_profit_pct ?? null;
    this.maxHoldingDays = s.definition.max_holding_days ?? null;
    this.atrStopMult = s.definition.atr_stop_mult ?? null;
    this.atrTrail = s.definition.atr_trail ?? false;
  }

  addRule(target: typeof this.entryRules): void {
    target.update((rules) => [...rules, { left: 'rsi_14', op: 'lt', right: '30' }]);
  }

  removeRule(target: typeof this.entryRules, index: number): void {
    target.update((rules) => rules.filter((_, i) => i !== index));
  }

  save(): void {
    const definition = this.buildDefinition();
    this.busy.set(true);
    const call = this.selected()
      ? this.api.updateStrategy(this.selected()!.id, this.name, this.description || null, definition)
      : this.api.createStrategy(this.name, this.description || null, definition);
    call.subscribe({
      next: (saved) => {
        this.busy.set(false);
        this.snackBar.open('Strategy saved', undefined, { duration: 2500 });
        this.reload(saved.id);
      },
      error: (err) => {
        this.busy.set(false);
        this.snackBar.open(err?.error?.message ?? 'Save failed', 'Dismiss', { duration: 6000 });
      },
    });
  }

  remove(): void {
    const current = this.selected();
    if (!current) return;
    this.busy.set(true);
    this.api.deleteStrategy(current.id).subscribe({
      next: () => { this.busy.set(false); this.newStrategy(); this.reload(); },
      error: () => { this.busy.set(false); this.snackBar.open('Delete failed', 'Dismiss', { duration: 4000 }); },
    });
  }

  run(): void {
    const current = this.selected();
    if (!current) return;
    this.busy.set(true);
    this.result.set(null);
    this.api.runBacktest(current.id, {
      from: this.fromDate || undefined,
      to: this.toDate || undefined,
      initial_capital: this.capital,
      max_positions: this.maxPositions,
      commission_pct: this.commissionPct,
      timeframe: this.timeframe,
    }).subscribe({
      next: (summary) => {
        this.api.getBacktest(summary.backtest_id).subscribe({
          next: (detail) => { this.result.set(detail); this.busy.set(false); },
          error: () => { this.busy.set(false); },
        });
      },
      error: (err) => {
        this.busy.set(false);
        this.snackBar.open(err?.error?.message ?? 'Backtest failed', 'Dismiss', { duration: 6000 });
      },
    });
  }

  private toDraft(rule: StrategyRule): RuleDraft {
    return { left: rule.left, op: rule.op, right: String(rule.right) };
  }

  private buildDefinition(): StrategyDefinition {
    const toRule = (d: RuleDraft): StrategyRule => {
      const right = d.right.trim();
      return {
        left: d.left.trim(),
        op: d.op as StrategyRule['op'],
        right: right !== '' && !isNaN(Number(right)) ? Number(right) : right,
      };
    };
    return {
      entry: this.entryRules().filter((r) => r.left && r.right !== '').map(toRule),
      exit: this.exitRules().filter((r) => r.left && r.right !== '').map(toRule),
      stop_loss_pct: this.stopLossPct || null,
      take_profit_pct: this.takeProfitPct || null,
      max_holding_days: this.maxHoldingDays || null,
      atr_stop_mult: this.atrStopMult || null,
      atr_trail: this.atrStopMult ? this.atrTrail : null,
    };
  }
}
