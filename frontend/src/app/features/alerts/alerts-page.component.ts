import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormControl, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { debounceTime, distinctUntilChanged, filter, switchMap } from 'rxjs';
import { toSignal } from '@angular/core/rxjs-interop';

import { AlertInfo, SymbolInfo } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

@Component({
  selector: 'app-alerts-page',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, MatCardModule, MatButtonModule,
            MatFormFieldModule, MatInputModule, MatSelectModule, MatAutocompleteModule,
            MatIconModule, MatTableModule, MatChipsModule, MatSnackBarModule, MatTooltipModule],
  template: `
    <div class="header-row">
      <h2>Alerts</h2>
      <button mat-stroked-button (click)="evaluateNow()"
              matTooltip="Alerts also run automatically after each daily sync">
        <mat-icon>bolt</mat-icon> Check now
      </button>
    </div>

    <mat-card appearance="outlined" class="create-card">
      <h3>New alert</h3>
      <div class="row">
        <mat-form-field appearance="outline" class="w-ticker">
          <mat-label>Symbol</mat-label>
          <input matInput [formControl]="tickerControl" [matAutocomplete]="auto"
                 placeholder="RELIANCE">
          <mat-autocomplete #auto="matAutocomplete">
            @for (s of suggestions(); track s.id) {
              <mat-option [value]="s.ticker">{{ s.ticker }} — {{ s.name }}</mat-option>
            }
          </mat-autocomplete>
        </mat-form-field>

        <mat-form-field appearance="outline" class="w-field">
          <mat-label>Field</mat-label>
          <mat-select [(ngModel)]="field">
            @for (f of fields(); track f) { <mat-option [value]="f">{{ f }}</mat-option> }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline" class="w-op">
          <mat-label>Op</mat-label>
          <mat-select [(ngModel)]="op">
            @for (o of ops(); track o) { <mat-option [value]="o">{{ o }}</mat-option> }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline" class="w-value">
          <mat-label>Value</mat-label>
          <input matInput type="number" [(ngModel)]="value">
        </mat-form-field>

        <mat-form-field appearance="outline" class="w-note">
          <mat-label>Note (optional)</mat-label>
          <input matInput [(ngModel)]="note">
        </mat-form-field>

        <button mat-flat-button color="primary" (click)="create()">
          <mat-icon>add_alert</mat-icon> Create
        </button>
      </div>
    </mat-card>

    @if (alerts().length) {
      <table mat-table [dataSource]="alerts()" class="table">
        <ng-container matColumnDef="ticker">
          <th mat-header-cell *matHeaderCellDef>Ticker</th>
          <td mat-cell *matCellDef="let a"><b>{{ a.ticker }}</b></td>
        </ng-container>
        <ng-container matColumnDef="condition">
          <th mat-header-cell *matHeaderCellDef>Condition</th>
          <td mat-cell *matCellDef="let a">{{ a.field }} {{ a.op }} {{ a.value }}
            @if (a.note) { <span class="muted">· {{ a.note }}</span> }
          </td>
        </ng-container>
        <ng-container matColumnDef="status">
          <th mat-header-cell *matHeaderCellDef>Status</th>
          <td mat-cell *matCellDef="let a">
            <span class="chip" [class.triggered]="a.status === 'TRIGGERED'"
                  [class.active]="a.status === 'ACTIVE'">{{ a.status }}</span>
            @if (a.status === 'TRIGGERED') {
              <span class="muted"> at {{ a.triggeredValue }} ·
                {{ a.triggeredAt | date: 'MMM d, HH:mm' }}</span>
            }
          </td>
        </ng-container>
        <ng-container matColumnDef="actions">
          <th mat-header-cell *matHeaderCellDef></th>
          <td mat-cell *matCellDef="let a" class="actions-cell">
            @if (a.status === 'TRIGGERED') {
              <button mat-icon-button (click)="rearm(a)" matTooltip="Re-arm">
                <mat-icon>replay</mat-icon>
              </button>
            }
            <button mat-icon-button (click)="remove(a)" matTooltip="Delete">
              <mat-icon>delete</mat-icon>
            </button>
          </td>
        </ng-container>
        <tr mat-header-row *matHeaderRowDef="columns"></tr>
        <tr mat-row *matRowDef="let a; columns: columns"></tr>
      </table>
    } @else {
      <p class="muted">No alerts yet — create one above. Alerts are checked after every
        daily data sync (18:30 IST) and whenever you press "Check now".</p>
    }
  `,
  styles: `
    h2, h3 { font-weight: 500; }
    .header-row { display: flex; justify-content: space-between; align-items: center; }
    .create-card { padding: 16px; margin-bottom: 16px; }
    .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    .w-ticker { min-width: 220px; }
    .w-field { width: 190px; }
    .w-op { width: 100px; }
    .w-value { width: 130px; }
    .w-note { flex: 1; min-width: 160px; }
    .table { width: 100%; }
    .chip { padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
    .chip.active { background: rgba(79, 195, 247, 0.2); color: #4fc3f7; }
    .chip.triggered { background: rgba(255, 183, 77, 0.2); color: #ffb74d; }
    .actions-cell { text-align: right; }
    .muted { opacity: 0.6; font-size: 12px; }
  `,
})
export class AlertsPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly snackBar = inject(MatSnackBar);

  readonly columns = ['ticker', 'condition', 'status', 'actions'];
  readonly alerts = signal<AlertInfo[]>([]);
  readonly fields = signal<string[]>(['close', 'rsi_14', 'volume_ratio', 'pe_trailing']);
  readonly ops = signal<string[]>(['gt', 'gte', 'lt', 'lte', 'eq']);

  readonly tickerControl = new FormControl('', { nonNullable: true });
  field = 'close';
  op = 'gt';
  value: number | null = null;
  note = '';

  readonly suggestions = toSignal(
    this.tickerControl.valueChanges.pipe(
      debounceTime(250),
      distinctUntilChanged(),
      filter((q) => q.length >= 1),
      switchMap((q) => this.api.searchSymbols(q)),
    ),
    { initialValue: [] as SymbolInfo[] },
  );

  ngOnInit(): void {
    this.reload();
    this.api.getScreenerFields().subscribe({
      next: (meta) => {
        this.fields.set(meta.numeric);
        this.ops.set(meta.ops);
      },
      error: () => {},   // fall back to the built-in defaults
    });
  }

  reload(): void {
    this.api.listAlerts().subscribe({
      next: (list) => this.alerts.set(list),
      error: () => this.snackBar.open('Failed to load alerts', 'Dismiss', { duration: 4000 }),
    });
  }

  create(): void {
    const ticker = this.tickerControl.value.trim().toUpperCase();
    if (!ticker || this.value === null) {
      this.snackBar.open('Symbol and value are required', 'Dismiss', { duration: 3000 });
      return;
    }
    this.api.createAlert(ticker, this.field, this.op, this.value, this.note || undefined)
      .subscribe({
        next: () => {
          this.snackBar.open('Alert created', undefined, { duration: 2500 });
          this.value = null;
          this.note = '';
          this.reload();
        },
        error: (err) => this.snackBar.open(err?.error?.message ?? 'Create failed', 'Dismiss', { duration: 5000 }),
      });
  }

  evaluateNow(): void {
    this.api.evaluateAlerts().subscribe({
      next: (r) => {
        this.snackBar.open(`Checked ${r.checked} alert(s), ${r.triggered} triggered`,
          undefined, { duration: 3500 });
        this.reload();
      },
      error: (err) => this.snackBar.open(err?.error?.message ?? 'Evaluation failed', 'Dismiss', { duration: 5000 }),
    });
  }

  rearm(alert: AlertInfo): void {
    this.api.rearmAlert(alert.id).subscribe({ next: () => this.reload() });
  }

  remove(alert: AlertInfo): void {
    this.api.deleteAlert(alert.id).subscribe({ next: () => this.reload() });
  }
}
