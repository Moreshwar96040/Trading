package com.tradingplatform.api.integration.marketdata;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;
import java.time.Instant;

/** Quote as returned by the Python market-data service (15-min delayed). */
public record QuoteDto(String ticker,
                       @JsonProperty("yahoo_symbol") String yahooSymbol,
                       BigDecimal price,
                       @JsonProperty("prev_close") BigDecimal prevClose,
                       BigDecimal change,
                       @JsonProperty("change_pct") BigDecimal changePct,
                       @JsonProperty("as_of") Instant asOf) {}
