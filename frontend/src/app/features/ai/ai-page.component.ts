import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';

import { AiPredictionRow, AiUsageSummary, AutopilotStatus,
         ConvictionCalibration } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

/** Accuracy at or below this is a coin flip — the conviction engine ignores it. */
const MIN_USEFUL_ACCURACY = 50;
/** Above this the model is doing something genuinely better than chance. */
const GOOD_ACCURACY = 55;

/**
 * AI & ML: what the models actually predict, how well they've tested, and what
 * the LLM layer costs. Deliberately does NOT re-introduce the old "trade ideas"
 * grid — that was retired because the Alpha Stack scores the same inputs better,
 * and two competing scorers that disagree is worse than one that doesn't.
 */
@Component({
  selector: 'app-ai-page',
  standalone: true,
  imports: [CommonModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule,
            MatTableModule, MatProgressSpinnerModule, MatSnackBarModule, MatTooltipModule],
  template: `
    <div class="header-row">
      <h2>AI &amp; ML</h2>
      <button mat-flat-button color="primary" (click)="train()" [disabled]="training()">
        <mat-icon>model_training</mat-icon>
        {{ training() ? 'Training…' : 'Retrain models' }}
      </button>
    </div>
    <p class="lede">Per-stock RandomForest models fitted on your stored price history,
      plus what the Claude layer has cost. The Alpha Stack consumes these as its
      <em>ml</em> layer — but only when a model beats a coin flip.</p>

    <!-- ============ model health: is any of this trustworthy? ============ -->
    <div class="cards">
      <mat-card appearance="outlined" class="card metric">
        <span class="value metric-value">{{ rows().length }}</span>
        <span class="label">Models trained</span>
      </mat-card>
      <mat-card appearance="outlined" class="card metric">
        <span class="value metric-value" [class.up]="usefulCount() > 0">{{ usefulCount() }}</span>
        <span class="label" matTooltip="Directional accuracy above 50% — the bar the
                                        Alpha Stack requires before it counts a vote">
          Beating a coin flip</span>
      </mat-card>
      <mat-card appearance="outlined" class="card metric">
        <span class="value metric-value">{{ avgAccuracy() ?? '—' }}<span class="pct">%</span></span>
        <span class="label">Average accuracy</span>
      </mat-card>
      <mat-card appearance="outlined" class="card metric">
        <span class="value metric-value" [class.up]="upCount() > downCount()"
              [class.down]="downCount() > upCount()">{{ upCount() }}/{{ downCount() }}</span>
        <span class="label">Predicting up / down</span>
      </mat-card>
    </div>

    <mat-card appearance="outlined" class="disclaimer">
      <mat-icon>info</mat-icon>
      <p>Educational tool, not investment advice. Directional accuracy near 50% means the
        model is guessing — which, for next-day stock returns, is the honest norm. A model
        below {{ minUseful }}% is <b>ignored</b> by the Alpha Stack rather than trusted.
        Never trade on these numbers alone.</p>
    </mat-card>

    <!-- ============ raw predictions ============ -->
    <h3>Model predictions</h3>
    @if (training()) {
      <div class="spinner"><mat-spinner diameter="34" />
        <span class="muted">Fitting models on your price history — this can take a minute.</span>
      </div>
    } @else if (rows().length) {
      <table mat-table [dataSource]="rows()" class="table">
        <ng-container matColumnDef="ticker">
          <th mat-header-cell *matHeaderCellDef>Ticker</th>
          <td mat-cell *matCellDef="let r">
            <a [routerLink]="['/alpha']" [queryParams]="{ ticker: r.ticker }"
               class="tk">{{ r.ticker }}</a>
            <span class="muted">{{ r.name }}</span>
          </td>
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
          <td mat-cell *matCellDef="let r">
            <span [class]="accuracyClass(r.testDirectionAccuracy)">
              {{ r.testDirectionAccuracy ?? '—' }}%</span>
            @if (r.testDirectionAccuracy !== null && r.testDirectionAccuracy <= minUseful) {
              <span class="ignored" matTooltip="Below the bar — the Alpha Stack ignores this vote">
                ignored</span>
            }
          </td>
        </ng-container>
        <ng-container matColumnDef="mae">
          <th mat-header-cell *matHeaderCellDef
              matTooltip="Mean absolute error of the predicted daily return">MAE</th>
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
    } @else {
      <mat-card appearance="outlined" class="empty">
        <mat-icon>psychology</mat-icon>
        <div>
          <p>No models trained yet.</p>
          <p class="muted">Press <b>Retrain models</b> to fit one per stock on your stored
            price history. You need a sync first so there are bars to learn from.</p>
        </div>
      </mat-card>
    }

    <!-- ============ paper autopilot: graded on money, not correlation ========== -->
    <h3 class="cal-header">Paper autopilot
      <span class="muted">· the Alpha Stack trading its own signals</span></h3>

    @if (autopilot(); as a) {
      @if (!a.enabled) {
        <mat-card appearance="outlined" class="empty">
          <mat-icon>toggle_off</mat-icon>
          <div>
            <p><b>Disabled.</b> Set <code>AUTOPILOT_ENABLED=true</code> in
              <code>.env</code> and restart the data service.</p>
            <p class="muted">When on, it opens <b>paper</b> positions for setups scoring
              ≥ {{ a.min_conviction }} (max {{ a.max_positions }} open), attaches an ATR
              stop and target, and records the conviction behind each entry so realised
              P&amp;L can be attributed back to the score. Paper only — it never touches
              Upstox or Exness.</p>
          </div>
        </mat-card>
      } @else {
        <div class="cards">
          <mat-card appearance="outlined" class="card metric">
            <span class="value metric-value">{{ a.open.length }}</span>
            <span class="label">Open positions</span>
          </mat-card>
          <mat-card appearance="outlined" class="card metric">
            <span class="value metric-value">{{ a.closed_count }}</span>
            <span class="label">Closed trades</span>
          </mat-card>
          <mat-card appearance="outlined" class="card metric">
            <span class="value metric-value" [class.up]="a.net > 0" [class.down]="a.net < 0">
              ₹{{ a.net | number: '1.0-0' }}</span>
            <span class="label">Realised P&amp;L</span>
          </mat-card>
        </div>

        @if (a.closed_count > 0) {
          <h4>Realised P&amp;L by conviction band</h4>
          <table mat-table [dataSource]="a.by_band" class="table">
            <ng-container matColumnDef="band">
              <th mat-header-cell *matHeaderCellDef>Band</th>
              <td mat-cell *matCellDef="let b"><b>{{ b.band }}</b></td>
            </ng-container>
            <ng-container matColumnDef="trades">
              <th mat-header-cell *matHeaderCellDef>Trades</th>
              <td mat-cell *matCellDef="let b">{{ b.trades }}</td>
            </ng-container>
            <ng-container matColumnDef="win_rate_pct">
              <th mat-header-cell *matHeaderCellDef>Win rate</th>
              <td mat-cell *matCellDef="let b">
                {{ b.win_rate_pct !== null ? b.win_rate_pct + '%' : '—' }}</td>
            </ng-container>
            <ng-container matColumnDef="net">
              <th mat-header-cell *matHeaderCellDef>Net</th>
              <td mat-cell *matCellDef="let b" [class.up]="b.net > 0" [class.down]="b.net < 0">
                ₹{{ b.net | number: '1.0-0' }}</td>
            </ng-container>
            <tr mat-header-row *matHeaderRowDef="autoBandColumns"></tr>
            <tr mat-row *matRowDef="let b; columns: autoBandColumns"></tr>
          </table>
          <p class="muted">If the 75+ band doesn't out-earn 55–75 here, the score isn't
            translating into money — which no amount of reweighting fixes.</p>
        } @else {
          <p class="muted">No closed trades yet — attribution appears once positions
            close via stop, target or the AI position manager.</p>
        }

        @if (a.open.length) {
          <h4>Open</h4>
          <table mat-table [dataSource]="a.open" class="table">
            <ng-container matColumnDef="ticker">
              <th mat-header-cell *matHeaderCellDef>Ticker</th>
              <td mat-cell *matCellDef="let t"><b>{{ t.ticker }}</b></td>
            </ng-container>
            <ng-container matColumnDef="conviction">
              <th mat-header-cell *matHeaderCellDef>Conviction</th>
              <td mat-cell *matCellDef="let t">{{ t.conviction }}</td>
            </ng-container>
            <ng-container matColumnDef="quantity">
              <th mat-header-cell *matHeaderCellDef>Qty</th>
              <td mat-cell *matCellDef="let t">{{ t.quantity }}</td>
            </ng-container>
            <ng-container matColumnDef="entry_price">
              <th mat-header-cell *matHeaderCellDef>Entry</th>
              <td mat-cell *matCellDef="let t">₹{{ t.entry_price | number: '1.2-2' }}</td>
            </ng-container>
            <ng-container matColumnDef="stop_price">
              <th mat-header-cell *matHeaderCellDef>Stop</th>
              <td mat-cell *matCellDef="let t" class="down">
                {{ t.stop_price ? ('₹' + (t.stop_price | number: '1.2-2')) : '—' }}</td>
            </ng-container>
            <ng-container matColumnDef="entry_date">
              <th mat-header-cell *matHeaderCellDef>Opened</th>
              <td mat-cell *matCellDef="let t" class="muted">{{ t.entry_date }}</td>
            </ng-container>
            <tr mat-header-row *matHeaderRowDef="autoOpenColumns"></tr>
            <tr mat-row *matRowDef="let t; columns: autoOpenColumns"></tr>
          </table>
        }
      }
    }

    <!-- ============ adaptive conviction: has the model earned its weights? ====== -->
    <h3 class="cal-header">Model calibration
      <span class="muted">· learned from the Alpha Stack's own recorded history</span></h3>

    @if (calibration(); as c) {
      @if (c.status === 'COLLECTING') {
        <mat-card appearance="outlined" class="empty">
          <mat-icon>hourglass_top</mat-icon>
          <div>
            <p><b>Collecting — {{ c.n }} of {{ c.needed }} labelled setups.</b></p>
            <p class="muted">{{ c.note }}</p>
          </div>
        </mat-card>
      } @else {
        <p class="muted range">{{ c.n }} labelled setups · {{ c.date_from }} → {{ c.date_to }}
          · horizon {{ c.horizon }}
          @if (c.conviction_ic !== null && c.conviction_ic !== undefined) {
            · overall conviction IC <b>{{ c.conviction_ic }}</b>
          }
        </p>

        <!-- does a higher score actually earn more? -->
        @if (c.calibration?.length) {
          <table mat-table [dataSource]="c.calibration ?? []" class="table">
            <ng-container matColumnDef="band">
              <th mat-header-cell *matHeaderCellDef>Conviction band</th>
              <td mat-cell *matCellDef="let b"><b>{{ b.band }}</b></td>
            </ng-container>
            <ng-container matColumnDef="n">
              <th mat-header-cell *matHeaderCellDef>Setups</th>
              <td mat-cell *matCellDef="let b">{{ b.n }}</td>
            </ng-container>
            <ng-container matColumnDef="avg_return">
              <th mat-header-cell *matHeaderCellDef>Avg forward return</th>
              <td mat-cell *matCellDef="let b" [class.up]="b.avg_return > 0"
                  [class.down]="b.avg_return < 0">
                {{ b.avg_return !== null ? (b.avg_return | number: '1.2-2') + '%' : '—' }}</td>
            </ng-container>
            <ng-container matColumnDef="hit_rate">
              <th mat-header-cell *matHeaderCellDef>Hit rate</th>
              <td mat-cell *matCellDef="let b">
                {{ b.hit_rate !== null ? b.hit_rate + '%' : '—' }}</td>
            </ng-container>
            <tr mat-header-row *matHeaderRowDef="bandColumns"></tr>
            <tr mat-row *matRowDef="let b; columns: bandColumns"></tr>
          </table>
        }

        <!-- which layers actually predict? -->
        <h4>Layer predictiveness</h4>
        <table mat-table [dataSource]="c.layer_ic ?? []" class="table">
          <ng-container matColumnDef="layer">
            <th mat-header-cell *matHeaderCellDef>Layer</th>
            <td mat-cell *matCellDef="let l"><b>{{ layerLabel(l.layer) }}</b></td>
          </ng-container>
          <ng-container matColumnDef="ic">
            <th mat-header-cell *matHeaderCellDef
                matTooltip="Information Coefficient — rank correlation with forward
                            return. 0.03-0.05 is useful, 0.10+ is strong.">IC</th>
            <td mat-cell *matCellDef="let l" [class.up]="l.ic > 0.03"
                [class.down]="l.ic < -0.03">{{ l.ic ?? '—' }}</td>
          </ng-container>
          <ng-container matColumnDef="verdict">
            <th mat-header-cell *matHeaderCellDef>Evidence</th>
            <td mat-cell *matCellDef="let l">
              @if (l.note) { <span class="muted">{{ l.note }}</span> }
              @else if (l.significant) { <span class="sig">significant</span> }
              @else { <span class="muted">no evidence (n={{ l.n }})</span> }
            </td>
          </ng-container>
          <tr mat-header-row *matHeaderRowDef="icColumns"></tr>
          <tr mat-row *matRowDef="let l; columns: icColumns"></tr>
        </table>

        <!-- suggested weights -->
        @if (c.weights; as w) {
          <h4>Suggested weights</h4>
          @if (w.status === 'OK') {
            <p class="muted">Ridge fit on {{ w.n }} setups, walk-forward validated
              @if (w.oos_ic !== null && w.oos_ic !== undefined) {
                (out-of-sample IC {{ w.oos_ic }})
              }
              · shrunk {{ ((1 - (w.shrinkage ?? 0)) * 100) | number: '1.0-0' }}% toward
              the current weights. <b>Suggestions only</b> — nothing is applied.</p>
            <table mat-table [dataSource]="w.weights ?? []" class="table">
              <ng-container matColumnDef="layer">
                <th mat-header-cell *matHeaderCellDef>Layer</th>
                <td mat-cell *matCellDef="let r"><b>{{ layerLabel(r.layer) }}</b></td>
              </ng-container>
              <ng-container matColumnDef="current">
                <th mat-header-cell *matHeaderCellDef>Current</th>
                <td mat-cell *matCellDef="let r">{{ r.current }}</td>
              </ng-container>
              <ng-container matColumnDef="suggested">
                <th mat-header-cell *matHeaderCellDef>Suggested</th>
                <td mat-cell *matCellDef="let r"><b>{{ r.suggested }}</b></td>
              </ng-container>
              <ng-container matColumnDef="delta">
                <th mat-header-cell *matHeaderCellDef>Change</th>
                <td mat-cell *matCellDef="let r" [class.up]="r.delta > 0"
                    [class.down]="r.delta < 0">
                  {{ r.delta > 0 ? '+' : '' }}{{ r.delta }}</td>
              </ng-container>
              <tr mat-header-row *matHeaderRowDef="weightColumns"></tr>
              <tr mat-row *matRowDef="let r; columns: weightColumns"></tr>
            </table>
          } @else {
            <p class="muted">
              @if (w.status === 'INSUFFICIENT') {
                Weight suggestions unlock at {{ w.needed }} labelled setups ({{ w.n }} so far)
                — seven weights need a few hundred rows before a fit is anything but noise.
              } @else { {{ w.note }} }
            </p>
          }
        }

        @if (c.veto_audit; as v) {
          @if (v.n > 0) {
            <p class="veto"><mat-icon>gavel</mat-icon>
              News veto blocked {{ v.n }} setups averaging
              {{ v.avg_return_vetoed | number: '1.2-2' }}% vs
              {{ v.avg_return_other | number: '1.2-2' }}% elsewhere — {{ v.verdict }}.</p>
          }
        }
      }
    }

    <!-- ============ what the LLM layer costs ============ -->
    <h3 class="cost-header">AI spend</h3>
    @if (usage(); as u) {
      <div class="cards">
        <mat-card appearance="outlined" class="card metric">
          <span class="value metric-value">₹{{ u.month.cost_inr | number: '1.2-2' }}</span>
          <span class="label">This month ({{ u.month.calls }} calls)</span>
        </mat-card>
        <mat-card appearance="outlined" class="card metric">
          <span class="value metric-value">₹{{ u.total.cost_inr | number: '1.2-2' }}</span>
          <span class="label">All time ({{ u.total.calls }} calls)</span>
        </mat-card>
        <mat-card appearance="outlined" class="card metric">
          <span class="value metric-value">{{ u.total.input_tokens + u.total.output_tokens
            | number: '1.0-0' }}</span>
          <span class="label">Tokens used</span>
        </mat-card>
      </div>
      @if (u.by_kind?.length) {
        <table mat-table [dataSource]="u.by_kind" class="table">
          <ng-container matColumnDef="kind">
            <th mat-header-cell *matHeaderCellDef>Feature</th>
            <td mat-cell *matCellDef="let k"><b>{{ kindLabel(k.kind) }}</b></td>
          </ng-container>
          <ng-container matColumnDef="calls">
            <th mat-header-cell *matHeaderCellDef>Calls</th>
            <td mat-cell *matCellDef="let k">{{ k.calls }}</td>
          </ng-container>
          <ng-container matColumnDef="tokens">
            <th mat-header-cell *matHeaderCellDef>Tokens</th>
            <td mat-cell *matCellDef="let k">
              {{ k.input_tokens + k.output_tokens | number: '1.0-0' }}</td>
          </ng-container>
          <ng-container matColumnDef="cost">
            <th mat-header-cell *matHeaderCellDef>Cost</th>
            <td mat-cell *matCellDef="let k">₹{{ k.cost_inr | number: '1.2-2' }}</td>
          </ng-container>
          <tr mat-header-row *matHeaderRowDef="usageColumns"></tr>
          <tr mat-row *matRowDef="let k; columns: usageColumns"></tr>
        </table>
      }
    } @else {
      <p class="muted">No AI usage recorded yet — costs appear once news digests or
        fundamentals explanations run.</p>
    }
  `,
  styles: `
    h2 { font-weight: 500; }
    h3 { font-weight: 500; margin-top: 26px; }
    .header-row { display: flex; justify-content: space-between; align-items: center;
                  gap: 16px; flex-wrap: wrap; }
    .lede { color: var(--text-dim); font-size: 13.5px; margin: -4px 0 18px; line-height: 1.5; }
    .lede em { color: var(--accent); font-style: normal; font-weight: 600; }
    .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
             gap: 12px; margin-bottom: 14px; }
    .card { padding: 14px; display: flex; flex-direction: column; gap: 4px; }
    .value { font-size: 22px; font-weight: 600; }
    .pct { font-size: 14px; opacity: 0.6; }
    .label { font-size: 12px; opacity: 0.65; }
    .disclaimer { padding: 12px 16px; display: flex; gap: 12px; align-items: center;
                  margin-bottom: 8px; }
    .disclaimer p { margin: 0; font-size: 12.5px; line-height: 1.5; }
    .disclaimer mat-icon { color: #ffb74d; flex-shrink: 0; }
    .table { width: 100%; margin-bottom: 12px; }
    .tk { font-weight: 700; text-decoration: none; color: var(--mat-sys-on-surface);
          margin-right: 6px; }
    .tk:hover { color: var(--accent); }
    .dir { font-weight: 600; }
    .up { color: var(--up); }
    .down { color: var(--down); }
    .acc-good { color: var(--up); font-weight: 600; }
    .acc-weak { color: #ffb74d; }
    .acc-bad { color: var(--down); }
    .ignored { font-size: 9px; font-weight: 800; letter-spacing: 0.06em; margin-left: 8px;
               padding: 1px 7px; border-radius: 999px; text-transform: uppercase;
               background: rgba(239,83,80,0.14); color: var(--down); }
    .muted { opacity: 0.6; font-size: 12px; }
    .spinner { display: flex; flex-direction: column; align-items: center; gap: 12px;
               padding: 28px; }
    .empty { display: flex; gap: 16px; align-items: center; padding: 22px;
             color: var(--text-dim); }
    .empty mat-icon { color: var(--accent); }
    .empty p { margin: 2px 0; }
    .cost-header { margin-top: 30px; }
    .cal-header { margin-top: 32px; }
    .cal-header .muted { font-weight: 400; }
    h4 { font-weight: 600; font-size: 13px; margin: 20px 0 6px; color: var(--text-dim);
         text-transform: uppercase; letter-spacing: 0.06em; }
    .range { margin: -4px 0 12px; }
    .sig { font-size: 10px; font-weight: 800; letter-spacing: 0.05em; padding: 2px 8px;
           border-radius: 999px; background: rgba(38,166,154,0.15); color: var(--up); }
    .veto { display: flex; align-items: center; gap: 8px; font-size: 13px;
            color: var(--text-dim); margin-top: 14px; }
    .veto mat-icon { font-size: 17px; width: 17px; height: 17px; }
  `,
})
export class AiPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly snackBar = inject(MatSnackBar);

  readonly minUseful = MIN_USEFUL_ACCURACY;
  readonly columns = ['ticker', 'direction', 'accuracy', 'mae', 'asOf', 'trained'];
  readonly usageColumns = ['kind', 'calls', 'tokens', 'cost'];

  readonly autoBandColumns = ['band', 'trades', 'win_rate_pct', 'net'];
  readonly autoOpenColumns = ['ticker', 'conviction', 'quantity', 'entry_price',
                              'stop_price', 'entry_date'];
  readonly bandColumns = ['band', 'n', 'avg_return', 'hit_rate'];
  readonly icColumns = ['layer', 'ic', 'verdict'];
  readonly weightColumns = ['layer', 'current', 'suggested', 'delta'];

  readonly rows = signal<AiPredictionRow[]>([]);
  readonly usage = signal<AiUsageSummary | null>(null);
  readonly calibration = signal<ConvictionCalibration | null>(null);
  readonly autopilot = signal<AutopilotStatus | null>(null);
  readonly training = signal(false);

  /** Models the Alpha Stack will actually listen to. */
  readonly usefulCount = computed(() => this.rows().filter(
    (r) => (r.testDirectionAccuracy ?? 0) > MIN_USEFUL_ACCURACY).length);

  readonly avgAccuracy = computed(() => {
    const vals = this.rows().map((r) => r.testDirectionAccuracy)
      .filter((v): v is number => v !== null);
    if (!vals.length) return null;
    return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length * 10) / 10;
  });

  readonly upCount = computed(() => this.rows().filter((r) => r.direction === 'UP').length);
  readonly downCount = computed(() => this.rows().filter((r) => r.direction === 'DOWN').length);

  ngOnInit(): void {
    this.reload();
    this.loadUsage();
    this.loadCalibration();
    this.loadAutopilot();
  }

  private loadAutopilot(): void {
    this.api.getAutopilotStatus().subscribe({
      next: (a) => this.autopilot.set(a),
      error: () => this.autopilot.set(null),     // additive panel — fail quietly
    });
  }

  private loadCalibration(): void {
    this.api.getConvictionCalibration().subscribe({
      next: (c) => this.calibration.set(c),
      error: () => this.calibration.set(null),   // additive panel — fail quietly
    });
  }

  accuracyClass(accuracy: number | null): string {
    if (accuracy === null) return '';
    if (accuracy >= GOOD_ACCURACY) return 'acc-good';
    if (accuracy > MIN_USEFUL_ACCURACY) return 'acc-weak';
    return 'acc-bad';
  }

  layerLabel(layer: string): string {
    return { technical: 'Technical (timing)', quality: 'Fundamentals (quality)',
             news: 'News sentiment', momentum: 'Relative strength', ml: 'ML vote',
             macro: 'Market-wide news', regime: 'Market regime' }[layer] ?? layer;
  }

  kindLabel(kind: string): string {
    return { NEWS: 'Stock news digests', FUNDAMENTALS: 'Fundamentals explanations',
             MACRO: 'Market-wide news', BRIEFING: 'Morning briefing',
             REVIEW: 'Trade reviews' }[kind] ?? kind;
  }

  reload(): void {
    this.api.listAiPredictions().subscribe({
      next: (list) => this.rows.set(list),
      error: () => this.snackBar.open('Failed to load predictions', 'Dismiss',
                                      { duration: 4000 }),
    });
  }

  private loadUsage(): void {
    this.api.getAiUsage().subscribe({
      next: (u) => this.usage.set(u),
      error: () => this.usage.set(null),      // cost panel is additive — fail quietly
    });
  }

  train(): void {
    this.training.set(true);
    this.api.trainAi().subscribe({
      next: (result) => {
        this.training.set(false);
        this.snackBar.open(`Trained ${result.trained} model(s)`, undefined,
                           { duration: 3500 });
        this.reload();
      },
      error: (err) => {
        this.training.set(false);
        this.snackBar.open(err?.error?.message ?? 'Training failed', 'Dismiss',
                           { duration: 6000 });
      },
    });
  }
}
