import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';

import { FxAccountReport, FxTradeReview } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

/**
 * Exness (MetaTrader 5) FX & crypto account — read-only.
 *
 * Deliberately risk-first, not conviction-scored: the Alpha Stack's edge is
 * fundamentals, NSE relative strength and Indian-market regime, none of which
 * mean anything for EURUSD or BTCUSD. What does transfer is arithmetic on your
 * own position — stops, margin, exposure — so that's what this shows.
 */
@Component({
  selector: 'app-exness-account',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule, MatIconModule,
            MatProgressSpinnerModule, MatTableModule, MatTooltipModule],
  template: `
    @if (loading()) {
      <div class="loading"><mat-spinner diameter="28" /> Reading your MT5 terminal…</div>
    } @else if (data()) {
      <!-- the as alias binds only on a primary if, so read the signal into d here -->
      @if (data(); as d) {

      @if (d.status === 'OK') {
        @if (d.account; as a) {
          <div class="cards">
            <mat-card appearance="outlined" class="card metric">
              <span class="value metric-value">{{ a.equity | number: '1.2-2' }}</span>
              <span class="label">Equity ({{ a.currency }})</span>
            </mat-card>
            <mat-card appearance="outlined" class="card metric">
              <span class="value metric-value">{{ a.balance | number: '1.2-2' }}</span>
              <span class="label">Balance</span>
            </mat-card>
            <mat-card appearance="outlined" class="card metric">
              <span class="value metric-value" [class.up]="a.profit > 0" [class.down]="a.profit < 0">
                {{ a.profit | number: '1.2-2' }}</span>
              <span class="label">Floating P&L</span>
            </mat-card>
            <mat-card appearance="outlined" class="card metric">
              <span class="value metric-value" [class.down]="a.margin_level > 0 && a.margin_level < 300">
                {{ a.margin_level ? (a.margin_level | number: '1.0-0') + '%' : '—' }}</span>
              <span class="label">Margin level</span>
            </mat-card>
          </div>
          <p class="acct-line">
            Account {{ a.login }} · {{ a.server }}
            @if (a.leverage) { · 1:{{ a.leverage }} leverage }
            · free margin {{ a.margin_free | number: '1.2-2' }} {{ a.currency }}
          </p>
        }

        @if (d.actions?.length) {
          <mat-card appearance="outlined" class="risk">
            <div class="risk-head">
              <mat-icon>shield</mat-icon>
              <h3>Risk queue</h3>
              @if (d.summary && d.summary.high_priority > 0) {
                <span class="hi">{{ d.summary.high_priority }} high priority</span>
              }
            </div>
            @for (a of d.actions; track $index) {
              <div class="act" [class]="'act ' + a.severity">
                <mat-icon>{{ a.severity === 'high' ? 'error' :
                             a.severity === 'medium' ? 'warning_amber' : 'info' }}</mat-icon>
                <span>{{ a.text }}</span>
              </div>
            }
          </mat-card>
        }

        @if (d.positions?.length) {
          <table mat-table [dataSource]="d.positions ?? []" class="table">
            <ng-container matColumnDef="symbol">
              <th mat-header-cell *matHeaderCellDef>Symbol</th>
              <td mat-cell *matCellDef="let p"><strong>{{ p.symbol }}</strong></td>
            </ng-container>
            <ng-container matColumnDef="side">
              <th mat-header-cell *matHeaderCellDef>Side</th>
              <td mat-cell *matCellDef="let p" [class.up]="p.side === 'BUY'"
                  [class.down]="p.side === 'SELL'">{{ p.side }}</td>
            </ng-container>
            <ng-container matColumnDef="volume">
              <th mat-header-cell *matHeaderCellDef>Lots</th>
              <td mat-cell *matCellDef="let p">{{ p.volume }}</td>
            </ng-container>
            <ng-container matColumnDef="price_open">
              <th mat-header-cell *matHeaderCellDef>Open</th>
              <td mat-cell *matCellDef="let p">{{ p.price_open }}</td>
            </ng-container>
            <ng-container matColumnDef="price_current">
              <th mat-header-cell *matHeaderCellDef>Now</th>
              <td mat-cell *matCellDef="let p">{{ p.price_current }}</td>
            </ng-container>
            <ng-container matColumnDef="stop_loss">
              <th mat-header-cell *matHeaderCellDef>Stop</th>
              <td mat-cell *matCellDef="let p">
                @if (p.stop_loss) { {{ p.stop_loss }} }
                @else { <span class="nostop">none</span> }
              </td>
            </ng-container>
            <ng-container matColumnDef="profit">
              <th mat-header-cell *matHeaderCellDef>P&L</th>
              <td mat-cell *matCellDef="let p" [class.up]="p.profit > 0" [class.down]="p.profit < 0">
                {{ p.profit | number: '1.2-2' }}
                @if (p.pnl_pct !== null) {
                  <span class="pct">({{ p.pnl_pct > 0 ? '+' : '' }}{{ p.pnl_pct | number: '1.2-2' }}%)</span>
                }
              </td>
            </ng-container>
            <tr mat-header-row *matHeaderRowDef="columns"></tr>
            <tr mat-row *matRowDef="let p; columns: columns"></tr>
          </table>
        } @else {
          <p class="muted">Connected — no open positions right now.</p>
        }

        <!-- ===== closed-trade analysis: the honest edge check ===== -->
        @if (review(); as rv) {
          @if (rv.status === 'OK' && rv.stats) {
            <div class="rev-head">
              <mat-icon>insights</mat-icon>
              <h3>Trade analysis</h3>
              <span class="muted">last {{ rv.days }} days · {{ rv.stats.trades }} closed</span>
            </div>
            <div class="cards">
              <mat-card appearance="outlined" class="card metric">
                <span class="value metric-value" [class.up]="rv.stats.net > 0"
                      [class.down]="rv.stats.net < 0">{{ rv.stats.net | number: '1.2-2' }}</span>
                <span class="label">Net P&L</span>
              </mat-card>
              <mat-card appearance="outlined" class="card metric">
                <span class="value metric-value">{{ rv.stats.win_rate_pct }}%</span>
                <span class="label">Win rate ({{ rv.stats.wins }}W/{{ rv.stats.losses }}L)</span>
              </mat-card>
              <mat-card appearance="outlined" class="card metric">
                <span class="value metric-value"
                      [class.up]="(rv.stats.profit_factor ?? 0) > 1"
                      [class.down]="(rv.stats.profit_factor ?? 0) < 1">
                  {{ rv.stats.profit_factor ?? '—' }}</span>
                <span class="label">Profit factor</span>
              </mat-card>
              <mat-card appearance="outlined" class="card metric">
                <span class="value metric-value" [class.up]="rv.stats.expectancy > 0"
                      [class.down]="rv.stats.expectancy < 0">
                  {{ rv.stats.expectancy | number: '1.2-2' }}</span>
                <span class="label">Per trade</span>
              </mat-card>
            </div>
            <p class="acct-line">
              Avg win {{ rv.stats.avg_win | number: '1.2-2' }} vs avg loss
              {{ rv.stats.avg_loss | number: '1.2-2' }} (payoff {{ rv.stats.payoff_ratio ?? '—' }})
              · swap {{ rv.stats.swap_total | number: '1.2-2' }}
              · commission {{ rv.stats.commission_total | number: '1.2-2' }}
            </p>

            @if (rv.leaks?.length) {
              <mat-card appearance="outlined" class="risk">
                <div class="risk-head">
                  <mat-icon>psychology_alt</mat-icon>
                  <h3>What's costing you</h3>
                </div>
                @for (l of rv.leaks; track $index) {
                  <div class="act" [class]="'act ' + l.severity">
                    <mat-icon>{{ l.severity === 'high' ? 'error' : 'warning_amber' }}</mat-icon>
                    <span>{{ l.text }}</span>
                  </div>
                }
              </mat-card>
            }

            @if (rv.symbols?.length) {
              <table mat-table [dataSource]="rv.symbols ?? []" class="table">
                <ng-container matColumnDef="symbol">
                  <th mat-header-cell *matHeaderCellDef>Symbol</th>
                  <td mat-cell *matCellDef="let s"><strong>{{ s.symbol }}</strong></td>
                </ng-container>
                <ng-container matColumnDef="trades">
                  <th mat-header-cell *matHeaderCellDef>Trades</th>
                  <td mat-cell *matCellDef="let s">{{ s.trades }}</td>
                </ng-container>
                <ng-container matColumnDef="win_rate_pct">
                  <th mat-header-cell *matHeaderCellDef>Win %</th>
                  <td mat-cell *matCellDef="let s">{{ s.win_rate_pct }}%</td>
                </ng-container>
                <ng-container matColumnDef="net">
                  <th mat-header-cell *matHeaderCellDef>Net</th>
                  <td mat-cell *matCellDef="let s" [class.up]="s.net > 0" [class.down]="s.net < 0">
                    {{ s.net | number: '1.2-2' }}</td>
                </ng-container>
                <tr mat-header-row *matHeaderRowDef="symbolColumns"></tr>
                <tr mat-row *matRowDef="let s; columns: symbolColumns"></tr>
              </table>
            }
          } @else if (rv.status === 'NO_TRADES') {
            <p class="muted">{{ rv.note }}</p>
          }
        }

      } @else {
        <mat-card appearance="outlined" class="setup">
          <div class="setup-head">
            <mat-icon>power_settings_new</mat-icon>
            <h3>MetaTrader 5 not connected</h3>
          </div>
          <p class="muted">{{ d.note }}</p>
          <ol class="steps">
            <li>Exness has no public REST API for retail accounts — the app reads your
              account through the <strong>MetaTrader 5 terminal</strong> running on this machine.</li>
            <li>Install the bridge on the machine running the Python service:
              <code>pip install MetaTrader5</code> (Windows only).</li>
            <li>Open MetaTrader 5, log into your Exness account, and leave it running.</li>
            <li>Optional — pin a specific account in <code>.env</code>:
              <code>MT5_LOGIN</code>, <code>MT5_PASSWORD</code>, <code>MT5_SERVER</code>
              (e.g. Exness-MT5Real). Blank uses whichever account the terminal is logged into.</li>
          </ol>
          <p class="ro">Read-only: the app requests account state and open positions.
            It has no order, modify, or close functions.</p>
        </mat-card>
      }
      }
    }

    <div class="foot">
      <button mat-stroked-button (click)="load()" [disabled]="loading()">
        <mat-icon>refresh</mat-icon> {{ loading() ? 'Reading…' : 'Refresh' }}
      </button>
    </div>
  `,
  styles: `
    .loading { display: flex; align-items: center; gap: 12px; color: var(--text-dim);
               padding: 24px 0; }
    .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
             gap: 12px; margin-bottom: 10px; }
    .card { padding: 14px; display: flex; flex-direction: column; gap: 4px; }
    .value { font-size: 21px; font-weight: 600; }
    .label { font-size: 12px; opacity: 0.65; }
    .acct-line { font-size: 12px; color: var(--text-dim); margin: 0 0 16px; }
    .rev-head { display: flex; align-items: center; gap: 8px; margin: 26px 0 12px; }
    .rev-head h3 { margin: 0; font-weight: 600; }
    .rev-head mat-icon { color: var(--accent-2); }
    .risk { padding: 14px 18px; margin-bottom: 16px; }
    .risk-head { display: flex; align-items: center; gap: 8px; }
    .risk-head h3 { margin: 0; font-weight: 600; }
    .risk-head mat-icon { color: var(--accent); }
    .hi { font-size: 11px; font-weight: 800; padding: 3px 10px; border-radius: 999px;
          background: rgba(239,83,80,0.15); color: var(--down); }
    .act { display: flex; align-items: flex-start; gap: 8px; padding: 7px 0;
           font-size: 13px; line-height: 1.45; }
    .act mat-icon { font-size: 17px; width: 17px; height: 17px; margin-top: 1px;
                    flex-shrink: 0; }
    .act.high { color: var(--down); }
    .act.medium { color: #ffb74d; }
    .act.info { color: var(--text-dim); }
    .table { width: 100%; }
    .nostop { color: var(--down); font-weight: 600; }
    .pct { font-size: 11px; opacity: 0.7; margin-left: 4px; }
    .up { color: var(--up); }
    .down { color: var(--down); }
    .muted { opacity: 0.65; font-size: 13px; }
    .setup { padding: 18px 22px; }
    .setup-head { display: flex; align-items: center; gap: 10px; }
    .setup-head h3 { margin: 0; font-weight: 600; }
    .setup-head mat-icon { color: #ffb74d; }
    .steps { margin: 14px 0 8px; padding-left: 22px; font-size: 13px; line-height: 1.8;
             color: var(--text-dim); }
    .steps code { background: var(--card-border); border-radius: 6px; padding: 1px 6px;
                  font-family: 'JetBrains Mono', monospace; font-size: 11.5px; }
    .ro { font-size: 12px; color: var(--up); margin: 10px 0 0; }
    .foot { margin-top: 14px; }
  `,
})
export class ExnessAccountComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  readonly data = signal<FxAccountReport | null>(null);
  readonly review = signal<FxTradeReview | null>(null);
  readonly loading = signal(false);
  readonly columns = ['symbol', 'side', 'volume', 'price_open', 'price_current',
                      'stop_loss', 'profit'];
  readonly symbolColumns = ['symbol', 'trades', 'win_rate_pct', 'net'];

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.api.getExnessAccount().subscribe({
      next: (d) => {
        this.data.set(d);
        this.loading.set(false);
        // Trade history only matters once the terminal is actually reachable.
        if (d.status === 'OK') { this.loadReview(); }
      },
      error: () => {
        this.loading.set(false);
        this.data.set({ status: 'ERROR',
                        note: 'Could not reach the data service.' });
      },
    });
  }

  private loadReview(): void {
    this.api.getExnessTrades(90).subscribe({
      next: (r) => this.review.set(r),
      error: () => this.review.set(null),      // analysis is additive — fail quietly
    });
  }
}
