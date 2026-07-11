package com.tradingplatform.api.screener.service;

import java.util.Map;
import java.util.Set;

/**
 * The screener DSL whitelist: every filterable/sortable field, mapped to its JPA
 * property. Guards against invalid columns — nothing outside this map ever reaches
 * the Criteria API.
 */
public final class ScreenerFields {

    private ScreenerFields() {}

    /** DSL name (snake_case, matches DB + UI) → entity property (camelCase). */
    public static final Map<String, String> NUMERIC = Map.ofEntries(
            Map.entry("close", "close"),
            Map.entry("change_1d_pct", "change1dPct"),
            Map.entry("volume", "volume"),
            Map.entry("avg_volume_20", "avgVolume20"),
            Map.entry("volume_ratio", "volumeRatio"),
            Map.entry("sma_20", "sma20"),
            Map.entry("sma_50", "sma50"),
            Map.entry("sma_200", "sma200"),
            Map.entry("ema_20", "ema20"),
            Map.entry("rsi_14", "rsi14"),
            Map.entry("macd", "macd"),
            Map.entry("macd_signal", "macdSignal"),
            Map.entry("macd_hist", "macdHist"),
            Map.entry("bb_upper", "bbUpper"),
            Map.entry("bb_lower", "bbLower"),
            Map.entry("atr_14", "atr14"),
            Map.entry("high_52w", "high52w"),
            Map.entry("low_52w", "low52w"),
            Map.entry("pct_from_52w_high", "pctFrom52wHigh"),
            Map.entry("pct_from_52w_low", "pctFrom52wLow"),
            Map.entry("return_1m_pct", "return1mPct"),
            Map.entry("return_3m_pct", "return3mPct"),
            Map.entry("return_1y_pct", "return1yPct"),
            // fundamentals (denormalized onto the snapshot in Phase 3)
            Map.entry("market_cap", "marketCap"),
            Map.entry("pe_trailing", "peTrailing"),
            Map.entry("pb", "pb"),
            Map.entry("dividend_yield_pct", "dividendYieldPct"),
            Map.entry("roe_pct", "roePct"),
            Map.entry("debt_to_equity", "debtToEquity"),
            Map.entry("profit_margin_pct", "profitMarginPct"),
            Map.entry("revenue_growth_pct", "revenueGrowthPct"));

    /** String fields live on the joined Symbol. */
    public static final Set<String> STRING = Set.of("sector");

    public static final Set<String> OPS = Set.of("gt", "gte", "lt", "lte", "eq");

    public static boolean isNumeric(String field) {
        return NUMERIC.containsKey(field);
    }

    public static boolean isString(String field) {
        return STRING.contains(field);
    }
}
