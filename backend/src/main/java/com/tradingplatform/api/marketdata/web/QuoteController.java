package com.tradingplatform.api.marketdata.web;

import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import com.tradingplatform.api.integration.marketdata.QuoteDto;
import com.tradingplatform.api.marketdata.service.SymbolService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/quotes")
public class QuoteController {

    private final MarketDataServiceClient marketData;
    private final SymbolService symbolService;

    public QuoteController(MarketDataServiceClient marketData, SymbolService symbolService) {
        this.marketData = marketData;
        this.symbolService = symbolService;
    }

    /** Delayed quote. Validates the ticker locally before hitting the Python service. */
    @GetMapping("/{ticker}")
    public QuoteDto getQuote(@PathVariable String ticker) {
        String canonical = symbolService.getByTicker(ticker).getTicker();
        return marketData.getQuote(canonical);
    }
}
