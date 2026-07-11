import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';

import { AiPredictionRow } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

@Component({
  selector: 'app-ai-page',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule, MatIconModule, MatTableModule,
            MatProgressSpinnerModule, MatSnackBarModule, MatTooltipModule],
  template: `
    <div class="header-row">
      <h2>AI Analysis</h2>
      <button mat-flat-button color="primary" (click)="train()" [disabled]="training()">
        <mat-icon>model_training</mat-icon>
        {{ training() ? 'Training (30s)…' : 'Retrain models' }}
      </button>
    </div>

    <mat-card appearance="outlined" class="disclaimer">
      <mat-icon>info</mat-icon>
      <p>Educational tool, not investment advice. These are RandomForest models fitted on
         ~2 years of daily data per stock. Check the <b>accuracy</b> column: directional
         accuracy near 50% means the model is guessing — which, for daily stock returns,
         is the honest norm. Never trade on these numbers alone.</p>
    </mat-card>

    @if (training()) {
      <div class="spinner"><mat-spinner diameter="36" /></div>
    }

    @if (rows().length) {
      <table mat-table [dataSource]="rows()" class="table">
        <ng-container matColumnDef="ticker">
          <th mat-header-cell *matHeaderCellDef>Ticker</th>
          <td mat-cell *matCellDef="let r"><b>{{ r.ticker }}</b> <span class="muted">{{ r.name }}</span></td>
        </ng-container>
        <ng-container matColumnDef="direction">
          <th mat-header-cell *matHeaderCellDef>Next day</th>
          <td mat-cell *matCellDef="let r">
            <span class="dir" [class.up]="r.direction === 'UP'"
                  [class.down]="r.direction === 'DOWN'">
              {{ r.direction }} {{ r.predictedReturnPct | number: '1.2-2' }}%
            </span>
          </td>
        </ng-container>
        <ng-container matColumnDef="accuracy">
          <th mat-header-cell *matHeaderCellDef
              matTooltip="Directional accuracy on held-out test data — 50% = coin flip">
            Accuracy</th>
          <td mat-cell *matCellDef="let r"
              [class.weak]="r.testDirectionAccuracy !== null && r.testDirectionAccuracy < 53">
            {{ r.testDirectionAccuracy ?? '—' }}%
          </td>
        </ng-container>
        <ng-container matColumnDef="mae">
          <th mat-header-cell *matHeaderCellDef matTooltip="Mean absolute error of predicted daily return">MAE</th>
          <td mat-cell *matCellDef="let r">{{ r.testMaePct | number: '1.2-2' }}%</td>
        </ng-container>
        <ng-container matColumnDef="asOf">
          <th mat-header-cell *matHeaderCellDef>Data up to</th>
          <td mat-cell *matCellDef="let r">{{ r.asOfDate }}</td>
        </ng-container>
        <ng-container matColumnDef="trained">
          <th mat-header-cell *matHeaderCellDef>Trained</th>
          <td mat-cell *matCellDef="let r" class="muted">
            {{ r.trainedAt | date: 'MMM d, HH:mm' }} · {{ r.trainRows }} rows</td>
        </ng-container>
        <tr mat-header-row *matHeaderRowDef="columns"></tr>
        <tr mat-row *matRowDef="let r; columns: columns"></tr>
      </table>
    } @else if (!training()) {
      <p class="muted">No predictions yet — press "Retrain models" to fit models on your
        stored price history.</p>
    }
  `,
  styles: `
    h2 { font-weight: 500; }
    .header-row { display: flex; justify-content: space-between; align-items: center; }
    .disclaimer { padding: 12px 16px; display: flex; gap: 12px; align-items: center;
                  margin-bottom: 16px; opacity: 0.85; }
    .disclaimer p { margin: 0; font-size: 13px; }
    .table { width: 100%; }
    .dir { font-weight: 600; }
    .up { color: #26a69a; }
    .down { color: #ef5350; }
    .weak { color: #ffb74d; }
    .muted { opacity: 0.6; font-size: 12px; }
    .spinner { display: flex; justify-content: center; padding: 24px; }
  `,
})
export class AiPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly snackBar = inject(MatSnackBar);

  readonly columns = ['ticker', 'direction', 'accuracy', 'mae', 'asOf', 'trained'];
  readonly rows = signal<AiPredictionRow[]>([]);
  readonly training = signal(false);

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.api.listAiPredictions().subscribe({
      next: (list) => this.rows.set(list),
      error: () => this.snackBar.open('Failed to load predictions', 'Dismiss', { duration: 4000 }),
    });
  }

  train(): void {
    this.training.set(true);
    this.api.trainAi().subscribe({
      next: (result) => {
        this.training.set(false);
        this.snackBar.open(`Trained ${result.trained} model(s)`, undefined, { duration: 3500 });
        this.reload();
      },
      error: (err) => {
        this.training.set(false);
        this.snackBar.open(err?.error?.message ?? 'Training failed', 'Dismiss', { duration: 6000 });
      },
    });
  }
}
