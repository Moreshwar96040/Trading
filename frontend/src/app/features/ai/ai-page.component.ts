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

import { AdaptationHistory, AdaptationRun,
         AiPredictionRow, AiUsageSummary, AutopilotStatus,
         CircuitBreakerReport,
         ConvictionCalibration, RegimeWeights, ShadowBoard,
         WeightProposal } from '../../core/models/market-data.models';
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

    <!-- ============ challenger proposal: what must a new model survive? ====== -->
    <h3 class="cal-header">Challenger proposal
      <span class="muted">· a candidate must pass every gate to be watched, and a
        human to be traded</span></h3>

    <div class="propose-row">
      <button mat-stroked-button (click)="propose()" [disabled]="proposing()">
        <mat-icon>science</mat-icon>
        {{ proposing() ? 'Running gates…' : 'Fit & test a challenger' }}
      </button>
      <span class="muted small">Fits new weights on recorded history, runs five
        validation gates, and registers a shadow model only on a clean sweep.
        Nothing here changes what you trade.</span>
    </div>

    @if (proposal(); as p) {
      <mat-card appearance="outlined" class="verdict"
                [class.ok]="p.status === 'PASSED'" [class.no]="p.status !== 'PASSED'">
        <mat-icon>{{ p.status === 'PASSED' ? 'verified' : 'block' }}</mat-icon>
        <div>
          <p class="vsum"><b>{{ p.summary }}</b></p>
          <p class="muted small">
            {{ p.n }} labelled setups
            @if (p.oos_ic !== null && p.oos_ic !== undefined) {
              · candidate out-of-sample IC <b>{{ p.oos_ic }}</b>
            }
            @if (p.champion_oos_ic !== null && p.champion_oos_ic !== undefined) {
              vs champion {{ p.champion_oos_ic }}
            }
            @if (p.registered_version_id) {
              · registered as shadow model #{{ p.registered_version_id }}
            }
          </p>
          @if (p.note) { <p class="muted small">{{ p.note }}</p> }
        </div>
      </mat-card>

      @if (p.gates?.length) {
        <ul class="gates">
          @for (g of p.gates; track g.gate) {
            <li [class.pass]="g.passed" [class.fail]="!g.passed">
              <mat-icon>{{ g.passed ? 'check_circle' : 'cancel' }}</mat-icon>
              <b>{{ gateLabel(g.gate) }}</b>
              <span class="muted">{{ g.reason }}</span>
            </li>
          }
        </ul>
      }

      @if (p.candidate) {
        <h4>Candidate weights</h4>
        <p class="muted small">Shown for inspection. These are not in use until
          promoted.</p>
        <div class="chips">
          @for (layer of layerOrder; track layer) {
            <span class="wchip"><b>{{ layerLabel(layer) }}</b>
              {{ p.candidate[layer] }}</span>
          }
        </div>
      }
    }

    <!-- ============ regime-aware weights ============ -->
    @if (regimeWeights(); as r) {
      @if (r.status === 'OK') {
        <h4>Weights by market regime</h4>
        <p class="muted small">Each regime starts identical to the global fit and
          drifts only in proportion to its own evidence — shrinkage
          n/(n+{{ r.shrink_k }}). Five regimes collapse to three buckets for
          learning, because a five-way split on this much data is noise.</p>
        @for (b of r.buckets; track b.bucket) {
          <div class="bucket">
            <div class="bhead">
              <b>{{ bucketLabel(b.bucket) }}</b>
              <span class="muted small">{{ b.n }} setups · pulled
                {{ (b.shrink * 100) | number: '1.0-0' }}% toward its own fit
                @if (b.status === 'USING_GLOBAL') { · too thin to fit — using global }
              </span>
            </div>
            <div class="chips">
              @for (w of b.weights; track w.layer) {
                <span class="wchip" [class.up]="w.drift > 1" [class.down]="w.drift < -1">
                  <b>{{ layerLabel(w.layer) }}</b> {{ w.weight }}
                  @if (w.drift !== 0) {
                    <em>{{ w.drift > 0 ? '+' : '' }}{{ w.drift }}</em>
                  }
                </span>
              }
            </div>
          </div>
        }
      }
    }

    <!-- ============ self-adjustment: what the system does on its own ======= -->
    @if (adaptation(); as a) {
      <h3 class="cal-header">Self-adjustment
        <span class="muted">· the Alpha Stack retuning itself, within your bounds</span></h3>

      <p class="muted small">
        Weights are chosen by market condition. A regime with no model of its own
        uses the global set — it only diverges once its own data justifies it.
        Automatic changes may move any layer at most 10 points from the baseline
        you approved, may not switch a layer off, and can never touch the news veto.
      </p>

      <div class="scopes">
        @for (s of a.scopes; track s.scope) {
          <mat-card appearance="outlined" class="scope"
                    [class.live]="s.scope === liveScope()">
            <div class="shead">
              <b>{{ scopeLabel(s.scope) }}</b>
              @if (s.scope === liveScope()) { <span class="pill ahead">Live now</span> }
              @if (s.is_anchor) {
                <span class="pill" matTooltip="These are the weights you approved.">
                  Your baseline</span>
              } @else {
                <span class="pill" matTooltip="Automatically tuned within your bounds.">
                  Auto-tuned</span>
              }
            </div>
            <div class="chips">
              @for (layer of layerOrder; track layer) {
                <span class="wchip"><b>{{ layerLabel(layer) }}</b>
                  {{ s.weights[layer] }}</span>
              }
            </div>
            <p class="muted small">
              {{ s.label }}
              @if (s.cooldown_days_left) {
                · locked for {{ s.cooldown_days_left }} more day(s)
              }
            </p>
            @if (!s.is_anchor) {
              <button mat-button (click)="revert(s.scope)" [disabled]="adapting()">
                <mat-icon>restore</mat-icon> Revert to my baseline
              </button>
            }
          </mat-card>
        }
      </div>

      <div class="propose-row">
        <button mat-stroked-button (click)="adapt(true)" [disabled]="adapting()">
          <mat-icon>visibility</mat-icon> Preview what it would change
        </button>
        <button mat-stroked-button color="primary" (click)="adapt(false)"
                [disabled]="adapting()">
          <mat-icon>autorenew</mat-icon> Run adaptation now
        </button>
        <span class="muted small">Runs automatically every Sunday when
          AUTO_ADAPT_ENABLED is on. A preview changes nothing at all.</span>
      </div>

      @if (adaptRun(); as r) {
        <mat-card appearance="outlined" class="verdict"
                  [class.ok]="r.status === 'OK'" [class.no]="r.status !== 'OK'">
          <mat-icon>{{ r.status === 'OK' ? 'insights' : 'info' }}</mat-icon>
          <div>
            <p class="vsum"><b>
              @if (r.status !== 'OK') { {{ r.status }} }
              @else if (r.dry_run) { Preview — nothing was changed }
              @else { {{ r.promoted }} scope(s) updated }
            </b></p>
            @if (r.note) { <p class="muted small">{{ r.note }}</p> }
          </div>
        </mat-card>
        @if (r.scopes?.length) {
          <ul class="gates">
            @for (s of r.scopes; track s.scope) {
              <li [class.pass]="s.action === 'PROMOTED' || s.action === 'WOULD_PROMOTE'"
                  [class.fail]="s.action === 'REJECTED' || s.action === 'WOULD_REJECT'">
                <mat-icon>{{ adaptIcon(s.action) }}</mat-icon>
                <b>{{ scopeLabel(s.scope) }}</b>
                <span class="muted">{{ s.reason || s.summary }}</span>
              </li>
            }
          </ul>
        }
      }

      @if (a.events.length) {
        <h4>Change log</h4>
        <p class="muted small">Every decision, including the decisions to do
          nothing — otherwise "why hasn't it adapted?" is unanswerable.</p>
        <ul class="events">
          @for (e of a.events; track e.id) {
            <li>
              <span class="pill" [class.ahead]="e.action === 'PROMOTED'"
                    [class.behind]="e.action === 'ROLLED_BACK'">{{ e.action }}</span>
              <b>{{ scopeLabel(e.scope) }}</b>
              <span class="muted">{{ e.reason }}</span>
              <span class="muted when">{{ e.occurred_at | date: 'short' }}</span>
            </li>
          }
        </ul>
      }
    }

    <!-- ============ circuit breakers ============ -->
    @if (breakers(); as b) {
      <h3 class="cal-header">Circuit breakers
        <span class="muted">· when the system must stop trading itself</span></h3>
      <mat-card appearance="outlined" class="verdict"
                [class.ok]="!b.halted" [class.no]="b.halted">
        <mat-icon>{{ b.halted ? 'pause_circle' : 'play_circle' }}</mat-icon>
        <div>
          <p class="vsum"><b>{{ b.halted ? 'Entries halted' : 'Trading allowed' }}</b></p>
          <p class="muted small">{{ b.summary }}</p>
        </div>
      </mat-card>
      <ul class="gates">
        @for (br of b.breakers; track br.breaker) {
          <li [class.pass]="!br.tripped" [class.fail]="br.tripped">
            <mat-icon>{{ br.tripped ? (br.severity === 'HALT' ? 'cancel' : 'warning')
                                    : 'check_circle' }}</mat-icon>
            <b>{{ breakerLabel(br.breaker) }}</b>
            <span class="muted">{{ br.reason }}</span>
          </li>
        }
      </ul>
    }

    <!-- ============ promotion: the human decision ============ -->
    @if (shadowBoard(); as s) {
      <h3 class="cal-header">Champion &amp; challengers
        <span class="muted">· replayed on identical history — promotion is yours to make</span></h3>
      <p class="muted small">
        Live model: <b>{{ s.champion?.label ?? 'baseline defaults' }}</b>.
        {{ s.shadows.length }} challenger(s) in shadow,
        {{ s.promotable }} currently ahead. {{ s.note }}
      </p>

      @if (s.shadows.length) {
        @for (sh of s.shadows; track sh.version_id) {
          <mat-card appearance="outlined" class="challenger">
            <div class="chead">
              <b>{{ sh.label }}</b>
              <span class="pill" [class.ahead]="sh.verdict === 'CHALLENGER_AHEAD'"
                    [class.behind]="sh.verdict === 'CHAMPION_AHEAD'">
                {{ verdictLabel(sh.verdict) }}</span>
              <span class="muted small">#{{ sh.version_id }}</span>
            </div>
            <p class="muted small">{{ sh.note }}</p>
            @if (sh.status === 'OK') {
              <p class="muted small">
                Challenger IC <b>{{ sh.candidate_ic }}</b> vs champion
                <b>{{ sh.champion_ic }}</b> on {{ sh.n }} setups
                @if (sh.rank_agreement !== null && sh.rank_agreement !== undefined) {
                  · ranks {{ (sh.rank_agreement * 100) | number: '1.0-0' }}% the same
                }
              </p>
              @if (sh.candidate_weights; as cw) {
                <div class="chips">
                  @for (layer of layerOrder; track layer) {
                    <span class="wchip"><b>{{ layerLabel(layer) }}</b>
                      {{ cw[layer] }}</span>
                  }
                </div>
              }
              <button mat-stroked-button color="primary"
                      [disabled]="promoting() || sh.verdict !== 'CHALLENGER_AHEAD'"
                      (click)="promote(sh.version_id, sh.label ?? '')">
                <mat-icon>publish</mat-icon> Promote to champion
              </button>
              @if (sh.verdict !== 'CHALLENGER_AHEAD') {
                <span class="muted small hint">Only a challenger that is measurably
                  ahead can be promoted from here.</span>
              }
            }
          </mat-card>
        }
        <button mat-button (click)="rollback()" [disabled]="promoting()">
          <mat-icon>undo</mat-icon> Roll back to the previous champion
        </button>
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
    .small { font-size: 12.5px; }
    .propose-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
                   margin: 10px 0 14px; }
    .propose-row .muted { flex: 1 1 320px; line-height: 1.5; }
    .verdict { display: flex; gap: 12px; padding: 14px 16px; align-items: flex-start;
               border-left: 3px solid var(--text-dim); }
    .verdict.ok { border-left-color: var(--up); }
    .verdict.no { border-left-color: var(--down); }
    .verdict p { margin: 0 0 4px; }
    .vsum { font-size: 13.5px; }
    .gates { list-style: none; padding: 0; margin: 12px 0 0;
             display: flex; flex-direction: column; gap: 6px; }
    .gates li { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
    .gates mat-icon { font-size: 17px; width: 17px; height: 17px; }
    .gates li.pass mat-icon { color: var(--up); }
    .gates li.fail mat-icon { color: var(--down); }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 4px; }
    .wchip { font-size: 12px; padding: 5px 10px; border-radius: 8px;
             background: var(--surface-2); border: 1px solid var(--border);
             display: inline-flex; gap: 6px; align-items: baseline; }
    .wchip b { font-weight: 600; color: var(--text-dim); }
    .wchip em { font-style: normal; font-weight: 700; font-size: 11px; }
    .wchip.up em { color: var(--up); }
    .wchip.down em { color: var(--down); }
    .bucket { margin: 12px 0 4px; }
    .bhead { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
    .challenger { padding: 14px 16px; margin: 10px 0; }
    .challenger p { margin: 4px 0 8px; }
    .chead { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .pill { font-size: 10px; font-weight: 800; letter-spacing: 0.05em;
            padding: 2px 9px; border-radius: 999px; text-transform: uppercase;
            background: var(--surface-2); color: var(--text-dim); }
    .pill.ahead { background: rgba(38,166,154,0.15); color: var(--up); }
    .pill.behind { background: rgba(239,83,80,0.15); color: var(--down); }
    .hint { margin-left: 10px; }
    .scopes { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
              gap: 12px; margin: 12px 0; }
    .scope { padding: 14px 16px; }
    .scope.live { border-color: var(--accent); }
    .scope p { margin: 6px 0 4px; }
    .shead { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
             margin-bottom: 8px; }
    .events { list-style: none; padding: 0; margin: 8px 0 0;
              display: flex; flex-direction: column; gap: 8px; }
    .events li { display: flex; align-items: baseline; gap: 10px; font-size: 12.5px;
                 flex-wrap: wrap; padding-bottom: 8px;
                 border-bottom: 1px solid var(--border); }
    .events .when { margin-left: auto; white-space: nowrap; }
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
  readonly proposal = signal<WeightProposal | null>(null);
  readonly regimeWeights = signal<RegimeWeights | null>(null);
  readonly breakers = signal<CircuitBreakerReport | null>(null);
  readonly shadowBoard = signal<ShadowBoard | null>(null);
  readonly adaptation = signal<AdaptationHistory | null>(null);
  readonly adaptRun = signal<AdaptationRun | null>(null);
  readonly training = signal(false);
  readonly proposing = signal(false);
  readonly promoting = signal(false);
  readonly adapting = signal(false);

  /** Which weight scope today's regime is actually using. */
  readonly liveScope = computed(() => this.adaptation()?.current_scope ?? 'global');

  readonly layerOrder = ['technical', 'quality', 'news', 'momentum',
                         'ml', 'macro', 'regime'];

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
    this.loadRegimeWeights();
    this.loadGovernance();
    this.loadAdaptation();
  }

  private loadAdaptation(): void {
    this.api.getAdaptationHistory().subscribe({
      next: (a) => this.adaptation.set(a),
      error: () => this.adaptation.set(null),    // additive panel — fail quietly
    });
  }

  /** Trigger a tuning cycle. `preview` runs it with nothing persisted. */
  adapt(preview: boolean): void {
    this.adapting.set(true);
    this.api.runAdaptation(preview).subscribe({
      next: (r) => {
        this.adapting.set(false);
        this.adaptRun.set(r);
        this.snackBar.open(
          r.status !== 'OK' ? (r.note ?? r.status)
            : preview ? 'Preview complete — nothing changed'
            : `${r.promoted} scope(s) updated`,
          undefined, { duration: 5000 });
        if (!preview) { this.loadAdaptation(); this.loadGovernance(); }
      },
      error: () => {
        this.adapting.set(false);
        this.snackBar.open('Adaptation failed', 'Dismiss', { duration: 4000 });
      },
    });
  }

  /** The panic button: discard every automatic change in one step. */
  revert(scope: string): void {
    const actor = window.prompt(
      `Revert ${this.scopeLabel(scope)} to the weights you approved?\n\nYour name:`);
    if (!actor?.trim()) return;
    this.adapting.set(true);
    this.api.revertToAnchor(actor.trim(), scope).subscribe({
      next: () => {
        this.adapting.set(false);
        this.snackBar.open('Reverted to your baseline', undefined,
                           { duration: 4000 });
        this.loadAdaptation();
      },
      error: () => {
        this.adapting.set(false);
        this.snackBar.open('Revert failed', 'Dismiss', { duration: 4000 });
      },
    });
  }

  scopeLabel(scope: string): string {
    return { global: 'All conditions (global)', risk_on: 'Risk-on markets',
             neutral: 'Neutral / choppy markets',
             risk_off: 'Risk-off markets' }[scope] ?? scope;
  }

  adaptIcon(action: string): string {
    return { PROMOTED: 'check_circle', WOULD_PROMOTE: 'task_alt',
             REJECTED: 'cancel', WOULD_REJECT: 'block',
             SKIPPED: 'schedule', ROLLED_BACK: 'undo' }[action] ?? 'info';
  }

  private loadGovernance(): void {
    this.api.getCircuitBreakers().subscribe({
      next: (b) => this.breakers.set(b),
      error: () => this.breakers.set(null),      // additive panel — fail quietly
    });
    this.api.getShadowBoard().subscribe({
      next: (s) => this.shadowBoard.set(s),
      error: () => this.shadowBoard.set(null),
    });
  }

  /** Promotion is the one place a human must be named — the audit trail is the
   *  whole reason the registry exists. */
  promote(versionId: number, label: string): void {
    const approvedBy = window.prompt(
      `Promote "${label}" to champion?\n\nYour name (recorded in the audit trail):`);
    if (!approvedBy?.trim()) return;
    const reason = window.prompt('Reason (optional):') ?? undefined;
    this.promoting.set(true);
    this.api.promoteModel(versionId, approvedBy.trim(), reason).subscribe({
      next: () => {
        this.promoting.set(false);
        this.snackBar.open(`${label} is now the champion`, undefined,
                           { duration: 4000 });
        this.loadGovernance();
        this.loadCalibration();
      },
      error: () => {
        this.promoting.set(false);
        this.snackBar.open('Promotion failed', 'Dismiss', { duration: 4000 });
      },
    });
  }

  rollback(): void {
    const actor = window.prompt('Roll back to the previous champion.\n\nYour name:');
    if (!actor?.trim()) return;
    this.promoting.set(true);
    this.api.rollbackModel(actor.trim(), window.prompt('Reason (optional):')
                                         ?? undefined).subscribe({
      next: () => {
        this.promoting.set(false);
        this.snackBar.open('Rolled back', undefined, { duration: 4000 });
        this.loadGovernance();
      },
      error: () => {
        this.promoting.set(false);
        this.snackBar.open('Rollback failed', 'Dismiss', { duration: 4000 });
      },
    });
  }

  breakerLabel(breaker: string): string {
    return { drawdown: 'Drawdown', loss_streak: 'Losing streak',
             ic_collapse: 'Signal decay', stale_data: 'Data freshness',
             dead_labels: 'Learning loop' }[breaker] ?? breaker;
  }

  verdictLabel(verdict: string | undefined): string {
    return { CHALLENGER_AHEAD: 'Ahead', CHAMPION_AHEAD: 'Behind', TIE: 'Tied',
             UNCLEAR: 'Unclear', NO_DATA: 'No history',
             INSUFFICIENT: 'Too little history' }[verdict ?? ''] ?? 'Unknown';
  }

  private loadRegimeWeights(): void {
    this.api.getRegimeWeights().subscribe({
      next: (r) => this.regimeWeights.set(r),
      error: () => this.regimeWeights.set(null),   // additive panel — fail quietly
    });
  }

  /** Fit a challenger and run the gates. Deliberately manual: this is a decision
   *  point, not background housekeeping. */
  propose(): void {
    this.proposing.set(true);
    this.api.proposeWeights().subscribe({
      next: (p) => {
        this.proposing.set(false);
        this.proposal.set(p);
        this.snackBar.open(p.summary ?? 'Proposal complete', undefined,
                           { duration: 5000 });
        this.loadRegimeWeights();
      },
      error: () => {
        this.proposing.set(false);
        this.snackBar.open('Could not run the proposal', 'Dismiss',
                           { duration: 4000 });
      },
    });
  }

  gateLabel(gate: string): string {
    return { sample_size: 'Sample size', oos_ic: 'Out-of-sample IC',
             turnover: 'Ranking churn', sign_flip: 'Direction reversal',
             stability: 'Bootstrap stability' }[gate] ?? gate;
  }

  bucketLabel(bucket: string): string {
    return { risk_on: 'Risk-on', neutral: 'Neutral / chop',
             risk_off: 'Risk-off' }[bucket] ?? bucket;
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
