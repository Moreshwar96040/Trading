import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';

import { DataHealth } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

/**
 * Data Health: every score in the app is only as good as the data under it.
 * One compact strip shows the freshness of each source; stale ones turn amber.
 */
@Component({
  selector: 'app-data-health-card',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule, MatIconModule,
            MatSnackBarModule, MatTooltipModule],
  template: `
    @if (health(); as h) {
      <mat-card appearance="outlined" class="dh-card">
        <mat-icon class="dh-icon">monitor_heart</mat-icon>
        <div class="chips">
          <span class="chip" [class.stale]="isStale(h.daily.last_bar, 4)"
                [matTooltip]="h.daily.rows + ' bars stored since ' + h.daily.first_bar">
            prices · {{ h.daily.last_bar || 'never' }}</span>
          <span class="chip" [class.stale]="isStale(h.snapshot.as_of, 4)"
                matTooltip="Screener snapshot (indicators, RS ranks, regime feed)">
            snapshot · {{ h.snapshot.as_of || 'never' }}</span>
          <span class="chip" [class.stale]="h.fundamentals.symbols === 0"
                [matTooltip]="'Oldest refresh: ' + (h.fundamentals.oldest || '—')">
            fundamentals · {{ h.fundamentals.symbols }} stocks</span>
          <span class="chip" [matTooltip]="h.intraday.rows + ' intraday bars stored'">
            15m · {{ h.intraday.rows > 0 ? shortTs(h.intraday.last_bar) : 'none' }}</span>
          <span class="chip" [class.stale]="isStale(h.signals.as_of, 4)"
                matTooltip="Live strategy signals evaluation">
            signals · {{ h.signals.as_of || 'never' }}</span>
        </div>
        <button mat-stroked-button class="sync-all" (click)="syncAll()" [disabled]="busy()"
                matTooltip="Daily sync → snapshot refresh → signal evaluation, in order">
          <mat-icon>sync</mat-icon> {{ busy() ? 'Syncing…' : 'Sync all' }}
        </button>
      </mat-card>
    }
  `,
  styles: `
    .dh-card { display: flex; align-items: center; gap: 12px; padding: 10px 16px;
               margin-bottom: 16px; flex-wrap: wrap; }
    .dh-icon { color: var(--accent); flex-shrink: 0; }
    .chips { display: flex; gap: 8px; flex-wrap: wrap; flex: 1; }
    .chip {
      font-size: 11px; font-weight: 600; padding: 4px 12px; border-radius: 999px;
      border: 1px solid var(--card-border); color: var(--text-dim); cursor: help;
      font-variant-numeric: tabular-nums;
    }
    .chip.stale { border-color: rgba(255,183,77,0.5); color: #ffb74d; }
    .sync-all { flex-shrink: 0; }
  `,
})
export class DataHealthCardComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly snackBar = inject(MatSnackBar);
  readonly health = signal<DataHealth | null>(null);
  readonly busy = signal(false);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.api.getDataHealth().subscribe({
      next: (h) => this.health.set(h),
      error: () => this.health.set(null),   // card is additive — vanish quietly
    });
  }

  /** Older than `days` calendar days (weekend-tolerant) counts as stale. */
  isStale(dateStr: string | undefined, days: number): boolean {
    if (!dateStr) return true;
    const then = new Date(dateStr).getTime();
    return isNaN(then) || (Date.now() - then) > days * 86_400_000;
  }

  shortTs(ts: string | undefined): string {
    if (!ts) return 'none';
    const d = new Date(ts);
    return isNaN(d.getTime()) ? 'none'
      : `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  syncAll(): void {
    this.busy.set(true);
    this.api.triggerDailySync().subscribe({
      next: () => this.api.triggerSnapshotRefresh().subscribe({
        next: () => this.api.evaluateSignals().subscribe({
          next: (r) => {
            this.busy.set(false);
            this.snackBar.open(`Synced · snapshot refreshed · ${r.signals} signals`,
                               undefined, { duration: 4000 });
            this.load();
          },
          error: () => this.finishWithWarning('signal evaluation'),
        }),
        error: () => this.finishWithWarning('snapshot refresh'),
      }),
      error: () => this.finishWithWarning('daily sync'),
    });
  }

  private finishWithWarning(step: string): void {
    this.busy.set(false);
    this.snackBar.open(`Stopped at ${step} — check the data service`, 'Dismiss',
                       { duration: 5000 });
    this.load();
  }
}
