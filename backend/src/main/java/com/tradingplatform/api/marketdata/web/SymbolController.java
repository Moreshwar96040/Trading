package com.tradingplatform.api.marketdata.web;

import com.tradingplatform.api.common.error.NotFoundException;
import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import com.tradingplatform.api.marketdata.service.SymbolService;
import com.tradingplatform.api.marketdata.web.dto.SymbolDto;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1/symbols")
public class SymbolController {

    private final SymbolService symbolService;
    private final MarketDataServiceClient mdClient;

    public SymbolController(SymbolService symbolService, MarketDataServiceClient mdClient) {
        this.symbolService = symbolService;
        this.mdClient = mdClient;
    }

    /** List/search active symbols. GET /api/v1/symbols?query=rel */
    @GetMapping
    public List<SymbolDto> search(@RequestParam(required = false) String query) {
        return symbolService.search(query).stream().map(SymbolDto::from).toList();
    }

    /**
     * Validate a ticker on Yahoo Finance, seed it into the symbols table, and
     * pull historical OHLCV data — all via the Python service.
     * Returns immediately if the symbol already exists in the DB.
     */
    @PostMapping("/seed")
    public SymbolDto seed(@RequestBody Map<String, String> body) {
        String ticker = body.getOrDefault("ticker", "").trim().toUpperCase();
        if (ticker.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "ticker is required");
        }
        try {
            return SymbolDto.from(symbolService.getByTicker(ticker));
        } catch (NotFoundException ignored) {
            // Not in DB yet — fall through to seed
        }
        MarketDataServiceClient.SymbolSeedResult result = mdClient.seedSymbol(ticker);
        // Python just committed the symbol; re-query to get the full JPA entity.
        return SymbolDto.from(symbolService.getByTicker(result.ticker()));
    }
}
