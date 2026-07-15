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

    /** GET /api/v1/momentum/board — sector rotation heat + RS leaders. */
    @GetMapping("/momentum/board")
    public Map<String, Object> momentumBoard() {
        return marketData.getMomentumBoard();
    }

    /** GET /api/v1/symbols/lookup?q= — search all NSE stocks (local DB + Yahoo). */
    @GetMapping("/symbols/lookup")
    public Map<String, Object> lookupSymbols(
            @org.springframework.web.bind.annotation.RequestParam String q) {
        return marketData.lookupSymbols(q);
    }

    /** GET /api/v1/alpha/stack?ticker= — conviction-ranked live setups. */
    @GetMapping("/alpha/stack")
    public Map<String, Object> alphaStack(
            @org.springframework.web.bind.annotation.RequestParam(required = false)
            String ticker) {
        return marketData.getAlphaStack(ticker);
    }

    /** GET /api/v1/portfolio/health — Position Guardian action queue. */
    @GetMapping("/portfolio/health")
    public Map<String, Object> portfolioHealth() {
        return marketData.getPortfolioHealth();
    }

    /** GET /api/v1/briefing — the morning AI briefing (cached per day). */
    @GetMapping("/briefing")
    public Map<String, Object> briefing(
            @org.springframework.web.bind.annotation.RequestParam(defaultValue = "false")
            boolean force) {
        return marketData.getBriefing(force);
    }
}
