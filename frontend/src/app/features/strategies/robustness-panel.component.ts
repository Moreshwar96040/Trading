import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, computed, input, signal } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { RobustnessReport } from '../../core/models/market-data.models';

/**
 * The overfitting guard, visualized:
 *  - animated score ring (0-100) with verdict
 *  - Monte Carlo histogram of 500 alternate histories (hover a bar for its range)
 *  - in-sample vs out-of-sample "duel" bars
 * Pure presentation; all numbers come from the backend robustness report.
 */
@Component({
  selector: 'app-robustness-panel',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatIconModule, MatTooltipModule],
  template: `
    @if (report(); as rep) {
      <mat-card appearance="outlined" class="lab">
        <div class="lab-grid">

          <!-- ============ score ring ============ -->
          <div class="ring-zone">
            <svg viewBox="0 0 120 120" class="ring">
              <circle cx="60" cy="60" r="52" class="ring-track" />
              <circle cx="60" cy="60" r="52" class="ring-fill"
                      [class]="'ring-fill ' + verdictClass()"
                      [style.stroke-dasharray]="circumference"
                      [style.stroke-dashoffset]="dashOffset()" />
              <text x="60" y="56" text-anchor="middle" class="ring-score">{{ shownScore() }}</text>
              <text x="60" y="74" text-anchor="middle" class="ring-sub">/ 100</text>
            </svg>
            <div class="verdict-chip" [class]="'verdict-chip ' + verdictClass()">
              {{ verdictLabel() }}
            </div>
            <div class="component-bars">
              @for (c of componentRows(); track c.label) {
                <div class="component-row" [matTooltip]="c.tip">
                  <span class="component-label">{{ c.label }}</span>
                  <div class="component-track">
                    <div class="component-fill" [style.width.%]="animate() ? c.pct : 0"></div>
                  </div>
                  <span class="component-value">{{ c.value }}/{{ c.max }}</span>
                </div>
              }
            </div>
          </div>

          <!-- ============ Monte Carlo ============ -->
          <div class="mc-zone">
            <h4><mat-icon>casino</mat-icon> {{ rep.monte_carlo?.resamples ?? 0 }} alternate histories</h4>
            <p class="mc-sub">Your backtest is one draw. Here's the distribution when the
              same trades land in a different order.</p>
            @if (rep.monte_carlo; as mc) {
              <div class="hist" (mouseleave)="hoverIdx.set(null)">
                @for (b of bars(); track b.i) {
                  <div class="hist-bar-slot" (mouseenter)="hoverIdx.set(b.i)"
                       [class.dim]="hoverIdx() !== null && hoverIdx() !== b.i">
                    <div class="hist-bar" [class.loss]="b.mid < 0"
                         [style.height.%]="animate() ? b.pct : 0"
                         [style.transition-delay.ms]="b.i * 18"></div>
                  </div>
                }
                <div class="hist-zero" [style.left.%]="zeroPos()"></div>
              </div>
              <div class="hist-readout">
                @if (hoveredBar(); as hb) {
                  <span>{{ hb.lo.toFixed(1) }}% … {{ hb.hi.toFixed(1) }}% →
                    <strong>{{ hb.count }}</strong> histories</span>
                } @else {
                  <span class="p-tags">
                    <span class="p-tag bad">p5 {{ mc.return_p5 }}%</span>
                    <span class="p-tag">median {{ mc.return_p50 }}%</span>
                    <span class="p-tag good">p95 {{ mc.return_p95 }}%</span>
                    <span class="p-tag" [class.bad]="mc.prob_loss_pct > 25">
                      {{ mc.prob_loss_pct }}% end in loss</span>
                  </span>
                }
              </div>
            } @else {
              <p class="mc-sub">No closed trades — nothing to resample.</p>
            }
          </div>

          <!-- ============ holdout duel ============ -->
          <div class="duel-zone">
            <h4><mat-icon>science</mat-icon> Unseen-data test</h4>
            <p class="mc-sub">First 70% of the window vs the 30% the strategy "hasn't seen".</p>
            @if (rep.holdout; as h) {
              <div class="duel">
                <div class="duel-row">
                  <span class="duel-label">In-sample</span>
                  <div class="duel-track">
                    <div class="duel-fill is" [style.width.%]="animate() ? duelPct(h.in_sample_return_pct) : 0"></div>
                  </div>
                  <span class="duel-value">{{ fmt(h.in_sample_return_pct) }}
                    <em>({{ h.in_sample_trades }} trades)</em></span>
                </div>
                <div class="duel-row">
                  <span class="duel-label">Out-of-sample</span>
                  <div class="duel-track">
                    <div class="duel-fill oos"
                         [class.fail]="(h.out_sample_return_pct ?? 0) < 0"
                         [style.width.%]="animate() ? duelPct(h.out_sample_return_pct) : 0"></div>
                  </div>
                  <span class="duel-value">{{ fmt(h.out_sample_return_pct) }}
                    <em>({{ h.out_sample_trades }} trades)</em></span>
                </div>
              </div>
            } @else {
              <p class="mc-sub">Window too short to split — widen the backtest dates.</p>
            }
            <ul class="reasons">
              @for (r of rep.reasons; track r) { <li>{{ r }}</li> }
            </ul>
          </div>
        </div>
      </mat-card>
    }
  `,
  styles: `
    .lab { padding: 18px 22px; margin-top: 14px; overflow: hidden; }
    .lab-grid { display: grid; grid-template-columns: 220px 1.2fr 1fr; gap: 28px; }
    @media (max-width: 1100px) { .lab-grid { grid-template-columns: 1fr; } }

    h4 { display: flex; align-items: center; gap: 6px; margin: 0 0 2px; font-weight: 600; }
    h4 mat-icon { font-size: 18px; width: 18px; height: 18px; color: var(--accent); }

    /* ---- ring ---- */
    .ring-zone { display: flex; flex-direction: column; align-items: center; gap: 10px; }
    .ring { width: 150px; height: 150px; transform: rotate(-90deg); }
    .ring-track { fill: none; stroke: var(--card-border); stroke-width: 9; }
    .ring-fill { fill: none; stroke-width: 9; stroke-linecap: round;
                 transition: stroke-dashoffset 1.1s cubic-bezier(0.22, 0.9, 0.3, 1); }
    .ring-fill.robust { stroke: var(--up); filter: drop-shadow(0 0 6px rgba(38,166,154,0.6)); }
    .ring-fill.promising { stroke: var(--accent); filter: drop-shadow(0 0 6px rgba(56,189,248,0.5)); }
    .ring-fill.fragile { stroke: #ffb74d; filter: drop-shadow(0 0 6px rgba(255,183,77,0.5)); }
    .ring-fill.overfit { stroke: var(--down); filter: drop-shadow(0 0 6px rgba(239,83,80,0.55)); }
    .ring-score { font-size: 30px; font-weight: 700; fill: var(--mat-sys-on-surface);
                  transform: rotate(90deg); transform-origin: 60px 60px; }
    .ring-sub { font-size: 10px; fill: var(--text-dim);
                transform: rotate(90deg); transform-origin: 60px 60px; }
    .verdict-chip { font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
                    padding: 4px 14px; border-radius: 999px; text-transform: uppercase; }
    .verdict-chip.robust { background: rgba(38,166,154,0.16); color: var(--up); }
    .verdict-chip.promising { background: rgba(56,189,248,0.16); color: var(--accent); }
    .verdict-chip.fragile { background: rgba(255,183,77,0.16); color: #ffb74d; }
    .verdict-chip.overfit { background: rgba(239,83,80,0.16); color: var(--down); }

    .component-bars { width: 100%; display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
    .component-row { display: grid; grid-template-columns: 74px 1fr 44px; gap: 8px;
                     align-items: center; font-size: 11px; }
    .component-label { color: var(--text-dim); }
    .component-track { height: 6px; border-radius: 4px; background: var(--card-border); overflow: hidden; }
    .component-fill { height: 100%; border-radius: 4px;
                      background: linear-gradient(90deg, var(--accent), var(--accent-2));
                      transition: width 0.9s cubic-bezier(0.22, 0.9, 0.3, 1) 0.3s; }
    .component-value { text-align: right; font-variant-numeric: tabular-nums; }

    /* ---- histogram ---- */
    .mc-sub { font-size: 12px; color: var(--text-dim); margin: 2px 0 10px; line-height: 1.45; }
    .hist { position: relative; display: flex; align-items: flex-end; gap: 2px;
            height: 110px; padding-bottom: 2px; border-bottom: 1px solid var(--card-border); }
    .hist-bar-slot { flex: 1; height: 100%; display: flex; align-items: flex-end;
                     cursor: crosshair; transition: opacity 0.15s ease; }
    .hist-bar-slot.dim { opacity: 0.35; }
    .hist-bar { width: 100%; border-radius: 3px 3px 0 0; min-height: 2px;
                background: linear-gradient(180deg, var(--accent), rgba(56,189,248,0.25));
                transition: height 0.7s cubic-bezier(0.22, 0.9, 0.3, 1); }
    .hist-bar.loss { background: linear-gradient(180deg, var(--down), rgba(239,83,80,0.2)); }
    .hist-zero { position: absolute; top: 0; bottom: 0; width: 0;
                 border-left: 1px dashed rgba(255,255,255,0.35); }
    .hist-readout { min-height: 24px; font-size: 12px; margin-top: 8px; color: var(--text-dim); }
    .p-tags { display: flex; gap: 8px; flex-wrap: wrap; }
    .p-tag { padding: 2px 10px; border-radius: 999px; background: var(--card-border);
             font-variant-numeric: tabular-nums; }
    .p-tag.good { color: var(--up); } .p-tag.bad { color: var(--down); }

    /* ---- duel ---- */
    .duel { display: flex; flex-direction: column; gap: 10px; margin: 6px 0 10px; }
    .duel-row { display: grid; grid-template-columns: 96px 1fr auto; gap: 10px;
                align-items: center; font-size: 12px; }
    .duel-label { color: var(--text-dim); }
    .duel-track { height: 14px; border-radius: 7px; background: var(--card-border); overflow: hidden; }
    .duel-fill { height: 100%; border-radius: 7px;
                 transition: width 1s cubic-bezier(0.22, 0.9, 0.3, 1) 0.2s; }
    .duel-fill.is { background: linear-gradient(90deg, var(--accent-2), var(--accent)); }
    .duel-fill.oos { background: linear-gradient(90deg, var(--up), #4dd0b0); }
    .duel-fill.oos.fail { background: linear-gradient(90deg, var(--down), #ff8a80); }
    .duel-value { font-variant-numeric: tabular-nums; white-space: nowrap; }
    .duel-value em { color: var(--text-dim); font-style: normal; font-size: 11px; }

    .reasons { margin: 8px 0 0; padding-left: 18px; font-size: 12px; color: var(--text-dim); }
    .reasons li { margin: 4px 0; line-height: 1.45; }
  `,
})
export class RobustnessPanelComponent implements AfterViewInit {
  readonly report = input.required<RobustnessReport | undefined>();

  readonly circumference = 2 * Math.PI * 52;
  readonly animate = signal(false);
  readonly hoverIdx = signal<number | null>(null);
  readonly shownScore = signal(0);

  ngAfterViewInit(): void {
    // kick animations one frame after paint so transitions actually run
    setTimeout(() => {
      this.animate.set(true);
      this.countUp();
    }, 60);
  }

  private countUp(): void {
    const target = this.report()?.score ?? 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 1000);
      this.shownScore.set(Math.round(target * (1 - Math.pow(1 - t, 3))));
      if (t < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  readonly dashOffset = computed(() => {
    const score = this.animate() ? (this.report()?.score ?? 0) : 0;
    return this.circumference * (1 - score / 100);
  });

  verdictClass(): string {
    switch (this.report()?.verdict) {
      case 'ROBUST': return 'robust';
      case 'PROMISING': return 'promising';
      case 'FRAGILE': return 'fragile';
      default: return 'overfit';
    }
  }

  verdictLabel(): string {
    return (this.report()?.verdict ?? '').replace('_', ' ');
  }

  readonly componentRows = computed(() => {
    const c = this.report()?.components;
    if (!c) return [];
    return [
      { label: 'Sample size', value: c.sample_size, max: 35, pct: (c.sample_size / 35) * 100,
        tip: 'More closed trades = more trustworthy statistics (30+ is workable)' },
      { label: 'Monte Carlo', value: c.monte_carlo, max: 35, pct: (c.monte_carlo / 35) * 100,
        tip: 'How well the unlucky tail (worst 5% of reshuffles) holds up' },
      { label: 'Unseen data', value: c.holdout, max: 30, pct: (c.holdout / 30) * 100,
        tip: 'Did the edge survive on the 30% of history it was not tuned on?' },
    ];
  });

  readonly bars = computed(() => {
    const h = this.report()?.monte_carlo?.histogram;
    if (!h || !h.counts.length) return [];
    const maxC = Math.max(...h.counts);
    const width = (h.max - h.min) / h.counts.length;
    return h.counts.map((count, i) => ({
      i, count,
      lo: h.min + i * width,
      hi: h.min + (i + 1) * width,
      mid: h.min + (i + 0.5) * width,
      pct: maxC > 0 ? (count / maxC) * 100 : 0,
    }));
  });

  readonly hoveredBar = computed(() => {
    const idx = this.hoverIdx();
    return idx === null ? null : this.bars()[idx] ?? null;
  });

  zeroPos(): number {
    const h = this.report()?.monte_carlo?.histogram;
    if (!h || h.max <= h.min) return 0;
    return Math.max(0, Math.min(100, (0 - h.min) / (h.max - h.min) * 100));
  }

  duelPct(v: number | null): number {
    const h = this.report()?.holdout;
    if (v === null || !h) return 0;
    const maxAbs = Math.max(Math.abs(h.in_sample_return_pct ?? 0),
                            Math.abs(h.out_sample_return_pct ?? 0), 1);
    return Math.abs(v) / maxAbs * 100;
  }

  fmt(v: number | null): string {
    return v === null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`;
  }
}
