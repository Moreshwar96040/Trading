package com.tradingplatform.api.fundamentals.web;

import com.tradingplatform.api.fundamentals.service.FundamentalsService;
import com.tradingplatform.api.fundamentals.web.dto.FundamentalsDto;
import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/fundamentals")
public class FundamentalsController {

    private final FundamentalsService fundamentalsService;
    private final MarketDataServiceClient marketData;

    public FundamentalsController(FundamentalsService fundamentalsService,
                                  MarketDataServiceClient marketData) {
        this.fundamentalsService = fundamentalsService;
        this.marketData = marketData;
    }

    /** GET /api/v1/fundamentals/RELIANCE — ratios + annual/quarterly statements. */
    @GetMapping("/{ticker}")
    public FundamentalsDto get(@PathVariable String ticker) {
        return fundamentalsService.getFundamentals(ticker);
    }

    /** GET /api/v1/fundamentals/RELIANCE/insights — plain-language AI read of the ratios. */
    @GetMapping("/{ticker}/insights")
    public Map<String, Object> insights(@PathVariable String ticker) {
        return marketData.getFundamentalsInsights(ticker);
    }
}
