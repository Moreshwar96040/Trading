import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';

import { RouterLink } from '@angular/router';

import { AiPredictionRow, TradeIdea } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

@Component({
  selector: 'app-ai-page',
  standalone: true,
  imports: [CommonModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule,
            MatTableModule, MatProgressSpinnerModule, MatSnackBarModule, MatTooltipModule],
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

    <!-- ============ trade ideas: the confluence view ============ -->
    <div class="header-row ideas-header">
      <h3>Trade ideas <span class="muted">· model + your strategies + regime + quality, ranked</span></h3>
      <button mat-stroked-button (click)="loadIdeas()" [disabled]="loadingIdeas()">
        <mat-icon>refresh</mat-icon> Refresh ideas
      </button>
    </div>

    @if (loadingIdeas()) {
      <div class="spinner"><mat-spinner diameter="32" /></div>
    } @else if (ideas().length) {
      <div class="ideas-grid">
        @for (idea of ideas(); track idea.ticker) {
          <mat-card appearance="outlined" class="idea-card">
            <div class="idea-top">
              <span class="score" matTooltip="Confluence score — how many independent reads agree">
                {{ idea.score }}</span>
              <div>
                <b>{{ idea.ticker }}</b>
                <div class="muted">{{ idea.name }}</div>
              </div>
              <span class="idea-spacer"></span>
              @if (idea.close !== null) {
                <span class="idea-close">₹{{ idea.close | number: '1.2-2' }}</span>
              }
            </div>
            <ul class="reasons">
              @for (r of idea.reasons; track r) { <li>{{ r }}</li> }
            </ul>
            @if (idea.risk_plan; as rp) {
              <p class="plan">
                <span class="down">Stop ₹{{ rp.stop_price | number: '1.2-2' }}</span>
                @if (rp.take_profit_price !== null) {
                  · <span class="up">Target ₹{{ rp.take_profit_price | number: '1.2-2' }}</span>
                } @else { · <span class="up">trail &amp; let it run</span> }
                · {{ rp.stop_pct }}% risk
              </p>
            }
            <div class="idea-actions">
              <button mat-flat-button color="primary" (click)="tradeIdea(idea)"
                      [disabled]="busy() || !idea.risk_plan">
                <mat-icon>rocket_launch</mat-icon> Trade it
              </button>
              <a mat-stroked-button [routerLink]="['/chart']"
                 [queryParams]="{ ticker: idea.ticker }">
                <mat-icon>show_chart</mat-icon> Chart
              </a>
            </div>
          </mat-card>
        }
      </div>
    } @else {
      <p class="muted">No positive-confluence ideas right now — train the models, evaluate
        strategy signals, and refresh.</p>
    }

    <h3 class="preds-header">Raw model predictions</h3>

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
    .ideas-header { margin-top: 8px; }
    .ideas-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
                  gap: 14px; margin-bottom: 20px; }
    .idea-card { padding: 16px; display: flex; flex-direction: column; gap: 8px; }
    .idea-top { display: flex; gap: 12px; align-items: center; }
    .idea-spacer { flex: 1; }
    .idea-close { font-variant-numeric: tabular-nums; font-weight: 600; }
    .score { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center;
             font-weight: 800; font-size: 16px; color: var(--on-gradient, #061020);
             background: linear-gradient(135deg, var(--accent), var(--accent-2)); }
    .reasons { margin: 0; padding-left: 18px; font-size: 13px; opacity: 0.85; }
    .reasons li { margin: 2px 0; }
    .plan { margin: 0; font-size: 13px; font-variant-numeric: tabular-nums; }
    .idea-actions { display: flex; gap: 10px; margin-top: 4px; }
    .preds-header { margin-top: 8px; }
  `,
})
export class AiPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly snackBar = inject(MatSnackBar);

  readonly columns = ['ticker', 'direction', 'accuracy', 'mae', 'asOf', 'trained'];
  readonly rows = signal<AiPredictionRow[]>([]);
  readonly training = signal(false);
  readonly ideas = signal<TradeIdea[]>([]);
  readonly loadingIdeas = signal(false);
  readonly busy = signal(false);

  ngOnInit(): void {
    this.reload();
    this.loadIdeas();
  }

  loadIdeas(): void {
    this.loadingIdeas.set(true);
    this.api.getAiIdeas().subscribe({
      next: (res) => { this.ideas.set(res.ideas); this.loadingIdeas.set(false); },
      error: () => { this.ideas.set([]); this.loadingIdeas.set(false); },
    });
  }

  /** Same one-click flow as strategy signals: size by risk, order carries the plan. */
  tradeIdea(idea: TradeIdea): void {
    const plan = idea.risk_plan;
    if (!plan) return;
    this.busy.set(true);
    this.api.calcPositionSize(plan.as_of_price, plan.stop_price).subscribe({
      next: (size) => {
        if (size.quantity < 1) {
          this.busy.set(false);
          this.snackBar.open('Risk sizing produced 0 shares — check risk settings', 'Dismiss',
                             { duration: 6000 });
          return;
        }
        this.api.placePaperOrder(idea.ticker, 'BUY', size.quantity, {
          stopPrice: plan.stop_price,
          targetPrice: plan.take_profit_price,
        }).subscribe({
          next: (order) => {
            this.busy.set(false);
            this.snackBar.open(order.status === 'FILLED'
              ? `Bought ${order.quantity} ${idea.ticker} @ ₹${order.price} · stop ₹${plan.stop_price}`
              : `Rejected: ${order.rejectReason}`, undefined, { duration: 6000 });
          },
          error: (err) => {
            this.busy.set(false);
            this.snackBar.open(err?.error?.message ?? 'Order failed', 'Dismiss', { duration: 6000 });
          },
        });
      },
      error: () => {
        this.busy.set(false);
        this.snackBar.open('Position sizing failed', 'Dismiss', { duration: 5000 });
      },
    });
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
