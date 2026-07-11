import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormControl, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { debounceTime, distinctUntilChanged, filter, switchMap } from 'rxjs';
import { toSignal } from '@angular/core/rxjs-interop';

import { PaperAccount, PaperOrder, SymbolInfo } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

@Component({
  selector: 'app-portfolio-page',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, MatCardModule, MatButtonModule,
            MatButtonToggleModule, MatFormFieldModule, MatInputModule, MatAutocompleteModule,
            MatIconModule, MatTableModule, MatProgressSpinnerModule, MatSnackBarModule,
            MatTooltipModule],
  template: `
    <div class="header-row">
      <h2>Paper Portfolio</h2>
      <button mat-stroked-button color="warn" (click)="reset()"
              matTooltip="Wipe positions, restore starting cash">
        <mat-icon>restart_alt</mat-icon> Reset account
      </button>
    </div>

    @if (account(); as a) {
      <div class="cards">
        <mat-card appearance="outlined" class="card">
          <span class="value">₹{{ a.equity | number: '1.0-0' }}</span>
          <span class="label">Equity</span>
        </mat-card>
        <mat-card appearance="outlined" class="card">
          <span class="value">₹{{ a.cash | number: '1.0-0' }}</span>
          <span class="label">Cash</span>
        </mat-card>
        <mat-card appearance="outlined" class="card">
          <span class="value" [class.up]="a.realizedPnl > 0" [class.down]="a.realizedPnl < 0">
            ₹{{ a.realizedPnl | number: '1.0-0' }}</span>
          <span class="label">Realized P&L</span>
        </mat-card>
        <mat-card appearance="outlined" class="card">
          <span class="value" [class.up]="a.unrealizedPnl > 0" [class.down]="a.unrealizedPnl < 0">
            ₹{{ a.unrealizedPnl | number: '1.0-0' }}</span>
          <span class="label">Unrealized P&L</span>
        </mat-card>
      </div>

      <!-- ============ order ticket ============ -->
      <mat-card appearance="outlined" class="ticket">
        <h3>Place order</h3>
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

          <mat-button-toggle-group [(ngModel)]="side">
            <mat-button-toggle value="BUY" class="buy-toggle">BUY</mat-button-toggle>
            <mat-button-toggle value="SELL" class="sell-toggle">SELL</mat-button-toggle>
          </mat-button-toggle-group>

          <mat-form-field appearance="outline" class="w-qty">
            <mat-label>Quantity</mat-label>
            <input matInput type="number" [(ngModel)]="quantity" min="1">
          </mat-form-field>

          <button mat-flat-button color="primary" (click)="placeOrder()" [disabled]="busy()">
            <mat-icon>send</mat-icon> Submit
          </button>
        </div>
        <p class="muted">Market order · fills at delayed quote when available, else last close.</p>
      </mat-card>

      <!-- ============ positions ============ -->
      <h3>Positions ({{ a.positions.length }})</h3>
      @if (a.positions.length) {
        <table mat-table [dataSource]="a.positions" class="table">
          <ng-container matColumnDef="ticker">
            <th mat-header-cell *matHeaderCellDef>Ticker</th>
            <td mat-cell *matCellDef="let p"><b>{{ p.ticker }}</b> <span class="muted">{{ p.name }}</span></td>
          </ng-container>
          <ng-container matColumnDef="quantity">
            <th mat-header-cell *matHeaderCellDef>Qty</th>
            <td mat-cell *matCellDef="let p">{{ p.quantity }}</td>
          </ng-container>
          <ng-container matColumnDef="avgCost">
            <th mat-header-cell *matHeaderCellDef>Avg cost</th>
            <td mat-cell *matCellDef="let p">₹{{ p.avgCost | number: '1.2-2' }}</td>
          </ng-container>
          <ng-container matColumnDef="lastPrice">
            <th mat-header-cell *matHeaderCellDef>Last</th>
            <td mat-cell *matCellDef="let p">₹{{ p.lastPrice | number: '1.2-2' }}</td>
          </ng-container>
          <ng-container matColumnDef="marketValue">
            <th mat-header-cell *matHeaderCellDef>Value</th>
            <td mat-cell *matCellDef="let p">₹{{ p.marketValue | number: '1.0-0' }}</td>
          </ng-container>
          <ng-container matColumnDef="unrealizedPnl">
            <th mat-header-cell *matHeaderCellDef>Unrealized</th>
            <td mat-cell *matCellDef="let p" [class.up]="p.unrealizedPnl > 0"
                [class.down]="p.unrealizedPnl < 0">
              ₹{{ p.unrealizedPnl | number: '1.0-0' }}
            </td>
          </ng-container>
          <tr mat-header-row *matHeaderRowDef="positionColumns"></tr>
          <tr mat-row *matRowDef="let p; columns: positionColumns"></tr>
        </table>
      } @else {
        <p class="muted">No open positions — place your first paper trade above.</p>
      }
    }

    @if (busy()) {
      <div class="spinner"><mat-spinner diameter="32" /></div>
    }

    <!-- ============ order history ============ -->
    <h3>Order history</h3>
    @if (orders().length) {
      <table mat-table [dataSource]="orders()" class="table">
        <ng-container matColumnDef="placedAt">
          <th mat-header-cell *matHeaderCellDef>Time</th>
          <td mat-cell *matCellDef="let o">{{ o.placedAt | date: 'MMM d, HH:mm' }}</td>
        </ng-container>
        <ng-container matColumnDef="ticker">
          <th mat-header-cell *matHeaderCellDef>Ticker</th>
          <td mat-cell *matCellDef="let o">{{ o.ticker }}</td>
        </ng-container>
        <ng-container matColumnDef="side">
          <th mat-header-cell *matHeaderCellDef>Side</th>
          <td mat-cell *matCellDef="let o" [class.up]="o.side === 'BUY'"
              [class.down]="o.side === 'SELL'">{{ o.side }}</td>
        </ng-container>
        <ng-container matColumnDef="quantity">
          <th mat-header-cell *matHeaderCellDef>Qty</th>
          <td mat-cell *matCellDef="let o">{{ o.quantity }}</td>
        </ng-container>
        <ng-container matColumnDef="price">
          <th mat-header-cell *matHeaderCellDef>Price</th>
          <td mat-cell *matCellDef="let o">
            @if (o.price !== null) { ₹{{ o.price | number: '1.2-2' }}
              <span class="muted">({{ o.priceSource }})</span> } @else { — }
          </td>
        </ng-container>
        <ng-container matColumnDef="status">
          <th mat-header-cell *matHeaderCellDef>Status</th>
          <td mat-cell *matCellDef="let o">
            {{ o.status }}
            @if (o.rejectReason) { <span class="muted">· {{ o.rejectReason }}</span> }
            @if (o.realizedPnl !== null) {
              <span [class.up]="o.realizedPnl > 0" [class.down]="o.realizedPnl < 0">
                · ₹{{ o.realizedPnl | number: '1.0-0' }}</span>
            }
          </td>
        </ng-container>
        <tr mat-header-row *matHeaderRowDef="orderColumns"></tr>
        <tr mat-row *matRowDef="let o; columns: orderColumns"></tr>
      </table>
    } @else {
      <p class="muted">No orders yet.</p>
    }
  `,
  styles: `
    h2, h3 { font-weight: 500; }
    .header-row { display: flex; justify-content: space-between; align-items: center; }
    .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
             gap: 12px; margin-bottom: 16px; }
    .card { padding: 14px; display: flex; flex-direction: column; gap: 4px; }
    .value { font-size: 22px; font-weight: 600; }
    .label { font-size: 12px; opacity: 0.65; }
    .ticket { padding: 16px; margin-bottom: 20px; }
    .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    .w-ticker { min-width: 260px; }
    .w-qty { width: 140px; }
    .buy-toggle.mat-button-toggle-checked { background: rgba(38, 166, 154, 0.25); }
    .sell-toggle.mat-button-toggle-checked { background: rgba(239, 83, 80, 0.25); }
    .table { width: 100%; margin-bottom: 20px; }
    .up { color: #26a69a; }
    .down { color: #ef5350; }
    .muted { opacity: 0.6; font-size: 12px; }
    .spinner { display: flex; justify-content: center; padding: 16px; }
  `,
})
export class PortfolioPageComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  private readonly snackBar = inject(MatSnackBar);

  readonly positionColumns = ['ticker', 'quantity', 'avgCost', 'lastPrice', 'marketValue', 'unrealizedPnl'];
  readonly orderColumns = ['placedAt', 'ticker', 'side', 'quantity', 'price', 'status'];

  readonly account = signal<PaperAccount | null>(null);
  readonly orders = signal<PaperOrder[]>([]);
  readonly busy = signal(false);

  readonly tickerControl = new FormControl('', { nonNullable: true });
  side: 'BUY' | 'SELL' = 'BUY';
  quantity = 1;

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
    this.refresh();
  }

  refresh(): void {
    this.api.getPaperAccount().subscribe({
      next: (a) => this.account.set(a),
      error: () => this.snackBar.open('Failed to load account', 'Dismiss', { duration: 4000 }),
    });
    this.api.listPaperOrders().subscribe({
      next: (o) => this.orders.set(o),
      error: () => {},
    });
  }

  placeOrder(): void {
    const ticker = this.tickerControl.value.trim().toUpperCase();
    if (!ticker || this.quantity < 1) {
      this.snackBar.open('Enter a symbol and a positive quantity', 'Dismiss', { duration: 3000 });
      return;
    }
    this.busy.set(true);
    this.api.placePaperOrder(ticker, this.side, this.quantity).subscribe({
      next: (order) => {
        this.busy.set(false);
        const msg = order.status === 'FILLED'
          ? `${order.side} ${order.quantity} ${order.ticker} @ ₹${order.price}`
          : `Rejected: ${order.rejectReason}`;
        this.snackBar.open(msg, undefined, { duration: 4000 });
        this.refresh();
      },
      error: (err) => {
        this.busy.set(false);
        this.snackBar.open(err?.error?.message ?? 'Order failed', 'Dismiss', { duration: 5000 });
      },
    });
  }

  reset(): void {
    this.busy.set(true);
    this.api.resetPaperAccount().subscribe({
      next: () => { this.busy.set(false); this.refresh(); },
      error: () => { this.busy.set(false); this.snackBar.open('Reset failed', 'Dismiss', { duration: 4000 }); },
    });
  }
}
