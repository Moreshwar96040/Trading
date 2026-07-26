import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { MarketNewsResponse } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

/**
 * Market Pulse: the multi-source news tape (WSJ/FT/aggregated Indian coverage)
 * distilled by AI into one sentiment chip + the genuinely market-moving events.
 * The same cached digest feeds the Alpha Stack's macro layer — what you see
 * here is exactly what conviction scores are using.
 */
@Component({
  selector: 'app-market-pulse-card',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule, MatIconModule, MatTooltipModule],
  template: `
    @if (pulse(); as p) {
      <mat-card appearance="outlined" class="pulse-card">
        <div class="head" (click)="open.set(!open())">
          <mat-icon class="pulse-icon">newspaper</mat-icon>
          <h3>Market pulse</h3>
          @if (digest(); as d) {
            @if (d.sentiment) {
              <span class="tone" [class]="'tone ' + d.sentiment">{{ d.sentiment }}</span>
            }
            <span class="stance">{{ d.stance }}</span>
          } @else if (!p.llm_enabled) {
            <span class="stance dim">headlines live · set ANTHROPIC_API_KEY for the AI read</span>
          }
          <button mat-icon-button class="refresh" (click)="refresh($event)"
                  [disabled]="loading()" matTooltip="Re-fetch all feeds">
            <mat-icon>refresh</mat-icon>
          </button>
          <mat-icon class="chevron" [class.open]="open()">expand_more</mat-icon>
        </div>

        @if (open()) {
          @if (digest(); as d) {
            @if (d.key_events?.length) {
              <ul class="events">
                @for (e of d.key_events; track e) { <li>{{ e }}</li> }
              </ul>
            }
            @if (d.risk_flags?.length) {
              <p class="risks"><mat-icon>warning_amber</mat-icon>
                {{ d.risk_flags!.join(' · ') }}</p>
            }
          }
          <div class="headlines">
            @for (h of p.headlines.slice(0, 10); track h.title) {
              <a class="headline" [href]="h.link" target="_blank" rel="noopener">
                <span class="src">{{ h.source }}</span>
                <span class="ttl">{{ h.title }}</span>
              </a>
            }
          </div>
        }
      </mat-card>
    }
  `,
  styles: `
    .pulse-card { padding: 12px 18px; margin-bottom: 16px; }
    .head { display: flex; align-items: center; gap: 10px; cursor: pointer; flex-wrap: wrap; }
    .pulse-icon { color: var(--accent); }
    h3 { margin: 0; font-weight: 600; }
    .tone { font-size: 10px; font-weight: 800; letter-spacing: 0.07em; padding: 3px 10px;
            border-radius: 999px; text-transform: uppercase; }
    .tone.positive { background: rgba(38,166,154,0.16); color: var(--up); }
    .tone.neutral, .tone.mixed { background: rgba(255,183,77,0.15); color: #ffb74d; }
    .tone.negative { background: rgba(239,83,80,0.15); color: var(--down); }
    .stance { font-size: 12.5px; color: var(--text-dim); flex: 1; min-width: 200px;
              line-height: 1.4; }
    .stance.dim { opacity: 0.7; }
    .refresh { margin-left: auto; }
    .chevron { transition: transform 0.25s ease; }
    .chevron.open { transform: rotate(180deg); }

    .events { margin: 10px 0 4px; padding-left: 20px; font-size: 13px; }
    .events li { margin: 4px 0; line-height: 1.45; }
    .risks { display: flex; align-items: center; gap: 6px; font-size: 12.5px;
             color: #ffb74d; margin: 6px 0; }
    .risks mat-icon { font-size: 17px; width: 17px; height: 17px; }

    .headlines { display: flex; flex-direction: column; gap: 2px; margin-top: 8px; }
    .headline { display: flex; gap: 10px; align-items: baseline; padding: 6px 8px;
                border-radius: 8px; text-decoration: none; color: inherit; font-size: 12.5px; }
    .headline:hover { background: rgba(128,128,128,0.08); }
    .src { font-size: 10px; font-weight: 700; color: var(--accent-2); flex-shrink: 0;
           min-width: 88px; letter-spacing: 0.03em; }
    .ttl { line-height: 1.4; }
  `,
})
export class MarketPulseCardComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  readonly pulse = signal<MarketNewsResponse | null>(null);
  readonly loading = signal(false);
  readonly open = signal(false);

  ngOnInit(): void {
    this.load(false);
  }

  refresh(event: Event): void {
    event.stopPropagation();
    this.load(true);
  }

  private load(refresh: boolean): void {
    this.loading.set(true);
    this.api.getMarketNews(refresh).subscribe({
      next: (p) => { this.pulse.set(p); this.loading.set(false); },
      error: () => { this.pulse.set(null); this.loading.set(false); },
    });
  }

  digest() {
    const d = this.pulse()?.digest;
    return d && 'insight' in d ? d.insight ?? null : null;
  }
}
