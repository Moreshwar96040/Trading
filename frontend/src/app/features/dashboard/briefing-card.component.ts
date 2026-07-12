import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';

import { MorningBriefing } from '../../core/models/market-data.models';
import { MarketDataService } from '../../core/services/market-data.service';

/**
 * The Morning Brief: Claude's pre-market read of YOUR book — positions plan,
 * regime, fresh signals, discipline note. Warmed by the scheduler before the
 * open; the regenerate button forces a fresh one.
 */
@Component({
  selector: 'app-briefing-card',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule, MatIconModule,
            MatProgressSpinnerModule, MatTooltipModule],
  template: `
    @if (visible()) {
      <mat-card appearance="outlined" class="brief">
        <div class="head">
          <div class="sun"><mat-icon>wb_twilight</mat-icon></div>
          <div>
            <h3>Morning brief</h3>
            <span class="sub">{{ briefing()?.date }} · your book, before the open</span>
          </div>
          <button mat-icon-button class="refresh" (click)="load(true)"
                  [disabled]="loading()" matTooltip="Regenerate">
            <mat-icon>autorenew</mat-icon>
          </button>
        </div>

        @if (loading()) {
          <div class="loading"><mat-spinner diameter="22" /> Writing today's brief…</div>
        } @else if (insight()) {
          @if (insight(); as n) {
          @if (n.headline) { <p class="headline">“{{ n.headline }}”</p> }
          @if (n.market_read) { <p class="market-read">{{ n.market_read }}</p> }
          @if (n.position_plans?.length) {
            <div class="plans">
              @for (p of n.position_plans; track p.ticker; let i = $index) {
                <div class="plan" [style.animation-delay.ms]="i * 90">
                  <span class="plan-ticker">{{ p.ticker }}</span>
                  <span class="plan-text">{{ p.plan }}</span>
                </div>
              }
            </div>
          }
          @if (n.opportunities?.length) {
            <div class="opps">
              <span class="opps-label"><mat-icon>bolt</mat-icon> Worth a look:</span>
              {{ n.opportunities!.join(' · ') }}
            </div>
          }
          @if (n.discipline_note) {
            <p class="discipline"><mat-icon>self_improvement</mat-icon> {{ n.discipline_note }}</p>
          }
          }
        } @else if (briefing()?.llm_enabled === false) {
          <p class="sub pad">Set ANTHROPIC_API_KEY to get an AI-written brief each morning —
            the Guardian below still works without it.</p>
        }
      </mat-card>
    }
  `,
  styles: `
    .brief {
      padding: 16px 20px; margin-bottom: 16px;
      background:
        linear-gradient(120deg, rgba(255, 183, 77, 0.05), transparent 40%),
        linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0)),
        var(--glass-bg) !important;
    }
    .head { display: flex; align-items: center; gap: 12px; }
    .sun {
      width: 42px; height: 42px; border-radius: 13px; display: grid; place-items: center;
      background: linear-gradient(135deg, rgba(255,183,77,0.25), rgba(239,108,0,0.12));
    }
    .sun mat-icon { color: #ffb74d; }
    h3 { margin: 0; font-weight: 600; }
    .sub { font-size: 12px; color: var(--text-dim); }
    .pad { margin: 12px 0 2px; }
    .refresh { margin-left: auto; }
    .loading { display: flex; align-items: center; gap: 12px; padding: 16px 2px 4px;
               color: var(--text-dim); font-size: 13px; }

    .headline { font-size: 16px; font-weight: 600; font-style: italic;
                margin: 14px 0 6px; letter-spacing: -0.01em; }
    .market-read { font-size: 13px; color: var(--text-dim); line-height: 1.55; margin: 0 0 10px; }

    .plans { display: flex; flex-direction: column; gap: 6px; }
    .plan {
      display: flex; gap: 12px; align-items: baseline;
      padding: 8px 12px; border-radius: 10px; font-size: 13px; line-height: 1.45;
      background: rgba(56, 189, 248, 0.045); border: 1px solid var(--card-border);
      animation: planIn 0.4s cubic-bezier(0.22, 0.9, 0.3, 1) both;
    }
    @keyframes planIn { from { opacity: 0; transform: translateY(6px); }
                        to { opacity: 1; transform: translateY(0); } }
    .plan-ticker { font: 700 12px 'Space Grotesk', sans-serif; color: var(--accent);
                   flex-shrink: 0; min-width: 74px; }
    .plan-text { flex: 1; }

    .opps { font-size: 13px; margin: 10px 0 0; color: var(--mat-sys-on-surface); }
    .opps-label { display: inline-flex; align-items: center; gap: 4px; font-weight: 600;
                  color: var(--accent-2); }
    .opps-label mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .discipline { display: flex; gap: 8px; align-items: center; font-size: 12.5px;
                  color: var(--text-dim); margin: 10px 0 0; font-style: italic; }
    .discipline mat-icon { font-size: 17px; width: 17px; height: 17px; color: #ffb74d; }
  `,
})
export class BriefingCardComponent implements OnInit {
  private readonly api = inject(MarketDataService);
  readonly briefing = signal<MorningBriefing | null>(null);
  readonly loading = signal(false);

  ngOnInit(): void {
    this.load(false);
  }

  load(force: boolean): void {
    this.loading.set(true);
    this.api.getBriefing(force).subscribe({
      next: (b) => { this.briefing.set(b); this.loading.set(false); },
      error: () => { this.briefing.set(null); this.loading.set(false); },
    });
  }

  visible(): boolean {
    const b = this.briefing();
    return this.loading() || !!b;
  }

  insight() {
    return this.briefing()?.narrative?.insight ?? null;
  }
}
