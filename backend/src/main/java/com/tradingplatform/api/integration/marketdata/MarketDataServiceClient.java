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
        try {
            return http.post().uri("/internal/sync/daily")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("tickers", tickers == null ? List.of() : tickers))
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
