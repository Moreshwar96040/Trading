package com.tradingplatform.api.marketdata.web;

import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Market regime + trading-review analytics (proxied from the Python service). */
@RestController
@RequestMapping("/api/v1")
public class RegimeController {

    private final MarketDataServiceClient marketData;

    public RegimeController(MarketDataServiceClient marketData) {
        this.marketData = marketData;
    }

    /** GET /api/v1/regime — breadth-based market regime. */
    @GetMapping("/regime")
    public Map<String, Object> regime() {
        return marketData.getRegime();
    }

    /** GET /api/v1/review/leaks — trading-habit analytics + AI coach narrative. */
    @GetMapping("/review/leaks")
    public Map<String, Object> leaks() {
        return marketData.getLeaksReport();
    }

    /** GET /api/v1/ai/usage — what the LLM insights have cost (month, total, by kind). */
    @GetMapping("/ai/usage")
    public Map<String, Object> aiUsage() {
        return marketData.getAiUsage();
    }
}
