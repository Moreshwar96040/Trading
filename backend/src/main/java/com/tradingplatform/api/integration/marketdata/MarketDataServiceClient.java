package com.tradingplatform.api.integration.marketdata;

import com.tradingplatform.api.common.config.AppProperties;
import com.tradingplatform.api.common.error.UpstreamException;
import java.net.http.HttpClient;
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * Thin HTTP client for the internal Python market-data service.
 * All external market-data access flows through that service — this class is
 * the only place the backend knows its URL.
 */
@Component
public class MarketDataServiceClient {

    private final RestClient http;

    public MarketDataServiceClient(RestClient.Builder builder, AppProperties props) {
        // Force HTTP/1.1: the JDK client's default h2c upgrade on plain-HTTP POSTs is
        // rejected by uvicorn ("Unsupported upgrade request"), breaking all POST calls.
        HttpClient http11 = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .build();
        this.http = builder.baseUrl(props.marketDataService().baseUrl())
                .requestFactory(new JdkClientHttpRequestFactory(http11))
                .build();
    }

    public QuoteDto getQuote(String ticker) {
        try {
            return http.get().uri("/internal/quotes/{ticker}", ticker)
                    .retrieve().body(QuoteDto.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Quote service unavailable for " + ticker, ex);
        }
    }

    public SyncSummaryDto syncDaily(List<String> tickers) {
        return syncDaily(tickers, null);
    }

    /** @param fromDate optional ISO date — backfill history at least back to this date. */
    public SyncSummaryDto syncDaily(List<String> tickers, String fromDate) {
        try {
            var body = new java.util.HashMap<String, Object>();
            body.put("tickers", tickers == null ? List.of() : tickers);
            if (fromDate != null && !fromDate.isBlank()) {
                body.put("from_date", fromDate);
            }
            return http.post().uri("/internal/sync/daily")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve().body(SyncSummaryDto.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Sync service unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getIndicators(String ticker, String from, String to) {
        try {
            return http.get()
                    .uri(uriBuilder -> {
                        var b = uriBuilder.path("/internal/indicators/{ticker}");
                        if (from != null) b = b.queryParam("from_date", from);
                        if (to != null) b = b.queryParam("to_date", to);
                        return b.build(ticker);
                    })
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Indicator service unavailable for " + ticker, ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> refreshSnapshots() {
        try {
            return http.post().uri("/internal/snapshot/refresh")
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Snapshot refresh unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> refreshFundamentals(List<String> tickers) {
        try {
            return http.post().uri("/internal/fundamentals/refresh")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("tickers", tickers == null ? List.of() : tickers))
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Fundamentals refresh unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getNews(String ticker, boolean refresh) {
        try {
            return http.get()
                    .uri(uriBuilder -> uriBuilder.path("/internal/news/{ticker}")
                            .queryParam("refresh", refresh).build(ticker))
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("News service unavailable for " + ticker, ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getMarketNews(boolean refresh) {
        try {
            return http.get()
                    .uri(uriBuilder -> uriBuilder.path("/internal/news/market")
                            .queryParam("refresh", refresh).build())
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Market news service unavailable", ex);
        }
    }

    /** Re-pull every market feed, regenerate the macro digest and refresh
     *  per-stock news for signaled/held symbols. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> refreshAllNews() {
        try {
            return http.post().uri("/internal/news/refresh-all")
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("News refresh unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getFundamentalsInsights(String ticker) {
        try {
            return http.get().uri("/internal/insights/fundamentals/{ticker}", ticker)
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Insight service unavailable for " + ticker, ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getRegime() {
        try {
            return http.get().uri("/internal/regime").retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Regime service unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getAiUsage() {
        try {
            return http.get().uri("/internal/ai/usage").retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("AI usage service unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> syncIntraday(List<String> tickers, String interval) {
        try {
            var body = new java.util.HashMap<String, Object>();
            body.put("tickers", tickers == null ? List.of() : tickers);
            if (interval != null && !interval.isBlank()) body.put("interval", interval);
            return http.post().uri("/internal/sync/intraday")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Intraday sync unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getDataHealth() {
        try {
            return http.get().uri("/internal/data/health").retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Data health service unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getEdgeGates() {
        try {
            return http.get().uri("/internal/edge/gates").retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Edge gates service unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getMomentumBoard() {
        try {
            return http.get().uri("/internal/momentum/board").retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Momentum service unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> lookupSymbols(String query) {
        try {
            return http.get()
                    .uri(uriBuilder -> uriBuilder.path("/internal/symbols/lookup")
                            .queryParam("q", query).build())
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Symbol lookup unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getAlphaStack(String ticker) {
        try {
            return http.get()
                    .uri(uriBuilder -> {
                        var b = uriBuilder.path("/internal/alpha/stack");
                        if (ticker != null && !ticker.isBlank()) b = b.queryParam("ticker", ticker);
                        return b.build();
                    })
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Alpha stack service unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getPortfolioHealth() {
        try {
            return http.get().uri("/internal/portfolio/health").retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Guardian service unavailable", ex);
        }
    }

    /** Guardian over paper positions PLUS live broker holdings (read-only import). */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getPortfolioHealthWithLive(List<Map<String, Object>> livePositions) {
        try {
            return http.post().uri("/internal/portfolio/health")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("live_positions", livePositions))
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Guardian service unavailable", ex);
        }
    }

    /** Exness/MT5 FX-crypto account + positions with risk actions (read-only). */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getExnessAccount() {
        try {
            return http.get().uri("/internal/exness/account").retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Exness/MT5 service unavailable", ex);
        }
    }

    /** Paper autopilot: open trades + realised P&amp;L attributed by conviction band. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getAutopilotStatus() {
        try {
            return http.get().uri("/internal/autopilot/status").retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Autopilot service unavailable", ex);
        }
    }

    /** Adaptive conviction: is the Alpha Stack predictive, and what weights
     *  would its own history suggest? Reports COLLECTING until enough data. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getConvictionCalibration(String horizon) {
        try {
            return http.get()
                    .uri(uriBuilder -> uriBuilder.path("/internal/conviction/calibration")
                            .queryParam("horizon", horizon).build())
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Calibration service unavailable", ex);
        }
    }

    /** Fit candidate weights and run every validation gate. Registers a SHADOW
     *  version when all gates pass — never promotes, that stays a human call. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> proposeWeights(String horizon) {
        try {
            return http.post()
                    .uri(uriBuilder -> uriBuilder.path("/internal/conviction/propose")
                            .queryParam("horizon", horizon).build())
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Weight proposal service unavailable", ex);
        }
    }

    /** Partially-pooled weights per regime bucket, with the shrinkage shown. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getRegimeWeights(String horizon) {
        try {
            return http.get()
                    .uri(uriBuilder -> uriBuilder.path("/internal/conviction/regime-weights")
                            .queryParam("horizon", horizon).build())
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Regime weight service unavailable", ex);
        }
    }

    /** Every shadow challenger replayed against the live champion. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getShadowBoard(String horizon) {
        try {
            return http.get()
                    .uri(uriBuilder -> uriBuilder.path("/internal/shadow/board")
                            .queryParam("horizon", horizon).build())
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Shadow evaluation unavailable", ex);
        }
    }

    /** Conditions under which the autopilot must stop opening new positions. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getCircuitBreakers() {
        try {
            return http.get().uri("/internal/circuit-breakers")
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Circuit breaker check unavailable", ex);
        }
    }

    /** Today's setups turned into a book under sector, correlation and risk caps. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getPortfolioPlan(double equity) {
        try {
            return http.get()
                    .uri(uriBuilder -> uriBuilder.path("/internal/portfolio/plan")
                            .queryParam("equity", equity).build())
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Portfolio constructor unavailable", ex);
        }
    }

    /** Registered model versions — the governance view. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> listModelVersions(String kind) {
        try {
            return http.get()
                    .uri(uriBuilder -> uriBuilder.path("/internal/models")
                            .queryParam("kind", kind).build())
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Model registry unavailable", ex);
        }
    }

    /** Promote a shadow version to champion. Attribution is mandatory upstream. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> promoteModel(long versionId, Map<String, Object> body) {
        try {
            return http.post().uri("/internal/models/{id}/promote", versionId)
                    .body(body).retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Model promotion unavailable", ex);
        }
    }

    /** Restore the previously retired champion. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> rollbackModel(Map<String, Object> body) {
        try {
            return http.post().uri("/internal/models/rollback")
                    .body(body).retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Model rollback unavailable", ex);
        }
    }

    /** Closed FX/crypto trade analysis from the MT5 deal history (read-only). */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getExnessTrades(int days) {
        try {
            return http.get()
                    .uri(uriBuilder -> uriBuilder.path("/internal/exness/trades")
                            .queryParam("days", days).build())
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Exness/MT5 trade review unavailable", ex);
        }
    }

    /** Alpha Monitor: score each held stock through the Alpha Stack and recommend
     *  ADD / HOLD / TRIM / SELL. Live broker holdings ride in the body. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getPortfolioAlphaReview(List<Map<String, Object>> livePositions) {
        try {
            return http.post().uri("/internal/portfolio/alpha-review")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("live_positions", livePositions == null ? List.of() : livePositions))
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Alpha Monitor service unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getBriefing(boolean force) {
        try {
            return http.get()
                    .uri(uriBuilder -> uriBuilder.path("/internal/briefing")
                            .queryParam("force", force).build())
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Briefing service unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getLeaksReport() {
        try {
            return http.get().uri("/internal/review/leaks").retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Review service unavailable", ex);
        }
    }

    /** Symbol metadata returned after seeding from Yahoo Finance. */
    public record SymbolSeedResult(Long id, String ticker, String name, String sector,
                                   String exchange, String currency, String yahooSymbol,
                                   boolean seeded) {}

    public SymbolSeedResult seedSymbol(String ticker) {
        try {
            return http.post().uri("/internal/symbols/seed")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("ticker", ticker))
                    .retrieve().body(SymbolSeedResult.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Symbol seed unavailable for " + ticker, ex);
        }
    }

    /** Result of validating a strategy definition in the Python engine. */
    public record ValidationResult(boolean valid, List<String> problems) {}

    public ValidationResult validateStrategy(Object definition) {
        try {
            return http.post().uri("/internal/strategies/validate")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("definition", definition))
                    .retrieve().body(ValidationResult.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Strategy validation service unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> runBacktest(Long strategyId, Map<String, Object> params) {
        try {
            return http.post().uri("/internal/backtests/run")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("strategy_id", strategyId, "params", params))
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Backtest service failed: " + ex.getMessage(), ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> evaluateAlerts() {
        try {
            return http.post().uri("/internal/alerts/evaluate")
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Alert evaluation unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getAiIdeas(int limit) {
        try {
            return http.get().uri("/internal/ai/ideas?limit={limit}", limit)
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("AI ideas service unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getAiRisk(String ticker, Object entryPrice) {
        try {
            return http.get()
                    .uri(uriBuilder -> {
                        var b = uriBuilder.path("/internal/ai/risk/{ticker}");
                        if (entryPrice != null) b = b.queryParam("entry_price", entryPrice);
                        return b.build(ticker);
                    })
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Adaptive risk service unavailable for " + ticker, ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> evaluateSignals() {
        try {
            return http.post().uri("/internal/signals/evaluate")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of())
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("Signal evaluation unavailable", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> trainAi(List<String> tickers) {
        try {
            return http.post().uri("/internal/ai/train")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("tickers", tickers == null ? List.of() : tickers))
                    .retrieve().body(Map.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("AI training unavailable: " + ex.getMessage(), ex);
        }
    }

    public SyncSummaryDto ingestCsv(String directory) {
        try {
            Map<String, Object> body = directory == null ? Map.of() : Map.of("directory", directory);
            return http.post().uri("/internal/ingest/csv")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve().body(SyncSummaryDto.class);
        } catch (RestClientException ex) {
            throw new UpstreamException("CSV ingestion service unavailable", ex);
        }
    }
}
