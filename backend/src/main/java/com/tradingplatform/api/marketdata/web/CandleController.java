package com.tradingplatform.api.marketdata.web;

import com.tradingplatform.api.marketdata.service.CandleService;
import com.tradingplatform.api.marketdata.web.dto.CandleSeriesDto;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/symbols/{ticker}/candles")
public class CandleController {

    private final CandleService candleService;

    public CandleController(CandleService candleService) {
        this.candleService = candleService;
    }

    /** GET /api/v1/symbols/RELIANCE/candles?from=2025-01-01&to=2026-06-30 */
    @GetMapping
    public CandleSeriesDto getCandles(
            @PathVariable String ticker,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate to) {
        return candleService.getDailyCandles(ticker, from, to);
    }
}
