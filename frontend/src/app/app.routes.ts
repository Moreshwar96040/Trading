import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  {
    path: 'dashboard',
    loadComponent: () =>
      import('./features/dashboard/dashboard-page.component')
        .then((m) => m.DashboardPageComponent),
  },
  {
    path: 'chart',
    loadComponent: () =>
      import('./features/chart/chart-page.component').then((m) => m.ChartPageComponent),
  },
  {
    path: 'screener',
    loadComponent: () =>
      import('./features/screener/screener-page.component').then((m) => m.ScreenerPageComponent),
  },
  {
    path: 'fundamentals',
    loadComponent: () =>
      import('./features/fundamentals/fundamentals-page.component')
        .then((m) => m.FundamentalsPageComponent),
  },
  {
    path: 'strategies',
    loadComponent: () =>
      import('./features/strategies/strategies-page.component')
        .then((m) => m.StrategiesPageComponent),
  },
  {
    path: 'portfolio',
    loadComponent: () =>
      import('./features/portfolio/portfolio-page.component')
        .then((m) => m.PortfolioPageComponent),
  },
  {
    path: 'risk',
    loadComponent: () =>
      import('./features/risk/risk-page.component').then((m) => m.RiskPageComponent),
  },
  {
    path: 'alerts',
    loadComponent: () =>
      import('./features/alerts/alerts-page.component').then((m) => m.AlertsPageComponent),
  },
  {
    path: 'journal',
    loadComponent: () =>
      import('./features/journal/journal-page.component').then((m) => m.JournalPageComponent),
  },
  {
    path: 'ai',
    loadComponent: () =>
      import('./features/ai/ai-page.component').then((m) => m.AiPageComponent),
  },
  {
    path: 'alpha',
    loadComponent: () =>
      import('./features/alpha/alpha-stack-page.component')
        .then((m) => m.AlphaStackPageComponent),
  },
  {
    path: 'momentum',
    loadComponent: () =>
      import('./features/momentum/momentum-page.component')
        .then((m) => m.MomentumPageComponent),
  },
  { path: '**', redirectTo: 'dashboard' },
];
