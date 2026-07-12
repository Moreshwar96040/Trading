import { Injectable, effect, signal } from '@angular/core';

export type ThemeMode = 'dark' | 'light';

/** Colors the lightweight-charts canvases need per theme (they can't read CSS vars). */
export interface ChartTheme {
  text: string;
  grid: string;
  border: string;
}

const CHART_THEMES: Record<ThemeMode, ChartTheme> = {
  dark: { text: '#cfd8dc', grid: 'rgba(197, 203, 206, 0.08)', border: 'rgba(197, 203, 206, 0.3)' },
  light: { text: '#475569', grid: 'rgba(15, 23, 42, 0.07)', border: 'rgba(15, 23, 42, 0.25)' },
};

const STORAGE_KEY = 'trading-ui-theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly mode = signal<ThemeMode>(
    localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark');

  constructor() {
    effect(() => {
      const mode = this.mode();
      document.documentElement.classList.toggle('light', mode === 'light');
      localStorage.setItem(STORAGE_KEY, mode);
    });
  }

  toggle(): void {
    this.mode.update((m) => (m === 'dark' ? 'light' : 'dark'));
  }

  chartTheme(): ChartTheme {
    return CHART_THEMES[this.mode()];
  }
}
