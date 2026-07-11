import {
  AfterViewInit, Component, ElementRef, OnDestroy, ViewChild, effect, input,
} from '@angular/core';
import {
  IChartApi, ISeriesApi, LineData, Time, createChart,
} from 'lightweight-charts';

/** Small RSI pane with 30/70 guide lines, time-synced visually below the main chart. */
@Component({
  selector: 'app-rsi-chart',
  standalone: true,
  template: `<div #host class="rsi-host"></div>`,
  styles: `
    :host { display: block; width: 100%; }
    .rsi-host { width: 100%; height: 140px; }
  `,
})
export class RsiChartComponent implements AfterViewInit, OnDestroy {
  points = input.required<LineData[]>();

  @ViewChild('host', { static: true })
  private host!: ElementRef<HTMLDivElement>;

  private chart?: IChartApi;
  private series?: ISeriesApi<'Line'>;
  private resizeObserver?: ResizeObserver;

  constructor() {
    effect(() => {
      const data = this.points();
      if (this.series) {
        this.series.setData(data);
        this.chart?.timeScale().fitContent();
      }
    });
  }

  ngAfterViewInit(): void {
    const el = this.host.nativeElement;
    this.chart = createChart(el, {
      width: el.clientWidth,
      height: 140,
      layout: { background: { color: 'transparent' }, textColor: '#cfd8dc' },
      grid: {
        vertLines: { color: 'rgba(197, 203, 206, 0.08)' },
        horzLines: { color: 'rgba(197, 203, 206, 0.08)' },
      },
      rightPriceScale: { borderColor: 'rgba(197, 203, 206, 0.3)' },
      timeScale: { borderColor: 'rgba(197, 203, 206, 0.3)' },
    });
    this.series = this.chart.addLineSeries({
      color: '#ab47bc', lineWidth: 2, priceLineVisible: false, lastValueVisible: true,
    });
    this.series.createPriceLine({ price: 70, color: '#ef5350', lineStyle: 2, lineWidth: 1, title: '70' } as never);
    this.series.createPriceLine({ price: 30, color: '#26a69a', lineStyle: 2, lineWidth: 1, title: '30' } as never);

    this.resizeObserver = new ResizeObserver(() =>
      this.chart?.applyOptions({ width: el.clientWidth }));
    this.resizeObserver.observe(el);

    this.series.setData(this.points());
    this.chart.timeScale().fitContent();
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    this.chart?.remove();
  }
}
