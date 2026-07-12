import { CommonModule } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ThemeService } from './core/services/theme.service';

interface NavItem { path: string; icon: string; title: string; }
interface NavSection { label: string; items: NavItem[]; }

const NAV_SECTIONS: NavSection[] = [
  {
    label: 'Overview',
    items: [
      { path: '/dashboard', icon: 'space_dashboard', title: 'Trade Desk' },
    ],
  },
  {
    label: 'Markets',
    items: [
      { path: '/chart', icon: 'candlestick_chart', title: 'Charts' },
      { path: '/screener', icon: 'filter_alt', title: 'Screener' },
      { path: '/fundamentals', icon: 'account_balance', title: 'Fundamentals' },
    ],
  },
  {
    label: 'Strategy',
    items: [
      { path: '/strategies', icon: 'psychology', title: 'Strategies' },
      { path: '/ai', icon: 'auto_awesome', title: 'AI Analysis' },
    ],
  },
  {
    label: 'Portfolio',
    items: [
      { path: '/portfolio', icon: 'account_balance_wallet', title: 'Portfolio' },
      { path: '/risk', icon: 'shield', title: 'Risk' },
      { path: '/alerts', icon: 'notifications', title: 'Alerts' },
      { path: '/journal', icon: 'menu_book', title: 'Journal' },
    ],
  },
];

/** Application shell: glass toolbar + grouped navigation. New features add a nav entry here. */
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive, MatToolbarModule,
            MatSidenavModule, MatListModule, MatIconModule, MatButtonModule,
            MatTooltipModule],
  template: `
    <mat-toolbar class="toolbar">
      <div class="brand-mark"><mat-icon>candlestick_chart</mat-icon></div>
      <span class="title">Trading Platform</span>
      <span class="badge">NSE</span>
      <span class="spacer"></span>
      <div class="market-status" [class.open]="marketOpen()">
        <span class="dot"></span>
        {{ marketOpen() ? 'Market open' : 'Market closed' }}
      </div>
      <span class="clock">{{ istNow() | date: 'HH:mm:ss' }} IST</span>
      <button mat-icon-button (click)="theme.toggle()"
              [matTooltip]="theme.mode() === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'">
        <mat-icon>{{ theme.mode() === 'dark' ? 'light_mode' : 'dark_mode' }}</mat-icon>
      </button>
    </mat-toolbar>

    <mat-sidenav-container class="container">
      <mat-sidenav mode="side" opened class="sidenav">
        @for (section of sections; track section.label) {
          <div class="section-label">{{ section.label }}</div>
          <mat-nav-list>
            @for (item of section.items; track item.path) {
              <a mat-list-item [routerLink]="item.path" routerLinkActive="active-link">
                <mat-icon matListItemIcon>{{ item.icon }}</mat-icon>
                <span matListItemTitle>{{ item.title }}</span>
              </a>
            }
          </mat-nav-list>
        }
        <div class="sidenav-footer">
          <span class="dot-mini"></span> Paper trading · educational
        </div>
      </mat-sidenav>

      <mat-sidenav-content class="content">
        <router-outlet />
      </mat-sidenav-content>
    </mat-sidenav-container>
  `,
  styles: `
    :host { display: flex; flex-direction: column; height: 100%; }

    .toolbar {
      gap: 12px;
      background: var(--shell-glass);
      backdrop-filter: blur(18px);
      border-bottom: 1px solid var(--card-border);
      transition: background 0.3s ease;
    }
    .brand-mark {
      width: 34px; height: 34px; border-radius: 10px;
      display: grid; place-items: center;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      box-shadow: 0 0 18px rgba(56, 189, 248, 0.45);
    }
    .brand-mark mat-icon { color: #061020; }
    .title {
      font-weight: 700; font-size: 17px; letter-spacing: -0.01em;
      background: linear-gradient(90deg, var(--title-from), var(--title-to));
      -webkit-background-clip: text; background-clip: text; color: transparent;
    }
    .badge {
      font-size: 10px; font-weight: 700; letter-spacing: 0.1em;
      padding: 3px 8px; border-radius: 999px;
      color: var(--accent); border: 1px solid rgba(56, 189, 248, 0.35);
      background: rgba(56, 189, 248, 0.1);
    }
    .spacer { flex: 1; }

    .market-status {
      display: flex; align-items: center; gap: 7px;
      font-size: 12px; font-weight: 600; color: var(--text-dim);
      padding: 5px 12px; border-radius: 999px;
      border: 1px solid var(--card-border); background: var(--glass-bg);
    }
    .market-status .dot {
      width: 8px; height: 8px; border-radius: 50%; background: #64748b;
    }
    .market-status.open { color: var(--up); border-color: rgba(38, 166, 154, 0.4); }
    .market-status.open .dot {
      background: var(--up);
      animation: pulse 1.8s ease-out infinite;
    }
    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 rgba(38, 166, 154, 0.55); }
      70% { box-shadow: 0 0 0 8px rgba(38, 166, 154, 0); }
      100% { box-shadow: 0 0 0 0 rgba(38, 166, 154, 0); }
    }
    .clock { font-size: 12px; color: var(--text-dim); font-variant-numeric: tabular-nums; }

    .container { flex: 1; }
    .sidenav {
      width: 216px;
      background: var(--shell-glass);
      backdrop-filter: blur(18px);
      border-right: 1px solid var(--card-border);
      padding: 8px 0;
      transition: background 0.3s ease;
    }
    .section-label {
      font-size: 10px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase;
      color: #64748b; padding: 14px 20px 4px;
    }
    a[mat-list-item] {
      border-radius: 10px;
      margin: 2px 10px;
      transition: transform 0.18s ease, background 0.18s ease;
    }
    a[mat-list-item]:hover { transform: translateX(3px); }
    .active-link {
      background: linear-gradient(90deg, rgba(56, 189, 248, 0.16), rgba(129, 140, 248, 0.08));
      box-shadow: inset 2px 0 0 var(--accent);
    }
    .active-link mat-icon { color: var(--accent); }

    .sidenav-footer {
      position: absolute; bottom: 12px; left: 0; right: 0;
      display: flex; align-items: center; justify-content: center; gap: 6px;
      font-size: 10.5px; color: #475569;
    }
    .dot-mini { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); opacity: 0.6; }

    .content { padding: 20px 24px; }
  `,
})
export class AppComponent {
  readonly theme = inject(ThemeService);
  readonly sections = NAV_SECTIONS;
  readonly istNow = signal(this.computeIst());
  readonly marketOpen = computed(() => {
    const now = this.istNow();
    const day = now.getDay();                            // shifted date: getters read IST wall time
    const minutes = now.getHours() * 60 + now.getMinutes();
    return day >= 1 && day <= 5 && minutes >= 555 && minutes <= 930;   // 09:15–15:30 IST
  });

  constructor() {
    const timer = setInterval(() => this.istNow.set(this.computeIst()), 1000);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }

  /** Wall-clock time in IST encoded as a local Date (safe for date pipe + getters). */
  private computeIst(): Date {
    const utcMs = Date.now() + new Date().getTimezoneOffset() * 60_000;
    return new Date(utcMs + 5.5 * 3_600_000);
  }
}
