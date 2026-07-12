import { CommonModule } from '@angular/common';
import { Component, ElementRef, EventEmitter, OnInit, Output, ViewChild,
         computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Router } from '@angular/router';

import { SymbolInfo } from './core/models/market-data.models';
import { MarketDataService } from './core/services/market-data.service';

interface PageResult { kind: 'page'; icon: string; title: string; hint: string; path: string; }
interface SymbolResult { kind: 'symbol'; ticker: string; name: string; sector: string | null; }
type Result = PageResult | SymbolResult;

const PAGES: PageResult[] = [
  { kind: 'page', icon: 'radar', title: 'Trade Desk', hint: 'regime · signals · account', path: '/dashboard' },
  { kind: 'page', icon: 'filter_alt', title: 'Screener', hint: 'scan the market', path: '/screener' },
  { kind: 'page', icon: 'auto_awesome', title: 'AI Ideas', hint: 'ranked confluence trades', path: '/ai' },
  { kind: 'page', icon: 'candlestick_chart', title: 'Charts', hint: 'price + indicators', path: '/chart' },
  { kind: 'page', icon: 'account_balance', title: 'Fundamentals', hint: 'ratios · statements · news', path: '/fundamentals' },
  { kind: 'page', icon: 'science', title: 'Strategy Lab', hint: 'backtest + robustness', path: '/strategies' },
  { kind: 'page', icon: 'layers', title: 'Alpha Stack', hint: 'conviction-ranked setups', path: '/alpha' },
  { kind: 'page', icon: 'account_balance_wallet', title: 'Portfolio', hint: 'paper positions', path: '/portfolio' },
  { kind: 'page', icon: 'shield', title: 'Risk', hint: 'limits + sizing', path: '/risk' },
  { kind: 'page', icon: 'notifications', title: 'Alerts', hint: 'price + indicator alerts', path: '/alerts' },
  { kind: 'page', icon: 'menu_book', title: 'Journal & Leaks', hint: 'entries + edge report', path: '/journal' },
];

/**
 * Ctrl+K command palette: jump to any page or any stock without touching the
 * mouse. Type a page name, or a ticker to open its chart (Tab for fundamentals).
 */
@Component({
  selector: 'app-command-palette',
  standalone: true,
  imports: [CommonModule, FormsModule, MatIconModule],
  template: `
    <div class="scrim" (click)="close.emit()">
      <div class="palette" (click)="$event.stopPropagation()">
        <div class="input-row">
          <mat-icon>search</mat-icon>
          <input #box type="text" [(ngModel)]="query" (ngModelChange)="onQuery($event)"
                 (keydown)="onKey($event)"
                 placeholder="Jump to page… or type a ticker (TCS, RELIANCE…)"
                 autocomplete="off" spellcheck="false" />
          <span class="esc-hint">esc</span>
        </div>

        <div class="results">
          @for (r of results(); track trackId(r); let i = $index) {
            <div class="result" [class.active]="i === activeIdx()"
                 (mouseenter)="activeIdx.set(i)" (click)="choose(r)">
              @if (r.kind === 'page') {
                <mat-icon>{{ r.icon }}</mat-icon>
                <span class="r-title">{{ r.title }}</span>
                <span class="r-hint">{{ r.hint }}</span>
                <span class="r-action">↵ open</span>
              } @else {
                <span class="tick-badge">{{ r.ticker.slice(0, 2) }}</span>
                <span class="r-title">{{ r.ticker }}</span>
                <span class="r-hint">{{ r.name }}@if (r.sector) { · {{ r.sector }} }</span>
                <span class="r-action">↵ chart · tab fundamentals</span>
              }
            </div>
          } @empty {
            <div class="no-results">
              @if (query.length) { Nothing matches “{{ query }}” }
              @else { Type to search pages and symbols }
            </div>
          }
        </div>

        <div class="footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>↵</kbd> open</span>
          <span><kbd>esc</kbd> close</span>
        </div>
      </div>
    </div>
  `,
  styles: `
    .scrim {
      position: fixed; inset: 0; z-index: 1000;
      background: rgba(2, 6, 16, 0.55);
      backdrop-filter: blur(6px);
      display: flex; justify-content: center; align-items: flex-start;
      padding-top: 14vh;
      animation: scrimIn 0.18s ease;
    }
    @keyframes scrimIn { from { opacity: 0; } to { opacity: 1; } }

    .palette {
      width: min(620px, 92vw);
      border-radius: 18px;
      border: 1px solid var(--card-glow);
      background: var(--glass-bg);
      backdrop-filter: blur(24px);
      box-shadow: 0 24px 80px -20px rgba(2, 6, 16, 0.9), 0 0 0 1px rgba(56,189,248,0.08);
      overflow: hidden;
      animation: palettePop 0.22s cubic-bezier(0.22, 0.9, 0.3, 1);
    }
    @keyframes palettePop {
      from { opacity: 0; transform: translateY(-14px) scale(0.98); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }

    .input-row {
      display: flex; align-items: center; gap: 12px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--card-border);
    }
    .input-row mat-icon { color: var(--accent); }
    input {
      flex: 1; background: none; border: none; outline: none;
      color: var(--mat-sys-on-surface);
      font: 500 16px Inter, sans-serif;
      letter-spacing: -0.01em;
    }
    input::placeholder { color: var(--text-dim); opacity: 0.7; }
    .esc-hint {
      font-size: 10px; font-weight: 700; color: var(--text-dim);
      border: 1px solid var(--card-border); border-radius: 6px; padding: 2px 7px;
    }

    .results { max-height: 46vh; overflow-y: auto; padding: 8px; }
    .result {
      display: flex; align-items: center; gap: 12px;
      padding: 10px 12px; border-radius: 12px; cursor: pointer;
      transition: background 0.12s ease;
    }
    .result mat-icon { color: var(--text-dim); font-size: 20px; width: 20px; height: 20px; }
    .result.active { background: linear-gradient(90deg, rgba(56,189,248,0.14), rgba(129,140,248,0.07)); }
    .result.active mat-icon { color: var(--accent); }
    .tick-badge {
      width: 30px; height: 30px; border-radius: 9px; flex-shrink: 0;
      display: grid; place-items: center;
      font: 700 11px 'Space Grotesk', sans-serif;
      color: var(--accent);
      background: rgba(56, 189, 248, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.25);
    }
    .r-title { font-weight: 600; font-size: 14px; white-space: nowrap; }
    .r-hint { font-size: 12px; color: var(--text-dim); overflow: hidden;
              text-overflow: ellipsis; white-space: nowrap; flex: 1; }
    .r-action { font-size: 10.5px; color: var(--text-dim); opacity: 0;
                transition: opacity 0.15s ease; white-space: nowrap; }
    .result.active .r-action { opacity: 0.9; }
    .no-results { padding: 26px; text-align: center; color: var(--text-dim); font-size: 13px; }

    .footer {
      display: flex; gap: 18px; padding: 10px 18px;
      border-top: 1px solid var(--card-border);
      font-size: 11px; color: var(--text-dim);
    }
    kbd {
      font: 600 10px Inter, sans-serif;
      border: 1px solid var(--card-border); border-radius: 5px;
      padding: 1px 5px; margin-right: 3px;
      background: rgba(255, 255, 255, 0.04);
    }
  `,
})
export class CommandPaletteComponent implements OnInit {
  @Output() close = new EventEmitter<void>();
  @ViewChild('box', { static: true }) box!: ElementRef<HTMLInputElement>;

  private readonly api = inject(MarketDataService);
  private readonly router = inject(Router);

  query = '';
  readonly activeIdx = signal(0);
  readonly symbols = signal<SymbolResult[]>([]);
  private searchTimer: ReturnType<typeof setTimeout> | null = null;

  readonly results = computed<Result[]>(() => {
    const q = this.querySig().trim().toLowerCase();
    const pages = q
      ? PAGES.filter((p) => p.title.toLowerCase().includes(q) || p.hint.includes(q))
      : PAGES;
    return [...pages, ...this.symbols()].slice(0, 12);
  });
  private readonly querySig = signal('');

  ngOnInit(): void {
    setTimeout(() => this.box.nativeElement.focus(), 30);
  }

  onQuery(q: string): void {
    this.querySig.set(q);
    this.activeIdx.set(0);
    if (this.searchTimer) clearTimeout(this.searchTimer);
    const term = q.trim();
    if (term.length < 1) { this.symbols.set([]); return; }
    this.searchTimer = setTimeout(() => {
      this.api.searchSymbols(term).subscribe({
        next: (list: SymbolInfo[]) => this.symbols.set(
          list.slice(0, 6).map((s) => ({ kind: 'symbol' as const, ticker: s.ticker,
                                         name: s.name, sector: s.sector }))),
        error: () => this.symbols.set([]),
      });
    }, 180);
  }

  onKey(e: KeyboardEvent): void {
    const n = this.results().length;
    if (e.key === 'ArrowDown') { e.preventDefault(); this.activeIdx.set((this.activeIdx() + 1) % Math.max(n, 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); this.activeIdx.set((this.activeIdx() - 1 + n) % Math.max(n, 1)); }
    else if (e.key === 'Enter') { e.preventDefault(); const r = this.results()[this.activeIdx()]; if (r) this.choose(r); }
    else if (e.key === 'Tab') {
      e.preventDefault();
      const r = this.results()[this.activeIdx()];
      if (r?.kind === 'symbol') this.go('/fundamentals', r.ticker);
    }
    else if (e.key === 'Escape') { this.close.emit(); }
  }

  choose(r: Result): void {
    if (r.kind === 'page') { this.router.navigateByUrl(r.path); this.close.emit(); }
    else this.go('/chart', r.ticker);
  }

  private go(path: string, ticker: string): void {
    this.router.navigate([path], { queryParams: { ticker } });
    this.close.emit();
  }

  trackId(r: Result): string {
    return r.kind === 'page' ? r.path : r.ticker;
  }
}
