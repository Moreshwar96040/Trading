import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { MarketDataService } from './market-data.service';

describe('MarketDataService', () => {
  let service: MarketDataService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(MarketDataService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('searches symbols with a query param', () => {
    service.searchSymbols('rel').subscribe((result) => expect(result).toEqual([]));

    const req = http.expectOne('/api/v1/symbols?query=rel');
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });

  it('requests candles with date range', () => {
    service.getCandles('RELIANCE', '2026-01-01', '2026-06-30').subscribe();

    const req = http.expectOne('/api/v1/symbols/RELIANCE/candles?from=2026-01-01&to=2026-06-30');
    expect(req.request.method).toBe('GET');
    req.flush({ ticker: 'RELIANCE', from: '2026-01-01', to: '2026-06-30', candles: [] });
  });

  it('requests a quote', () => {
    service.getQuote('TCS').subscribe();

    const req = http.expectOne('/api/v1/quotes/TCS');
    expect(req.request.method).toBe('GET');
    req.flush({});
  });
});
