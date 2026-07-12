import {
  AfterViewInit, Component, ElementRef, OnDestroy, ViewChild, effect, inject, input,
} from '@angular/core';
import {
  CandlestickData, HistogramData, IChartApi, ISeriesApi, LineData, Time, createChart,
} from 'lightweight-charts';

import { Candle } from '../../core/models/market-data.models';
import { ThemeService } from '../../core/services/theme.service';

export interface OverlayLine {
  id: string;          // stable key, e.g. 'sma_50'
  color: string;
  data: LineData[];
}

/**
 * Thin wrapper around TradingView lightweight-charts: candlesticks + volume.
 * Pure presentation — receives candles, renders them, nothing else.
 */
@Component({
  selector: 'app-candlestick-chart',
  standalone: true,
  template: `<div #chartHost class="chart-host"></div>`,
  styles: `
    :host { display: block; width: 100%; }
    .chart-host { width: 100%; height: 480px; }
  `,
})
export class CandlestickChartComponent implements AfterViewInit, OnDestroy {
  candles = input.required<Candle[]>();
  overlays = input<OverlayLine[]>([]);

  @ViewChild('chartHost', { static: true })
  private chartHost!: ElementRef<HTMLDivElement>;

  private readonly theme = inject(ThemeService);
  private chart?: IChartApi;
  private candleSeries?: ISeriesApi<'Candlestick'>;
  private volumeSeries?: ISeriesApi<'Histogram'>;
  private overlaySeries = new Map<string, ISeriesApi<'Line'>>();
  private resizeObserver?: ResizeObserver;

  constructor() {
    // Signal inputs don't fire ngOnChanges — react to new data via effects.
    effect(() => {
      const data = this.candles();
      this.render(data);
    });
    effect(() => {
      const lines = this.overlays();
      this.renderOverlays(lines);
    });
    effect(() => {
      this.theme.mode();                       // re-skin when the theme flips
      this.chart?.applyOptions(this.themedOptions());
    });
  }

  private themedOptions() {
    const t = this.theme.chartTheme();
    return {
      layout: { background: { color: 'transparent' }, textColor: t.text },
      grid: { vertLines: { color: t.grid }, horzLines: { color: t.grid } },
      timeScale: { borderColor: t.border },
      rightPriceScale: { borderColor: t.border },
    };
  }

  ngAfterViewInit(): void {
    const host = this.chartHost.nativeElement;
    this.chart = createChart(host, {
      width: host.clientWidth,
      height: 480,
      ...this.themedOptions(),
    });

    this.candleSeries = this.chart.addCandlestickSeries({
      upColor: '#26a69a', downColor: '#ef5350',
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
      borderVisible: false,
    });

    this.volumeSeries = this.chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    this.chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    this.resizeObserver = new ResizeObserver(() =>
      this.chart?.applyOptions({ width: host.clientWidth }));
    this.resizeObserver.observe(host);

    this.render(this.candles());
    this.renderOverlays(this.overlays());
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    this.chart?.remove();
  }

  private renderOverlays(lines: OverlayLine[]): void {
    if (!this.chart) return;
    const wanted = new Set(lines.map((l) => l.id));

    for (const [id, series] of this.overlaySeries) {
      if (!wanted.has(id)) {
        this.chart.removeSeries(series);
        this.overlaySeries.delete(id);
      }
    }
    for (const line of lines) {
      let series = this.overlaySeries.get(line.id);
      if (!series) {
        series = this.chart.addLineSeries({
          color: line.color, lineWidth: 1,
          priceLineVisible: false, lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        this.overlaySeries.set(line.id, series);
      }
      series.setData(line.data);
    }
  }

  private render(data: Candle[]): void {
    if (!this.candleSeries || !this.volumeSeries) return;

    this.candleSeries.setData(data.map((c): CandlestickData => ({
      time: c.time as Time,
      open: c.open, high: c.high, low: c.low, close: c.close,
    })));

    this.volumeSeries.setData(data.map((c): HistogramData => ({
      time: c.time as Time,
      value: c.volume,
      color: c.close >= c.open ? 'rgba(38, 166, 154, 0.4)' : 'rgba(239, 83, 80, 0.4)',
    })));

    this.chart?.timeScale().fitContent();
  }
}
