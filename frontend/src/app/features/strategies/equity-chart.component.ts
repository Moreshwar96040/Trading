import {
  AfterViewInit, Component, ElementRef, OnDestroy, ViewChild, effect, inject, input,
} from '@angular/core';
import { IChartApi, ISeriesApi, LineData, Time, createChart } from 'lightweight-charts';

import { ThemeService } from '../../core/services/theme.service';

/** Portfolio equity curve (area-style line). */
@Component({
  selector: 'app-equity-chart',
  standalone: true,
  template: `<div #host class="host"></div>`,
  styles: `
    :host { display: block; width: 100%; }
    .host { width: 100%; height: 280px; }
  `,
})
export class EquityChartComponent implements AfterViewInit, OnDestroy {
  points = input.required<{ d: string; v: number }[]>();

  @ViewChild('host', { static: true })
  private host!: ElementRef<HTMLDivElement>;

  private readonly theme = inject(ThemeService);
  private chart?: IChartApi;
  private series?: ISeriesApi<'Area'>;
  private resizeObserver?: ResizeObserver;

  constructor() {
    effect(() => {
      const data = this.points();
      if (this.series) {
        this.series.setData(this.toLineData(data));
        this.chart?.timeScale().fitContent();
      }
    });
    effect(() => {
      this.theme.mode();
      this.chart?.applyOptions(this.themedOptions());
    });
  }

  private themedOptions() {
    const t = this.theme.chartTheme();
    return {
      layout: { background: { color: 'transparent' }, textColor: t.text },
      grid: { vertLines: { color: t.grid }, horzLines: { color: t.grid } },
      rightPriceScale: { borderColor: t.border },
      timeScale: { borderColor: t.border },
    };
  }

  ngAfterViewInit(): void {
    const el = this.host.nativeElement;
    this.chart = createChart(el, {
      width: el.clientWidth,
      height: 280,
      ...this.themedOptions(),
    });
    this.series = this.chart.addAreaSeries({
      lineColor: '#4fc3f7',
      topColor: 'rgba(79, 195, 247, 0.3)',
      bottomColor: 'rgba(79, 195, 247, 0.02)',
      lineWidth: 2,
    });
    this.resizeObserver = new ResizeObserver(() =>
      this.chart?.applyOptions({ width: el.clientWidth }));
    this.resizeObserver.observe(el);

    this.series.setData(this.toLineData(this.points()));
    this.chart.timeScale().fitContent();
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    this.chart?.remove();
  }

  private toLineData(points: { d: string; v: number }[]): LineData[] {
    return points.map((p) => ({ time: p.d as Time, value: p.v }));
  }
}
