package com.tradingplatform.api.common.config;

import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * All application-level knobs, bound from application.yml / environment.
 * No values are hardcoded anywhere else.
 */
@ConfigurationProperties(prefix = "app")
public record AppProperties(MarketDataService marketDataService, Cors cors, Candles candles) {

    /** Base URL of the internal Python market-data service. */
    public record MarketDataService(String baseUrl, int timeoutSeconds) {}

    /** Origins allowed to call this API (the Angular dev server by default). */
    public record Cors(List<String> allowedOrigins) {}

    /** Candle query defaults. */
    public record Candles(int defaultRangeDays, int maxRangeDays) {}
}
