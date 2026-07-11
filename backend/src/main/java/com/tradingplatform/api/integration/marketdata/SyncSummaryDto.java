package com.tradingplatform.api.integration.marketdata;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Map;

/** Result of an ingestion/sync run in the Python market-data service. */
public record SyncSummaryDto(String status,
                             @JsonProperty("rows_inserted") int rowsInserted,
                             @JsonProperty("rows_rejected") int rowsRejected,
                             Map<String, Object> symbols,
                             List<String> failures) {}
