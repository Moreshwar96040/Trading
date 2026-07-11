package com.tradingplatform.api.marketdata.web;

import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import com.tradingplatform.api.marketdata.service.SymbolService;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Indicator series for chart overlays — computed on demand by the Python service. */
@RestController
@RequestMapping("/api/v1/indicators")
public class IndicatorController {

    private final MarketDataServiceClient marketData;
    private final SymbolService symbolService;

    public IndicatorController(MarketDataServiceClient marketData, SymbolService symbolService) {
        this.marketData = marketData;
        this.symbolService = symbolService;
    }

    /** GET /api/v1/indicators/RELIANCE?from=2025-07-01&to=2026-06-30 */
    @GetMapping("/{ticker}")
    public Map<String, Object> indicators(@PathVariable String ticker,
                                          @RequestParam(required = false) String from,
                                          @RequestParam(required = false) String to) {
        String canonical = symbolService.getByTicker(ticker).getTicker();
        return marketData.getIndicators(canonical, from, to);
    }
}
