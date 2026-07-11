import {
  AfterViewInit, Component, ElementRef, OnDestroy, ViewChild, effect, input,
} from '@angular/core';
import { IChartApi, ISeriesApi, LineData, Time, createChart } from 'lightweight-charts';

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
  }

  ngAfterViewInit(): void {
    const el = this.host.nativeElement;
    this.chart = createChart(el, {
      width: el.clientWidth,
      height: 280,
      layout: { background: { color: 'transparent' }, textColor: '#cfd8dc' },
      grid: {
        vertLines: { color: 'rgba(197, 203, 206, 0.08)' },
        horzLines: { color: 'rgba(197, 203, 206, 0.08)' },
      },
      rightPriceScale: { borderColor: 'rgba(197, 203, 206, 0.3)' },
      timeScale: { borderColor: 'rgba(197, 203, 206, 0.3)' },
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
