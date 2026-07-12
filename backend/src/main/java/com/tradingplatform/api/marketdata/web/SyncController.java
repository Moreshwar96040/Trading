package com.tradingplatform.api.marketdata.web;

import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import com.tradingplatform.api.integration.marketdata.SyncSummaryDto;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Manual triggers for data loads (the scheduled sync runs inside the Python service). */
@RestController
@RequestMapping("/api/v1/sync")
public class SyncController {

    private final MarketDataServiceClient marketData;

    public SyncController(MarketDataServiceClient marketData) {
        this.marketData = marketData;
    }

    /**
     * POST /api/v1/sync/daily  body: {"tickers": ["RELIANCE"], "from": "2020-01-01"}
     * (both optional; empty tickers = all, "from" backfills history back to that date).
     */
    @PostMapping("/daily")
    @SuppressWarnings("unchecked")
    public SyncSummaryDto syncDaily(@RequestBody(required = false) Map<String, Object> body) {
        List<String> tickers = body != null && body.get("tickers") instanceof List<?> list
                ? (List<String>) list : List.of();
        String from = body != null && body.get("from") instanceof String s ? s : null;
        return marketData.syncDaily(tickers, from);
    }

    /** POST /api/v1/sync/csv-import — one-time import of the local dataset. */
    @PostMapping("/csv-import")
    public SyncSummaryDto csvImport() {
        return marketData.ingestCsv(null);
    }

    /** POST /api/v1/sync/snapshot — recompute screener snapshots on demand. */
    @PostMapping("/snapshot")
    public Map<String, Object> refreshSnapshots() {
        return marketData.refreshSnapshots();
    }

    /** POST /api/v1/sync/fundamentals — fetch ratios + statements from Yahoo (slow: ~1 min). */
    @PostMapping("/fundamentals")
    public Map<String, Object> refreshFundamentals(
            @RequestBody(required = false) Map<String, List<String>> body) {
        List<String> tickers = body == null ? List.of() : body.getOrDefault("tickers", List.of());
        return marketData.refreshFundamentals(tickers);
    }
}
