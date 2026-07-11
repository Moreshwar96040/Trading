package com.tradingplatform.api.screener.web.dto;

/**
 * One filter condition: {@code field op (value | ref)}.
 * Exactly one of {@code value} (number/string literal) or {@code ref}
 * (another snapshot field, for cross-field filters like close > sma_200) must be set.
 */
public record ScreenCondition(String field, String op, Object value, String ref) {}
