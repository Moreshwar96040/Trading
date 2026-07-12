import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatAutocompleteModule, MatAutocompleteSelectedEvent } from '@angular/material/autocomplete';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCardModule } from '@angular/material/card';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { provideNativeDateAdapter } from '@angular/material/core';
import { ActivatedRoute } from '@angular/router';
import { LineData, Time } from 'lightweight-charts';
import { debounceTime, distinctUntilChanged, filter, map, switchMap } from 'rxjs';
import { toSignal } from '@angular/core/rxjs-interop';

import {
  Candle, IndicatorSeries, Quote, SymbolInfo,
} from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';
import { CandlestickChartComponent, OverlayLine } from './candlestick-chart.component';
import { RsiChartComponent } from './rsi-chart.component';

type RangeKey = '3M' | '6M' | '1Y' | '2Y' | 'Custom';
const RANGE_DAYS: Record<Exclude<RangeKey, 'Custom'>, number> = { '3M': 92, '6M': 183, '1Y': 365, '2Y': 730 };

const OVERLAY_STYLES: Record<string, { color: string; label: string }> = {
  sma_20: { color: '#ffb74d', label: 'SMA 20' },
  sma_50: { color: '#4fc3f7', label: 'SMA 50' },
  sma_200: { color: '#f06292', label: 'SMA 200' },
  bb_upper: { color: 'rgba(144, 164, 174, 0.7)', label: 'BB' },
  bb_lower: { color: 'rgba(144, 164, 174, 0.7)', label: 'BB' },
  ichimoku_tenkan: { color: '#26c6da', label: 'Tenkan' },
  ichimoku_kijun: { color: '#ab47bc', label: 'Kijun' },
  ichimoku_senkou_a: { color: 'rgba(38, 166, 154, 0.9)', label: 'Senkou A' },
  ichimoku_senkou_b: { color: 'rgba(239, 83, 80, 0.9)', label: 'Senkou B' },
  support: { color: 'rgba(38, 166, 154, 0.5)', label: 'Support' },
  resistance: { color: 'rgba(239, 83, 80, 0.5)', label: 'Resistance' },
};

/** Sentinel exchange value used to flag the "Add from Yahoo Finance" autocomplete entry. */
const YAHOO_SENTINEL = 'YAHOO';

@Component({
  selector: 'app-chart-page',
  standalone: true,
  providers: [provideNativeDateAdapter()],
  imports: [CommonModule, ReactiveFormsModule, MatFormFieldModule, MatInputModule,
            MatAutocompleteModule, MatCardModule, MatButtonToggleModule,
            MatIconModule, MatProgressSpinnerModule, MatSnackBarModule,
            MatDatepickerModule,
            CandlestickChartComponent, RsiChartComponent],
  template: `
    <div class="controls">
      <mat-form-field appearance="outline" class="search">
        <mat-label>Search symbol</mat-label>
        <input matInput placeholder="e.g. RELIANCE, INFY" [formControl]="searchControl"
               [matAutocomplete]="auto">
        <mat-icon matSuffix>search</mat-icon>
        <mat-autocomplete #auto="matAutocomplete" (optionSelected)="onSymbolSelected($event)">
          @for (s of suggestions(); track s.ticker) {
            @if (s.exchange === YAHOO_SENTINEL) {
              <mat-option [value]="s.ticker" class="yahoo-option">
                <mat-icon class="yahoo-icon">add_circle_outline</mat-icon>
                <span>Add "{{ s.ticker }}" from Yahoo Finance</span>
              </mat-option>
            } @else {
              <mat-option [value]="s.ticker">
                <span class="ticker">{{ s.ticker }}</span>
                <span class="name">{{ s.name }} · {{ s.sector }}</span>
              </mat-option>
            }
          }
        </mat-autocomplete>
      </mat-form-field>

      <mat-button-toggle-group [value]="range()" (change)="onRangeChange($event.value)">
        @for (r of rangeKeys; track r) {
          <mat-button-toggle [value]="r">{{ r }}</mat-button-toggle>
        }
      </mat-button-toggle-group>

      @if (range() === 'Custom') {
        <mat-form-field appearance="outline" class="date-field">
          <mat-label>From</mat-label>
          <input matInput [matDatepicker]="fromPicker" [value]="fromDate()"
                 (dateChange)="onFromDateChange($event.value)">
          <mat-datepicker-toggle matSuffix [for]="fromPicker" />
          <mat-datepicker #fromPicker />
        </mat-form-field>
        <mat-form-field appearance="outline" class="date-field">
          <mat-label>To</mat-label>
          <input matInput [matDatepicker]="toPicker" [value]="toDate()"
                 (dateChange)="onToDateChange($event.value)">
          <mat-datepicker-toggle matSuffix [for]="toPicker" />
          <mat-datepicker #toPicker />
        </mat-form-field>
      }

      <mat-button-toggle-group multiple [value]="activeOverlays()"
                               (change)="onOverlaysChange($event.value)">
        <mat-button-toggle value="sma_20">SMA20</mat-button-toggle>
        <mat-button-toggle value="sma_50">SMA50</mat-button-toggle>
        <mat-button-toggle value="sma_200">SMA200</mat-button-toggle>
        <mat-button-toggle value="bb">Bollinger</mat-button-toggle>
        <mat-button-toggle value="ichimoku">Ichimoku</mat-button-toggle>
        <mat-button-toggle value="sr">S/R</mat-button-toggle>
        <mat-button-toggle value="rsi">RSI</mat-button-toggle>
      </mat-button-toggle-group>
    </div>

    @if (quote(); as q) {
      <mat-card class="quote-card" appearance="outlined">
        <span class="quote-ticker">{{ q.ticker }}</span>
        <span class="quote-price">₹{{ q.price | number: '1.2-2' }}</span>
        @if (q.change !== null) {
          <span class="quote-change" [class.up]="q.change >= 0" [class.down]="q.change < 0">
            {{ q.change >= 0 ? '+' : '' }}{{ q.change | number: '1.2-2' }}
            ({{ q.change_pct | number: '1.2-2' }}%)
          </span>
        }
        <span class="quote-asof">15-min delayed · {{ q.as_of | date: 'medium' }}</span>
      </mat-card>
    }

    @if (loading() || seeding()) {
      <div class="spinner">
        <mat-spinner diameter="36" />
        @if (seeding()) {
          <span class="seed-label">Fetching data from Yahoo Finance…</span>
        }
      </div>
    }

    @if (selectedTicker()) {
      <mat-card appearance="outlined" class="chart-card">
        <app-candlestick-chart [candles]="candles()" [overlays]="overlayLines()" />
        @if (showRsi() && rsiPoints().length) {
          <app-rsi-chart [points]="rsiPoints()" />
        }
      </mat-card>
    } @else if (!loading() && !seeding()) {
      <p class="hint">Search for any NSE symbol above to load its chart.</p>
    }
  `,
  styles: `
    .controls { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
    .search { min-width: 320px; }
    .date-field { width: 160px; }
    .ticker { font-weight: 600; margin-right: 8px; }
    .name { opacity: 0.6; font-size: 12px; }
    .yahoo-option { font-style: italic; opacity: 0.85; }
    .yahoo-icon { font-size: 18px; vertical-align: middle; margin-right: 6px; color: #4fc3f7; }
    .quote-card { display: flex; flex-direction: row; gap: 16px; align-items: baseline;
                  padding: 12px 16px; margin-bottom: 16px; }
    .quote-ticker { font-weight: 600; font-size: 18px; }
    .quote-price { font-size: 24px; font-weight: 500; }
    .quote-change.up { color: #26a69a; }
    .quote-change.down { color: #ef5350; }
    .quote-asof { opacity: 0.5; font-size: 12px; margin-left: auto; }
    .chart-card { padding: 8px; }
    .spinner { display: flex; align-items: center; gap: 12px; justify-content: center; padding: 24px; }
    .seed-label { opacity: 0.7; font-size: 14px; }
    .hint { opacity: 0.6; }
  `,
})
export class ChartPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly route = inject(ActivatedRoute);
  private readonly snackBar = inject(MatSnackBar);

  readonly YAHOO_SENTINEL = YAHOO_SENTINEL;
  readonly rangeKeys: RangeKey[] = ['3M', '6M', '1Y', '2Y', 'Custom'];
  readonly searchControl = new FormControl('', { nonNullable: true });

  readonly selectedTicker = signal<string | null>(null);
  readonly range = signal<RangeKey>('1Y');
  readonly fromDate = signal<Date>(new Date(Date.now() - RANGE_DAYS['1Y'] * 86_400_000));
  readonly toDate = signal<Date>(new Date());
  readonly candles = signal<Candle[]>([]);
  readonly quote = signal<Quote | null>(null);
  readonly indicators = signal<IndicatorSeries | null>(null);
  readonly activeOverlays = signal<string[]>(['sma_50', 'sma_200']);
  readonly loading = signal(false);
  readonly seeding = signal(false);

  readonly showRsi = computed(() => this.activeOverlays().includes('rsi'));

  readonly overlayLines = computed<OverlayLine[]>(() => {
    const ind = this.indicators();
    if (!ind) return [];
    const active = this.activeOverlays();
    const keys: string[] = [];
    for (const k of ['sma_20', 'sma_50', 'sma_200']) {
      if (active.includes(k)) keys.push(k);
    }
    if (active.includes('bb')) keys.push('bb_upper', 'bb_lower');
    if (active.includes('ichimoku')) {
      keys.push('ichimoku_tenkan', 'ichimoku_kijun', 'ichimoku_senkou_a', 'ichimoku_senkou_b');
    }
    if (active.includes('sr')) keys.push('support', 'resistance');
    return keys
      .filter((k) => ind.series[k])
      .map((k) => ({
        id: k,
        color: OVERLAY_STYLES[k].color,
        data: this.toLineData(ind.dates, ind.series[k]),
      }));
  });

  readonly rsiPoints = computed<LineData[]>(() => {
    const ind = this.indicators();
    return ind?.series['rsi_14'] ? this.toLineData(ind.dates, ind.series['rsi_14']) : [];
  });

  readonly suggestions = toSignal(
    this.searchControl.valueChanges.pipe(
      debounceTime(250),
      distinctUntilChanged(),
      filter((q) => q.length >= 1),
      switchMap((q) =>
        this.api.searchSymbols(q).pipe(
          map((results) => {
            if (results.length === 0 && q.trim().length >= 2) {
              const ticker = q.trim().toUpperCase();
              return [{
                id: -1, ticker, name: 'Add from Yahoo Finance',
                sector: null, exchange: YAHOO_SENTINEL, currency: '',
              } as SymbolInfo];
            }
            return results;
          }),
        ),
      ),
    ),
    { initialValue: [] as SymbolInfo[] },
  );

  ngOnInit(): void {
    const ticker = this.route.snapshot.queryParamMap.get('ticker');
    if (ticker) {
      this.searchControl.setValue(ticker, { emitEvent: false });
      this.selectedTicker.set(ticker.toUpperCase());
      this.loadData();
    }
  }

  onSymbolSelected(event: MatAutocompleteSelectedEvent): void {
    const ticker = (event.option.value as string).trim().toUpperCase();
    const match = this.suggestions().find((s) => s.ticker === ticker);

    if (match?.exchange === YAHOO_SENTINEL) {
      this.seeding.set(true);
      this.api.seedSymbol(ticker).subscribe({
        next: () => {
          this.seeding.set(false);
          this.selectedTicker.set(ticker);
          this.loadData();
        },
        error: () => {
          this.seeding.set(false);
          this.snackBar.open(`"${ticker}" not found on Yahoo Finance`, 'Dismiss', { duration: 5000 });
        },
      });
    } else {
      this.selectedTicker.set(ticker);
      this.loadData();
    }
  }

  onRangeChange(value: RangeKey): void {
    this.range.set(value);
    if (value !== 'Custom') {
      const to = new Date();
      const from = new Date(to.getTime() - RANGE_DAYS[value] * 86_400_000);
      this.fromDate.set(from);
      this.toDate.set(to);
      this.loadData();
    }
  }

  onFromDateChange(value: Date | null): void {
    if (value) {
      this.fromDate.set(value);
      this.loadData();
    }
  }

  onToDateChange(value: Date | null): void {
    if (value) {
      this.toDate.set(value);
      this.loadData();
    }
  }

  onOverlaysChange(value: string[]): void {
    this.activeOverlays.set(value);
  }

  private loadData(): void {
    const ticker = this.selectedTicker();
    if (!ticker) return;

    this.loading.set(true);
    const fromIso = this.isoDate(this.fromDate());
    const toIso = this.isoDate(this.toDate());

    this.api.getCandles(ticker, fromIso, toIso).subscribe({
      next: (series) => {
        this.candles.set(series.candles);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.snackBar.open(`Failed to load candles for ${ticker}`, 'Dismiss', { duration: 4000 });
      },
    });

    this.api.getIndicators(ticker, fromIso, toIso).subscribe({
      next: (ind) => this.indicators.set(ind),
      error: () => this.indicators.set(null),
    });

    this.api.getQuote(ticker).subscribe({
      next: (q) => this.quote.set(q),
      error: () => this.quote.set(null),
    });
  }

  private toLineData(dates: string[], values: (number | null)[]): LineData[] {
    const out: LineData[] = [];
    for (let i = 0; i < dates.length; i++) {
      const v = values[i];
      if (v !== null && v !== undefined) {
        out.push({ time: dates[i] as Time, value: v });
      }
    }
    return out;
  }

  private isoDate(d: Date): string {
    return d.toISOString().slice(0, 10);
  }
}
