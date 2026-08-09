import { CommonModule } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { NavigationCancel, NavigationEnd, NavigationError, NavigationStart, Router,
         RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { CommandPaletteComponent } from './command-palette.component';
import { AiUsageSummary } from './core/models/market-data.models';
import { MarketDataService } from './core/services/market-data.service';
import { ThemeService } from './core/services/theme.service';

interface NavItem { path: string; icon: string; title: string; }
interface NavSection { label: string; items: NavItem[]; }

// The nav follows the trading cycle, so the structure itself teaches the workflow:
// see the tape -> find candidates -> prove the edge -> execute with rules -> learn.
const NAV_SECTIONS: NavSection[] = [
  {
    label: '1 · Radar',
    items: [
      { path: '/dashboard', icon: 'radar', title: 'Trade Desk' },
    ],
  },
  {
    label: '2 · Discover',
    items: [
      { path: '/screener', icon: 'filter_alt', title: 'Screener' },
      { path: '/momentum', icon: 'speed', title: 'Momentum' },
      { path: '/chart', icon: 'candlestick_chart', title: 'Charts' },
      { path: '/fundamentals', icon: 'account_balance', title: 'Fundamentals' },
    ],
  },
  {
    label: '3 · Validate',
    items: [
      { path: '/strategies', icon: 'science', title: 'Strategy Lab' },
      { path: '/alpha', icon: 'layers', title: 'Alpha Stack' },
      { path: '/ai', icon: 'psychology', title: 'AI & ML' },
    ],
  },
  {
    label: '4 · Execute',
    items: [
      { path: '/portfolio', icon: 'account_balance_wallet', title: 'Portfolio' },
      { path: '/risk', icon: 'shield', title: 'Risk' },
      { path: '/alerts', icon: 'notifications', title: 'Alerts' },
    ],
  },
  {
    label: '5 · Review',
    items: [
      { path: '/journal', icon: 'menu_book', title: 'Journal & Leaks' },
    ],
  },
];

/** Application shell: glass toolbar + grouped navigation. New features add a nav entry here. */
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive, MatToolbarModule,
            MatSidenavModule, MatListModule, MatIconModule, MatButtonModule,
            MatTooltipModule, CommandPaletteComponent],
  template: `
    <!-- route-change progress beam -->
    <div class="route-beam" [class.loading]="routeLoading()"></div>

    <mat-toolbar class="toolbar">
      <div class="brand-mark"><mat-icon>candlestick_chart</mat-icon></div>
      <span class="title">Trading Platform</span>
      <span class="badge">NSE</span>
      <span class="spacer"></span>
      <button class="cmdk" (click)="paletteOpen.set(true)"
              matTooltip="Jump anywhere — pages or tickers">
        <mat-icon>search</mat-icon> Search
        <span class="cmdk-keys"><kbd>Ctrl</kbd><kbd>K</kbd></span>
      </button>
      <div class="market-status" [class.open]="marketOpen()">
        <span class="dot"></span>
        {{ marketOpen() ? 'Market open' : 'Market closed' }}
      </div>
      @if (aiUsage(); as u) {
        <div class="ai-spend" [matTooltip]="aiSpendTooltip()">
          <mat-icon>auto_awesome</mat-icon>
          ₹{{ u.month.cost_inr | number: '1.2-2' }}
          <span class="ai-spend-label">AI this month</span>
        </div>
      }
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

    @if (paletteOpen()) {
      <app-command-palette (close)="paletteOpen.set(false)" />
    }
  `,
  styles: `
    :host { display: flex; flex-direction: column; height: 100%; }

    .route-beam {
      position: fixed; top: 0; left: 0; right: 100%; height: 2.5px; z-index: 1100;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      box-shadow: 0 0 12px rgba(56, 189, 248, 0.7);
      opacity: 0; transition: opacity 0.3s ease 0.2s;
    }
    .route-beam.loading {
      opacity: 1; transition: none;
      animation: beam 1s cubic-bezier(0.3, 0.8, 0.4, 1) infinite;
    }
    @keyframes beam {
      0% { left: 0; right: 100%; }
      50% { left: 20%; right: 20%; }
      100% { left: 100%; right: 0; }
    }

    .cmdk {
      display: flex; align-items: center; gap: 8px;
      font: 500 12.5px Inter, sans-serif; color: var(--text-dim);
      padding: 6px 8px 6px 12px; border-radius: 10px; cursor: pointer;
      border: 1px solid var(--card-border); background: var(--glass-bg);
      transition: border-color 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
    }
    .cmdk:hover {
      border-color: var(--card-glow); color: var(--mat-sys-on-surface);
      box-shadow: 0 0 14px -4px rgba(56, 189, 248, 0.5);
    }
    .cmdk mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .cmdk-keys kbd {
      font: 600 10px Inter, sans-serif; color: var(--text-dim);
      border: 1px solid var(--card-border); border-radius: 5px;
      padding: 1px 5px; margin-left: 3px; background: rgba(255, 255, 255, 0.04);
    }

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

    .ai-spend {
      display: flex; align-items: center; gap: 6px;
      font-size: 12px; font-weight: 700; color: var(--accent-2);
      padding: 5px 12px; border-radius: 999px; cursor: default;
      border: 1px solid rgba(129, 140, 248, 0.35); background: rgba(129, 140, 248, 0.08);
      font-variant-numeric: tabular-nums;
    }
    .ai-spend mat-icon { font-size: 15px; width: 15px; height: 15px; }
    .ai-spend-label { font-weight: 500; color: var(--text-dim); font-size: 11px; }

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
  private readonly api = inject(MarketDataService);
  private readonly router = inject(Router);
  readonly sections = NAV_SECTIONS;
  readonly istNow = signal(this.computeIst());
  readonly aiUsage = signal<AiUsageSummary | null>(null);
  readonly paletteOpen = signal(false);
  readonly routeLoading = signal(false);
  readonly marketOpen = computed(() => {
    const now = this.istNow();
    const day = now.getDay();                            // shifted date: getters read IST wall time
    const minutes = now.getHours() * 60 + now.getMinutes();
    return day >= 1 && day <= 5 && minutes >= 555 && minutes <= 930;   // 09:15–15:30 IST
  });

  constructor() {
    const timer = setInterval(() => this.istNow.set(this.computeIst()), 1000);
    const loadUsage = () => this.api.getAiUsage().subscribe({
      next: (u) => this.aiUsage.set(u),
      error: () => this.aiUsage.set(null),   // endpoint down — vanish quietly
    });
    loadUsage();
    const usageTimer = setInterval(loadUsage, 120_000);   // refresh every 2 min

    // ---- Ctrl/Cmd+K opens the command palette anywhere ----
    const onKeydown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        this.paletteOpen.update((open) => !open);
      }
    };
    document.addEventListener('keydown', onKeydown);

    // ---- cursor spotlight: paint --mx/--my on whichever card the pointer is over ----
    const onPointerMove = (e: PointerEvent) => {
      const card = (e.target as HTMLElement)?.closest?.('.mat-mdc-card') as HTMLElement | null;
      if (card) {
        const rect = card.getBoundingClientRect();
        card.style.setProperty('--mx', `${e.clientX - rect.left}px`);
        card.style.setProperty('--my', `${e.clientY - rect.top}px`);
      }
    };
    document.addEventListener('pointermove', onPointerMove, { passive: true });

    // ---- route-change beam ----
    const routerSub = this.router.events.subscribe((ev) => {
      if (ev instanceof NavigationStart) this.routeLoading.set(true);
      else if (ev instanceof NavigationEnd || ev instanceof NavigationCancel
               || ev instanceof NavigationError) this.routeLoading.set(false);
    });

    inject(DestroyRef).onDestroy(() => {
      clearInterval(timer);
      clearInterval(usageTimer);
      document.removeEventListener('keydown', onKeydown);
      document.removeEventListener('pointermove', onPointerMove);
      routerSub.unsubscribe();
    });
  }

  aiSpendTooltip(): string {
    const u = this.aiUsage();
    if (!u) return '';
    if (u.total.calls === 0) {
      return 'No AI calls recorded yet — insights are cached, so you only pay when data changes';
    }
    const kinds = u.by_kind.map((k) => `${k.kind.toLowerCase()}: ₹${k.cost_inr}`).join(' · ');
    return `${u.month.calls} AI calls this month `
      + `(${((u.month.input_tokens + u.month.output_tokens) / 1000).toFixed(1)}K tokens)`
      + (kinds ? ` — ${kinds}` : '')
      + ` · all-time ₹${u.total.cost_inr} ($${u.total.cost_usd})`;
  }

  /** Wall-clock time in IST encoded as a local Date (safe for date pipe + getters). */
  private computeIst(): Date {
    const utcMs = Date.now() + new Date().getTimezoneOffset() * 60_000;
    return new Date(utcMs + 5.5 * 3_600_000);
  }
}
