import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router } from '@angular/router';

import {
  ScreenCondition, ScreenRow, ScreenerFieldsMeta,
} from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';
import { SCREENER_PRESETS, ScreenerPreset } from './screener-presets';

/** Editable condition row: value/ref entered as one string, resolved on run. */
interface ConditionDraft {
  field: string;
  op: string;
  operand: string; // number → value, field name → ref
}

@Component({
  selector: 'app-screener-page',
  standalone: true,
  imports: [CommonModule, FormsModule, MatCardModule, MatChipsModule, MatFormFieldModule,
            MatSelectModule, MatInputModule, MatButtonModule, MatIconModule, MatTableModule,
            MatProgressSpinnerModule, MatSnackBarModule, MatTooltipModule],
  template: `
    <h2>Stock Screener</h2>

    <mat-chip-set class="presets">
      @for (p of presets; track p.name) {
        <mat-chip (click)="applyPreset(p)" [matTooltip]="p.description">{{ p.name }}</mat-chip>
      }
    </mat-chip-set>

    <mat-card appearance="outlined" class="builder">
      @for (c of drafts(); track $index) {
        <div class="condition-row">
          <mat-form-field appearance="outline" class="w-field">
            <mat-label>Field</mat-label>
            <mat-select [(ngModel)]="c.field">
              @for (f of allFields(); track f) {
                <mat-option [value]="f">{{ f }}</mat-option>
              }
            </mat-select>
          </mat-form-field>

          <mat-form-field appearance="outline" class="w-op">
            <mat-label>Op</mat-label>
            <mat-select [(ngModel)]="c.op">
              @for (o of ops(); track o) {
                <mat-option [value]="o">{{ o }}</mat-option>
              }
            </mat-select>
          </mat-form-field>

          <mat-form-field appearance="outline" class="w-operand">
            <mat-label>Value or field</mat-label>
            <input matInput [(ngModel)]="c.operand" placeholder="30 · sma_200 · IT">
          </mat-form-field>

          <button mat-icon-button (click)="removeCondition($index)" aria-label="Remove">
            <mat-icon>close</mat-icon>
          </button>
        </div>
      }

      <div class="actions">
        <button mat-stroked-button (click)="addCondition()">
          <mat-icon>add</mat-icon> Condition
        </button>
        <button mat-flat-button color="primary" (click)="run()" [disabled]="loading()">
          <mat-icon>filter_alt</mat-icon> Run screen
        </button>
        <button mat-button (click)="refreshSnapshots()" matTooltip="Recompute indicator snapshots from latest data">
          <mat-icon>refresh</mat-icon> Refresh data
        </button>
      </div>
    </mat-card>

    @if (loading()) {
      <div class="spinner"><mat-spinner diameter="36" /></div>
    } @else if (ran()) {
      <p class="count">{{ rows().length }} match(es)</p>
      <table mat-table [dataSource]="rows()" class="results">
        @for (col of columns; track col.key) {
          <ng-container [matColumnDef]="col.key">
            <th mat-header-cell *matHeaderCellDef>{{ col.label }}</th>
            <td mat-cell *matCellDef="let r"
                [class.up]="col.signed && r[col.key] > 0"
                [class.down]="col.signed && r[col.key] < 0">
              <!-- A blank "TK age" means no live bullish cross (null), not zero. -->
              {{ col.numeric ? (r[col.key] | number: '1.0-2') : r[col.key] }}
            </td>
          </ng-container>
        }
        <tr mat-header-row *matHeaderRowDef="columnKeys"></tr>
        <tr mat-row *matRowDef="let r; columns: columnKeys" class="row"
            (click)="openChart(r)"></tr>
      </table>
    }
  `,
  styles: `
    h2 { font-weight: 500; margin: 0 0 12px; }
    .presets { margin-bottom: 12px; }
    .presets mat-chip { cursor: pointer; }
    .builder { padding: 16px; margin-bottom: 16px; }
    .condition-row { display: flex; gap: 12px; align-items: center; }
    .w-field { width: 220px; }
    .w-op { width: 90px; }
    .w-operand { width: 180px; }
    .actions { display: flex; gap: 12px; }
    .count { opacity: 0.7; }
    .results { width: 100%; }
    .row { cursor: pointer; }
    .row:hover { background: var(--mat-sys-surface-container-high); }
    .up { color: #26a69a; }
    .down { color: #ef5350; }
    .spinner { display: flex; justify-content: center; padding: 24px; }
  `,
})
export class ScreenerPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);

  readonly presets = SCREENER_PRESETS;
  readonly columns = [
    { key: 'ticker', label: 'Ticker', numeric: false, signed: false },
    { key: 'name', label: 'Name', numeric: false, signed: false },
    { key: 'sector', label: 'Sector', numeric: false, signed: false },
    { key: 'close', label: 'Close', numeric: true, signed: false },
    { key: 'change1dPct', label: '1D %', numeric: true, signed: true },
    { key: 'rsi14', label: 'RSI', numeric: true, signed: false },
    { key: 'volumeRatio', label: 'Vol×', numeric: true, signed: false },
    { key: 'pctFrom52wHigh', label: '52wH %', numeric: true, signed: true },
    { key: 'return1mPct', label: '1M %', numeric: true, signed: true },
    { key: 'return3mPct', label: '3M %', numeric: true, signed: true },
    { key: 'return1yPct', label: '1Y %', numeric: true, signed: true },
    // Ichimoku: "TK age" = days since blue crossed above red (— when bearish),
    // "Cloud %" = how far price sits above the cloud top.
    { key: 'tkCrossAgeDays', label: 'TK age', numeric: true, signed: false },
    { key: 'pctAboveCloud', label: 'Cloud %', numeric: true, signed: true },
  ] as const;
  readonly columnKeys = this.columns.map((c) => c.key);

  readonly drafts = signal<ConditionDraft[]>([{ field: 'rsi_14', op: 'lt', operand: '30' }]);
  readonly rows = signal<ScreenRow[]>([]);
  readonly loading = signal(false);
  readonly ran = signal(false);
  readonly numericFields = signal<string[]>([]);
  readonly allFields = signal<string[]>([]);
  readonly ops = signal<string[]>(['gt', 'gte', 'lt', 'lte', 'eq']);

  ngOnInit(): void {
    this.api.getScreenerFields().subscribe({
      next: (meta: ScreenerFieldsMeta) => {
        this.numericFields.set(meta.numeric);
        this.allFields.set([...meta.numeric, ...meta.string]);
        this.ops.set(meta.ops);
      },
      error: () => this.snackBar.open('Failed to load screener fields', 'Dismiss', { duration: 4000 }),
    });
  }

  applyPreset(preset: ScreenerPreset): void {
    this.drafts.set(preset.conditions.map((c) => ({
      field: c.field, op: c.op,
      operand: c.ref ?? String(c.value ?? ''),
    })));
    this.run();
  }

  addCondition(): void {
    this.drafts.update((d) => [...d, { field: 'close', op: 'gt', operand: '' }]);
  }

  removeCondition(index: number): void {
    this.drafts.update((d) => d.filter((_, i) => i !== index));
  }

  run(): void {
    const conditions: ScreenCondition[] = [];
    for (const d of this.drafts()) {
      const operand = d.operand.trim();
      if (!d.field || !operand) continue;
      if (this.numericFields().includes(operand)) {
        conditions.push({ field: d.field, op: d.op as ScreenCondition['op'], ref: operand });
      } else if (!isNaN(Number(operand))) {
        conditions.push({ field: d.field, op: d.op as ScreenCondition['op'], value: Number(operand) });
      } else {
        conditions.push({ field: d.field, op: d.op as ScreenCondition['op'], value: operand });
      }
    }

    this.loading.set(true);
    this.api.runScreen({ conditions, sortBy: 'rsi_14', sortDir: 'asc' }).subscribe({
      next: (rows) => {
        this.rows.set(rows);
        this.loading.set(false);
        this.ran.set(true);
      },
      error: (err) => {
        this.loading.set(false);
        const msg = err?.error?.message ?? 'Screen failed';
        this.snackBar.open(msg, 'Dismiss', { duration: 5000 });
      },
    });
  }

  refreshSnapshots(): void {
    this.loading.set(true);
    this.api.triggerSnapshotRefresh().subscribe({
      next: () => { this.loading.set(false); this.snackBar.open('Snapshots refreshed', undefined, { duration: 2500 }); this.run(); },
      error: () => { this.loading.set(false); this.snackBar.open('Snapshot refresh failed', 'Dismiss', { duration: 4000 }); },
    });
  }

  openChart(row: ScreenRow): void {
    this.router.navigate(['/chart'], { queryParams: { ticker: row.ticker } });
  }
}
