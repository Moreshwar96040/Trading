import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';

/** Application shell: toolbar + navigation sidenav. New features add a nav entry here. */
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, MatToolbarModule,
            MatSidenavModule, MatListModule, MatIconModule],
  template: `
    <mat-toolbar class="toolbar">
      <mat-icon>candlestick_chart</mat-icon>
      <span class="title">Trading Platform</span>
      <span class="spacer"></span>
      <span class="phase">NSE · All 7 phases</span>
    </mat-toolbar>

    <mat-sidenav-container class="container">
      <mat-sidenav mode="side" opened class="sidenav">
        <mat-nav-list>
          <a mat-list-item routerLink="/chart" routerLinkActive="active-link">
            <mat-icon matListItemIcon>show_chart</mat-icon>
            <span matListItemTitle>Charts</span>
          </a>
          <a mat-list-item routerLink="/screener" routerLinkActive="active-link">
            <mat-icon matListItemIcon>filter_alt</mat-icon>
            <span matListItemTitle>Screener</span>
          </a>
          <a mat-list-item routerLink="/fundamentals" routerLinkActive="active-link">
            <mat-icon matListItemIcon>account_balance</mat-icon>
            <span matListItemTitle>Fundamentals</span>
          </a>
          <a mat-list-item routerLink="/strategies" routerLinkActive="active-link">
            <mat-icon matListItemIcon>psychology</mat-icon>
            <span matListItemTitle>Strategies</span>
          </a>
          <a mat-list-item routerLink="/portfolio" routerLinkActive="active-link">
            <mat-icon matListItemIcon>account_balance_wallet</mat-icon>
            <span matListItemTitle>Portfolio</span>
          </a>
          <a mat-list-item routerLink="/risk" routerLinkActive="active-link">
            <mat-icon matListItemIcon>shield</mat-icon>
            <span matListItemTitle>Risk</span>
          </a>
          <a mat-list-item routerLink="/alerts" routerLinkActive="active-link">
            <mat-icon matListItemIcon>notifications</mat-icon>
            <span matListItemTitle>Alerts</span>
          </a>
          <a mat-list-item routerLink="/journal" routerLinkActive="active-link">
            <mat-icon matListItemIcon>menu_book</mat-icon>
            <span matListItemTitle>Journal</span>
          </a>
          <a mat-list-item routerLink="/ai" routerLinkActive="active-link">
            <mat-icon matListItemIcon>auto_awesome</mat-icon>
            <span matListItemTitle>AI Analysis</span>
          </a>
        </mat-nav-list>
      </mat-sidenav>

      <mat-sidenav-content class="content">
        <router-outlet />
      </mat-sidenav-content>
    </mat-sidenav-container>
  `,
  styles: `
    :host { display: flex; flex-direction: column; height: 100%; }
    .toolbar { gap: 8px; }
    .title { font-weight: 500; }
    .spacer { flex: 1; }
    .phase { font-size: 12px; opacity: 0.6; }
    .container { flex: 1; }
    .sidenav { width: 200px; }
    .content { padding: 16px; }
    .active-link { background: var(--mat-sys-surface-container-highest); }
  `,
})
export class AppComponent {}
