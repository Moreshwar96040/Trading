package com.tradingplatform.api.strategy.web.dto;

import com.fasterxml.jackson.databind.JsonNode;
import com.tradingplatform.api.strategy.domain.Backtest;
import com.tradingplatform.api.strategy.domain.BacktestTrade;
import com.tradingplatform.api.strategy.domain.Strategy;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.function.Function;

/** Request/response records for strategies + backtests. */
public final class StrategyDtos {

    private StrategyDtos() {}

    public record StrategyRequest(String name, String description, JsonNode definition) {}

    public record StrategyDto(Long id, String name, String description, JsonNode definition,
                              Instant createdAt, Instant updatedAt) {

        public static StrategyDto from(Strategy s, Function<String, JsonNode> parse) {
            return new StrategyDto(s.getId(), s.getName(), s.getDescription(),
                    parse.apply(s.getDefinition()), s.getCreatedAt(), s.getUpdatedAt());
        }
    }

    public record BacktestSummaryDto(Long id, Long strategyId, String status,
                                     Instant startedAt, Instant finishedAt,
                                     JsonNode params, JsonNode metrics, String error) {

        public static BacktestSummaryDto from(Backtest b, Function<String, JsonNode> parse) {
            return new BacktestSummaryDto(b.getId(), b.getStrategyId(), b.getStatus(),
                    b.getStartedAt(), b.getFinishedAt(), parse.apply(b.getParams()),
                    parse.apply(b.getMetrics()), b.getError());
        }
    }

    public record BacktestDetailDto(Long id, Long strategyId, String status,
                                    Instant startedAt, Instant finishedAt, JsonNode params,
                                    JsonNode metrics, JsonNode equityCurve, String error,
                                    List<TradeDto> trades) {}

    public record TradeDto(String ticker, LocalDate entryDate, BigDecimal entryPrice,
                           LocalDate exitDate, BigDecimal exitPrice, Integer quantity,
                           BigDecimal pnl, BigDecimal pnlPct, String exitReason) {

        public static TradeDto from(BacktestTrade t) {
            return new TradeDto(t.getTicker(), t.getEntryDate(), t.getEntryPrice(),
                    t.getExitDate(), t.getExitPrice(), t.getQuantity(), t.getPnl(),
                    t.getPnlPct(), t.getExitReason());
        }
    }
}
