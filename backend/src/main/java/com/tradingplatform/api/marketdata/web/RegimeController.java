package com.tradingplatform.api.marketdata.web;

import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import com.tradingplatform.api.integration.upstox.UpstoxService;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Market regime + trading-review analytics (proxied from the Python service). */
@RestController
@RequestMapping("/api/v1")
public class RegimeController {

    private final MarketDataServiceClient marketData;
    private final UpstoxService upstox;

    public RegimeController(MarketDataServiceClient marketData, UpstoxService upstox) {
        this.marketData = marketData;
        this.upstox = upstox;
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

    /** GET /api/v1/data/health — freshness of every data source. */
    @GetMapping("/data/health")
    public Map<String, Object> dataHealth() {
        return marketData.getDataHealth();
    }

    /** GET /api/v1/edge/gates — per-strategy validation pipeline. */
    @GetMapping("/edge/gates")
    public Map<String, Object> edgeGates() {
        return marketData.getEdgeGates();
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

    /** GET /api/v1/portfolio/health — Guardian action queue; when Upstox is
     *  connected, real holdings join the checks (marked [LIVE]). */
    @GetMapping("/portfolio/health")
    public Map<String, Object> portfolioHealth() {
        List<Map<String, Object>> live = upstox.livePositions();
        return live.isEmpty()
                ? marketData.getPortfolioHealth()
                : marketData.getPortfolioHealthWithLive(live);
    }

    /** GET /api/v1/exness/account — MT5 (Exness) FX/crypto account, open positions
     *  and risk actions. Read-only; no order endpoints by design. */
    @GetMapping("/exness/account")
    public Map<String, Object> exnessAccount() {
        return marketData.getExnessAccount();
    }

    /** GET /api/v1/autopilot/status — paper autopilot positions and realised
     *  P&amp;L attributed by conviction band. Paper only. */
    @GetMapping("/autopilot/status")
    public Map<String, Object> autopilotStatus() {
        return marketData.getAutopilotStatus();
    }

    /** GET /api/v1/conviction/calibration — per-layer IC, calibration curve and
     *  suggested weights learned from the Alpha Stack's own recorded history. */
    @GetMapping("/conviction/calibration")
    public Map<String, Object> convictionCalibration(
            @org.springframework.web.bind.annotation.RequestParam(
                    defaultValue = "fwd_return_10d") String horizon) {
        return marketData.getConvictionCalibration(horizon);
    }

    /** GET /api/v1/exness/trades?days=90 — closed FX/crypto trade analysis. */
    @GetMapping("/exness/trades")
    public Map<String, Object> exnessTrades(
            @org.springframework.web.bind.annotation.RequestParam(defaultValue = "90")
            int days) {
        return marketData.getExnessTrades(days);
    }

    /** GET /api/v1/portfolio/alpha-review — score each holding through the Alpha
     *  Stack and recommend ADD / HOLD / TRIM / SELL. Live Upstox holdings included
     *  when connected. Suggestions only — no orders are placed. */
    @GetMapping("/portfolio/alpha-review")
    public Map<String, Object> portfolioAlphaReview() {
        return marketData.getPortfolioAlphaReview(upstox.livePositions());
    }

    /** GET /api/v1/briefing — the morning AI briefing (cached per day). */
    @GetMapping("/briefing")
    public Map<String, Object> briefing(
            @org.springframework.web.bind.annotation.RequestParam(defaultValue = "false")
            boolean force) {
        return marketData.getBriefing(force);
    }
}
