import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatAutocompleteModule, MatAutocompleteSelectedEvent } from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { debounceTime, distinctUntilChanged, filter, switchMap } from 'rxjs';
import { toSignal } from '@angular/core/rxjs-interop';

import { FundamentalsData, StatementRow, SymbolInfo } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

interface RatioCard {
  label: string;
  value: string;
  hint?: string;
}

const CRORE = 1e7;

@Component({
  selector: 'app-fundamentals-page',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, MatFormFieldModule, MatInputModule,
            MatAutocompleteModule, MatCardModule, MatButtonModule, MatIconModule,
            MatProgressSpinnerModule, MatSnackBarModule, MatTableModule,
            MatButtonToggleModule, RouterLink],
  template: `
    <div class="controls">
      <mat-form-field appearance="outline" class="search">
        <mat-label>Search symbol</mat-label>
        <input matInput placeholder="e.g. TCS" [formControl]="searchControl"
               [matAutocomplete]="auto">
        <mat-icon matSuffix>search</mat-icon>
        <mat-autocomplete #auto="matAutocomplete" (optionSelected)="onSymbolSelected($event)">
          @for (s of suggestions(); track s.id) {
            <mat-option [value]="s.ticker">
              <span class="ticker">{{ s.ticker }}</span>
              <span class="name">{{ s.name }} · {{ s.sector }}</span>
            </mat-option>
          }
        </mat-autocomplete>
      </mat-form-field>

      @if (data(); as d) {
        <a mat-stroked-button [routerLink]="['/chart']" [queryParams]="{ ticker: d.ticker }">
          <mat-icon>show_chart</mat-icon> Chart
        </a>
        <button mat-stroked-button (click)="refresh()" [disabled]="refreshing()">
          <mat-icon>cloud_download</mat-icon>
          {{ refreshing() ? 'Fetching from Yahoo…' : 'Refresh fundamentals' }}
        </button>
      }
    </div>

    @if (loading()) {
      <div class="spinner"><mat-spinner diameter="36" /></div>
    }

    @if (data(); as d) {
      <h2>{{ d.name }} <span class="sector-tag">{{ d.sector }}</span></h2>

      @if (d.ratios; as r) {
        <div class="cards">
          @for (card of ratioCards(); track card.label) {
            <mat-card appearance="outlined" class="ratio-card">
              <span class="ratio-value">{{ card.value }}</span>
              <span class="ratio-label">{{ card.label }}</span>
            </mat-card>
          }
        </div>
        <p class="asof">Ratios as of {{ r.computedAt | date: 'medium' }} (Yahoo Finance)</p>
      } @else {
        <mat-card appearance="outlined" class="empty-card">
          <p>No fundamentals stored yet for {{ d.ticker }}.</p>
          <button mat-flat-button color="primary" (click)="refresh()" [disabled]="refreshing()">
            {{ refreshing() ? 'Fetching…' : 'Fetch now' }}
          </button>
        </mat-card>
      }

      @if (d.annual.length || d.quarterly.length) {
        <div class="stmt-header">
          <h3>Financial statements <span class="crore-hint">(₹ crore)</span></h3>
          <mat-button-toggle-group [value]="periodType()" (change)="periodType.set($event.value)">
            <mat-button-toggle value="annual">Annual</mat-button-toggle>
            <mat-button-toggle value="quarterly">Quarterly</mat-button-toggle>
          </mat-button-toggle-group>
        </div>

        <table mat-table [dataSource]="statements()" class="stmt-table">
          <ng-container matColumnDef="periodEnd">
            <th mat-header-cell *matHeaderCellDef>Period</th>
            <td mat-cell *matCellDef="let s">{{ s.periodEnd | date: 'MMM yyyy' }}</td>
          </ng-container>
          @for (col of stmtCols; track col.key) {
            <ng-container [matColumnDef]="col.key">
              <th mat-header-cell *matHeaderCellDef>{{ col.label }}</th>
              <td mat-cell *matCellDef="let s"
                  [class.down]="col.signed && s[col.key] < 0">
                {{ toCrore(s[col.key]) }}
              </td>
            </ng-container>
          }
          <tr mat-header-row *matHeaderRowDef="stmtColumnKeys"></tr>
          <tr mat-row *matRowDef="let s; columns: stmtColumnKeys"></tr>
        </table>
      }
    } @else if (!loading()) {
      <p class="hint">Search for a symbol to see its fundamentals.</p>
    }
  `,
  styles: `
    .controls { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
    .search { min-width: 320px; }
    .ticker { font-weight: 600; margin-right: 8px; }
    .name { opacity: 0.6; font-size: 12px; }
    h2 { font-weight: 500; margin: 8px 0 16px; }
    .sector-tag { font-size: 13px; opacity: 0.6; font-weight: 400; margin-left: 8px; }
    .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
             gap: 12px; }
    .ratio-card { padding: 14px; display: flex; flex-direction: column; gap: 4px; }
    .ratio-value { font-size: 20px; font-weight: 600; }
    .ratio-label { font-size: 12px; opacity: 0.65; }
    .asof { font-size: 12px; opacity: 0.5; margin: 10px 0 20px; }
    .empty-card { padding: 20px; display: flex; gap: 16px; align-items: center; }
    .stmt-header { display: flex; align-items: center; gap: 16px; margin-top: 8px; }
    .crore-hint { font-size: 12px; opacity: 0.6; font-weight: 400; }
    .stmt-table { width: 100%; margin-top: 8px; }
    .down { color: #ef5350; }
    .spinner { display: flex; justify-content: center; padding: 24px; }
    .hint { opacity: 0.6; margin-top: 16px; }
  `,
})
export class FundamentalsPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);

  readonly searchControl = new FormControl('', { nonNullable: true });
  readonly data = signal<FundamentalsData | null>(null);
  readonly loading = signal(false);
  readonly refreshing = signal(false);
  readonly periodType = signal<'annual' | 'quarterly'>('annual');

  readonly stmtCols = [
    { key: 'revenue', label: 'Revenue', signed: false },
    { key: 'operatingIncome', label: 'Op. income', signed: true },
    { key: 'netIncome', label: 'Net income', signed: true },
    { key: 'eps', label: 'EPS (₹)', signed: true },
    { key: 'totalAssets', label: 'Assets', signed: false },
    { key: 'shareholdersEquity', label: 'Equity', signed: false },
    { key: 'operatingCashFlow', label: 'Op. CF', signed: true },
    { key: 'freeCashFlow', label: 'FCF', signed: true },
  ] as const;
  readonly stmtColumnKeys = ['periodEnd', ...this.stmtCols.map((c) => c.key)];

  readonly statements = computed<StatementRow[]>(() => {
    const d = this.data();
    if (!d) return [];
    return this.periodType() === 'annual' ? d.annual : d.quarterly;
  });

  readonly ratioCards = computed<RatioCard[]>(() => {
    const r = this.data()?.ratios;
    if (!r) return [];
    const n = (v: number | null, digits = 2, suffix = '') =>
      v === null || v === undefined ? '—' : `${v.toFixed(digits)}${suffix}`;
    const cap = r.marketCap === null ? '—' : `₹${(r.marketCap / CRORE).toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr`;
    return [
      { label: 'Market cap', value: cap },
      { label: 'P/E (trailing)', value: n(r.peTrailing) },
      { label: 'P/E (forward)', value: n(r.peForward) },
      { label: 'P/B', value: n(r.pb) },
      { label: 'P/S', value: n(r.ps) },
      { label: 'Dividend yield', value: n(r.dividendYieldPct, 2, '%') },
      { label: 'ROE', value: n(r.roePct, 1, '%') },
      { label: 'Debt / Equity', value: n(r.debtToEquity) },
      { label: 'Profit margin', value: n(r.profitMarginPct, 1, '%') },
      { label: 'Operating margin', value: n(r.operatingMarginPct, 1, '%') },
      { label: 'Revenue growth', value: n(r.revenueGrowthPct, 1, '%') },
      { label: 'Earnings growth', value: n(r.earningsGrowthPct, 1, '%') },
      { label: 'EPS (trailing)', value: n(r.epsTrailing, 2, ' ₹') },
      { label: 'Book value', value: n(r.bookValue, 0, ' ₹') },
      { label: 'Beta', value: n(r.beta) },
    ];
  });

  readonly suggestions = toSignal(
    this.searchControl.valueChanges.pipe(
      debounceTime(250),
      distinctUntilChanged(),
      filter((q) => q.length >= 1),
      switchMap((q) => this.api.searchSymbols(q)),
    ),
    { initialValue: [] as SymbolInfo[] },
  );

  ngOnInit(): void {
    const ticker = this.route.snapshot.queryParamMap.get('ticker');
    if (ticker) {
      this.searchControl.setValue(ticker, { emitEvent: false });
      this.load(ticker.toUpperCase());
    }
  }

  onSymbolSelected(event: MatAutocompleteSelectedEvent): void {
    const ticker = event.option.value as string;
    this.router.navigate([], { queryParams: { ticker }, queryParamsHandling: 'merge' });
    this.load(ticker);
  }

  refresh(): void {
    const ticker = this.data()?.ticker;
    if (!ticker) return;
    this.refreshing.set(true);
    this.api.triggerFundamentalsRefresh([ticker]).subscribe({
      next: () => { this.refreshing.set(false); this.load(ticker); },
      error: () => {
        this.refreshing.set(false);
        this.snackBar.open('Fundamentals refresh failed (Yahoo reachable?)', 'Dismiss', { duration: 5000 });
      },
    });
  }

  toCrore(value: number | null): string {
    if (value === null || value === undefined) return '—';
    if (Math.abs(value) < 1000) return value.toFixed(2);   // per-share figures like EPS
    return (value / CRORE).toLocaleString('en-IN', { maximumFractionDigits: 0 });
  }

  private load(ticker: string): void {
    this.loading.set(true);
    this.api.getFundamentals(ticker).subscribe({
      next: (d) => { this.data.set(d); this.loading.set(false); },
      error: () => {
        this.loading.set(false);
        this.snackBar.open(`Failed to load fundamentals for ${ticker}`, 'Dismiss', { duration: 4000 });
      },
    });
  }
}
