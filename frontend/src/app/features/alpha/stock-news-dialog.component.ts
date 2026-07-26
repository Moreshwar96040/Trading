import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { NewsArticle, NewsInsight } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

export interface StockNewsDialogData {
  ticker: string;
  name?: string;
  /** The 0-10 news score already computed by the Alpha Stack, shown in the header. */
  score?: number | null;
}

/**
 * Click-through from the Alpha Stack's news score: fetches the stock's stored
 * headlines + cached AI digest on open, so the trader can see WHY the news
 * layer scored what it did without leaving the stack.
 */
@Component({
  selector: 'app-stock-news-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule, MatButtonModule, MatIconModule,
            MatProgressSpinnerModule],
  template: `
    <div class="news-dialog">
      <div class="head">
        <div class="title">
          <mat-icon>newspaper</mat-icon>
          <div>
            <h2>{{ data.ticker }} news</h2>
            @if (data.name) { <p class="sub">{{ data.name }}</p> }
          </div>
        </div>
        @if (data.score !== null && data.score !== undefined) {
          <div class="score" [class]="scoreClass(data.score)"
               title="News sentiment score out of 10">
            <span class="score-num">{{ data.score | number: '1.1-1' }}</span>
            <span class="score-den">/ 10</span>
          </div>
        }
      </div>

      @if (loading()) {
        <div class="loading"><mat-spinner diameter="28" /> Fetching latest news…</div>
      } @else {
        @if (insight(); as ni) {
          <div class="digest">
            <div class="digest-head">
              <mat-icon>auto_awesome</mat-icon>
              <span>AI digest</span>
              @if (ni.sentiment) {
                <span class="verdict" [class]="'verdict sentiment-' + ni.sentiment">{{ ni.sentiment }}</span>
              }
            </div>
            @if (ni.summary) { <p class="summary">{{ ni.summary }}</p> }
            @if (ni.key_points?.length) {
              <ul>@for (p of ni.key_points; track p) { <li>{{ p }}</li> }</ul>
            }
            @if (ni.catalysts?.length) {
              <div class="catalysts">
                @for (c of ni.catalysts; track c.type) {
                  <span class="catalyst" [class]="'catalyst catalyst-' + c.direction">
                    {{ c.type.replace('_', ' ') }}
                  </span>
                }
              </div>
            }
            @if (ni.watch_for?.length) {
              <p class="watch-for"><strong>Watch for:</strong> {{ ni.watch_for!.join(' · ') }}</p>
            }
          </div>
        } @else if (!llmEnabled()) {
          <p class="hint">Set ANTHROPIC_API_KEY in .env to get an AI news digest.</p>
        }

        @if (articles().length) {
          <div class="news-list">
            @for (a of articles(); track a.title) {
              <a class="news-item" [href]="a.link" target="_blank" rel="noopener">
                <span class="news-title">{{ a.title }}</span>
                <span class="news-meta">{{ a.publisher }} · {{ a.published_at | date: 'MMM d, y' }}</span>
              </a>
            }
          </div>
        } @else {
          <p class="hint">No stored news for {{ data.ticker }} yet.</p>
        }
      }

      <div class="actions">
        <a mat-stroked-button [href]="'/fundamentals?ticker=' + data.ticker">
          <mat-icon>insights</mat-icon> Full fundamentals
        </a>
        <button mat-flat-button color="primary" mat-dialog-close>Close</button>
      </div>
    </div>
  `,
  styles: `
    .news-dialog { min-width: 340px; max-width: 560px; }
    .head { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    .title { display: flex; align-items: center; gap: 12px; }
    .title h2 { margin: 0; font-weight: 600; }
    .title .sub { margin: 2px 0 0; font-size: 12px; color: var(--text-dim); }
    .score { display: flex; flex-direction: column; align-items: center; line-height: 1;
             padding: 8px 14px; border-radius: 12px; border: 1px solid var(--card-border); }
    .score-num { font: 700 22px 'Space Grotesk', sans-serif; }
    .score-den { font-size: 11px; color: var(--text-dim); margin-top: 2px; }
    .score.good { color: var(--up); border-color: rgba(38,166,154,0.4); }
    .score.mid { color: #ffb74d; border-color: rgba(255,183,77,0.4); }
    .score.bad { color: var(--down); border-color: rgba(239,83,80,0.4); }
    .loading { display: flex; align-items: center; gap: 12px; padding: 24px 0;
               color: var(--text-dim); }
    .digest { margin: 16px 0; padding: 14px 16px; border-radius: 10px;
              background: rgba(128,128,128,0.06); }
    .digest-head { display: flex; align-items: center; gap: 8px; font-weight: 500;
                   font-size: 13px; }
    .digest-head mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .verdict { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
               padding: 3px 10px; border-radius: 12px; font-weight: 600; }
    .sentiment-positive { background: #1b5e2033; color: #66bb6a; }
    .sentiment-mixed, .sentiment-neutral { background: #f57f1733; color: #ffb74d; }
    .sentiment-negative { background: #b71f1f33; color: #ef5350; }
    .summary { margin: 10px 0; line-height: 1.5; }
    .digest ul { margin: 6px 0; padding-left: 20px; }
    .digest li { margin: 3px 0; line-height: 1.4; }
    .catalysts { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 2px; }
    .catalyst { font-size: 11px; text-transform: capitalize; padding: 2px 8px;
                border-radius: 10px; background: #ffffff14; }
    .catalyst-positive { background: #1b5e2033; color: #66bb6a; }
    .catalyst-negative { background: #b71f1f33; color: #ef5350; }
    .catalyst-neutral { background: #f57f1733; color: #ffb74d; }
    .watch-for { font-size: 13px; opacity: 0.85; margin: 6px 0 0; }
    .news-list { display: flex; flex-direction: column; gap: 4px; margin-top: 8px;
                 max-height: 260px; overflow-y: auto; }
    .news-item { display: flex; flex-direction: column; padding: 10px 12px; border-radius: 8px;
                 text-decoration: none; color: inherit; }
    .news-item:hover { background: rgba(128,128,128,0.08); }
    .news-title { line-height: 1.4; }
    .news-meta { font-size: 12px; opacity: 0.55; margin-top: 2px; }
    .hint { opacity: 0.6; margin: 16px 0; }
    .actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
  `,
})
export class StockNewsDialogComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  readonly data = inject<StockNewsDialogData>(MAT_DIALOG_DATA);

  readonly loading = signal(true);
  readonly articles = signal<NewsArticle[]>([]);
  readonly insight = signal<NewsInsight | null>(null);
  readonly llmEnabled = signal(true);

  ngOnInit(): void {
    this.api.getNews(this.data.ticker, false).subscribe({
      next: (resp) => {
        this.loading.set(false);
        this.articles.set(resp.articles);
        this.llmEnabled.set(resp.llm_enabled);
        this.insight.set(this.unwrap<NewsInsight>(resp.insight));
      },
      error: () => this.loading.set(false),
    });
  }

  scoreClass(score: number): string {
    return score >= 6.5 ? 'good' : score >= 4 ? 'mid' : 'bad';
  }

  /** The API wraps cached insights as {insight, generated_at, cached}; errors as {error}. */
  private unwrap<T>(raw: unknown): T | null {
    if (!raw || typeof raw !== 'object') return null;
    const obj = raw as Record<string, unknown>;
    if ('error' in obj) return null;
    if ('insight' in obj && obj['insight']) return obj['insight'] as T;
    return obj as T;
  }
}
