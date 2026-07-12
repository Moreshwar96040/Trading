import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';

import { JournalEntry } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';
import { LeaksReportComponent } from './leaks-report.component';

@Component({
  selector: 'app-journal-page',
  standalone: true,
  imports: [CommonModule, FormsModule, MatCardModule, MatButtonModule, MatFormFieldModule,
            MatInputModule, MatIconModule, MatSnackBarModule, MatTooltipModule,
            LeaksReportComponent],
  template: `
    <h2>Trade Journal</h2>

    <!-- ============ what your trades say about your habits ============ -->
    <app-leaks-report />

    <mat-card appearance="outlined" class="editor">
      <h3>{{ editingId() ? 'Edit entry' : 'New entry' }}</h3>
      <div class="row">
        <mat-form-field appearance="outline" class="grow">
          <mat-label>Title</mat-label>
          <input matInput [(ngModel)]="title" placeholder="Why I bought TCS on the dip">
        </mat-form-field>
        <mat-form-field appearance="outline" class="w-ticker">
          <mat-label>Ticker (optional)</mat-label>
          <input matInput [(ngModel)]="ticker" placeholder="TCS">
        </mat-form-field>
        <mat-form-field appearance="outline" class="w-tags">
          <mat-label>Tags (comma-separated)</mat-label>
          <input matInput [(ngModel)]="tags" placeholder="dip-buy, discipline, fomo">
        </mat-form-field>
      </div>
      <mat-form-field appearance="outline" class="body-field">
        <mat-label>What happened, why, and what you learned</mat-label>
        <textarea matInput rows="5" [(ngModel)]="body"></textarea>
      </mat-form-field>
      <div class="row">
        <button mat-flat-button color="primary" (click)="save()">
          <mat-icon>save</mat-icon> {{ editingId() ? 'Update' : 'Save entry' }}
        </button>
        @if (editingId()) {
          <button mat-button (click)="resetForm()">Cancel</button>
        }
      </div>
    </mat-card>

    @for (e of entries(); track e.id) {
      <mat-card appearance="outlined" class="entry">
        <div class="entry-header">
          <div>
            <span class="entry-title">{{ e.title }}</span>
            @if (e.ticker) { <span class="chip">{{ e.ticker }}</span> }
            @if (e.tags) {
              @for (t of e.tags.split(','); track t) { <span class="tag">#{{ t }}</span> }
            }
          </div>
          <div>
            <span class="muted">{{ e.createdAt | date: 'MMM d, y HH:mm' }}</span>
            <button mat-icon-button (click)="edit(e)" matTooltip="Edit">
              <mat-icon>edit</mat-icon>
            </button>
            <button mat-icon-button (click)="remove(e)" matTooltip="Delete">
              <mat-icon>delete</mat-icon>
            </button>
          </div>
        </div>
        <p class="entry-body">{{ e.body }}</p>
      </mat-card>
    } @empty {
      <p class="muted">No journal entries yet. The best traders write down every lesson.</p>
    }
  `,
  styles: `
    h2, h3 { font-weight: 500; }
    .editor { padding: 16px; margin-bottom: 20px; }
    .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    .grow { flex: 2; min-width: 240px; }
    .w-ticker { width: 160px; }
    .w-tags { flex: 1; min-width: 200px; }
    .body-field { width: 100%; }
    .entry { padding: 14px 16px; margin-bottom: 12px; }
    .entry-header { display: flex; justify-content: space-between; align-items: center; }
    .entry-title { font-weight: 600; margin-right: 8px; }
    .chip { background: rgba(79, 195, 247, 0.2); color: #4fc3f7; padding: 2px 8px;
            border-radius: 10px; font-size: 12px; margin-right: 6px; }
    .tag { opacity: 0.6; font-size: 12px; margin-right: 6px; }
    .entry-body { white-space: pre-wrap; margin: 8px 0 0; }
    .muted { opacity: 0.6; font-size: 12px; }
  `,
})
export class JournalPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly snackBar = inject(MatSnackBar);

  readonly entries = signal<JournalEntry[]>([]);
  readonly editingId = signal<number | null>(null);

  title = '';
  ticker = '';
  tags = '';
  body = '';

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.api.listJournal().subscribe({
      next: (list) => this.entries.set(list),
      error: () => this.snackBar.open('Failed to load journal', 'Dismiss', { duration: 4000 }),
    });
  }

  save(): void {
    if (!this.title.trim() || !this.body.trim()) {
      this.snackBar.open('Title and body are required', 'Dismiss', { duration: 3000 });
      return;
    }
    const payload = {
      ticker: this.ticker.trim().toUpperCase() || null,
      title: this.title.trim(),
      body: this.body,
      tags: this.tags.trim() || null,
    };
    const call = this.editingId()
      ? this.api.updateJournalEntry(this.editingId()!, payload)
      : this.api.createJournalEntry(payload);
    call.subscribe({
      next: () => {
        this.snackBar.open('Saved', undefined, { duration: 2000 });
        this.resetForm();
        this.reload();
      },
      error: (err) => this.snackBar.open(err?.error?.message ?? 'Save failed', 'Dismiss', { duration: 5000 }),
    });
  }

  edit(entry: JournalEntry): void {
    this.editingId.set(entry.id);
    this.title = entry.title;
    this.ticker = entry.ticker ?? '';
    this.tags = entry.tags ?? '';
    this.body = entry.body;
  }

  remove(entry: JournalEntry): void {
    this.api.deleteJournalEntry(entry.id).subscribe({ next: () => this.reload() });
  }

  resetForm(): void {
    this.editingId.set(null);
    this.title = '';
    this.ticker = '';
    this.tags = '';
    this.body = '';
  }
}
