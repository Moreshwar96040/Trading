package com.tradingplatform.api.strategy.web.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

/** One live strategy signal, joined with strategy and symbol names for display. */
public record SignalDto(
        Long id,
        Long strategyId,
        String strategyName,
        String ticker,
        String symbolName,
        String signal,
        LocalDate asOfDate,
        BigDecimal close,
        Instant evaluatedAt) {
}
