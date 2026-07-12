package com.tradingplatform.api.strategy.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tradingplatform.api.paper.domain.PaperOrder;
import com.tradingplatform.api.paper.repository.PaperOrderRepository;
import com.tradingplatform.api.strategy.domain.Backtest;
import com.tradingplatform.api.strategy.repository.BacktestRepository;
import com.tradingplatform.api.strategy.repository.StrategyRepository;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Phase E feedback loop: how is each strategy doing in LIVE paper trading versus
 * what its backtest promised? A strategy whose live win rate collapses below its
 * backtest is decaying — the scoreboard makes that visible instead of hopeful.
 */
@Service
public class ScoreboardService {

    public record StrategyScore(Long strategyId, String name, int liveTrades, int liveWins,
                                Double liveWinRatePct, BigDecimal livePnl,
                                Double backtestWinRatePct, Double backtestTotalReturnPct,
                                String verdict) {}

    private static final double DECAY_TOLERANCE_PCT = 15.0;   // live may lag backtest by this much
    private static final int MIN_LIVE_TRADES = 3;             // fewer = not enough evidence

    private final StrategyRepository strategies;
    private final BacktestRepository backtests;
    private final PaperOrderRepository orders;
    private final ObjectMapper objectMapper;

    public ScoreboardService(StrategyRepository strategies, BacktestRepository backtests,
                             PaperOrderRepository orders, ObjectMapper objectMapper) {
        this.strategies = strategies;
        this.backtests = backtests;
        this.orders = orders;
        this.objectMapper = objectMapper;
    }

    @Transactional(readOnly = true)
    public List<StrategyScore> scoreboard() {
        Map<Long, List<PaperOrder>> sellsByStrategy =
                orders.findByStrategyIdIsNotNullAndStatus("FILLED").stream()
                        .filter(o -> "SELL".equals(o.getSide()) && o.getRealizedPnl() != null)
                        .collect(Collectors.groupingBy(PaperOrder::getStrategyId));

        return strategies.findAll().stream().map(strategy -> {
            List<PaperOrder> sells = sellsByStrategy.getOrDefault(strategy.getId(), List.of());
            int trades = sells.size();
            int wins = (int) sells.stream().filter(o -> o.getRealizedPnl().signum() > 0).count();
            BigDecimal pnl = sells.stream().map(PaperOrder::getRealizedPnl)
                    .reduce(BigDecimal.ZERO, BigDecimal::add).setScale(2, RoundingMode.HALF_UP);
            Double liveWinRate = trades == 0 ? null
                    : Math.round(wins * 10000.0 / trades) / 100.0;

            JsonNode metrics = latestBacktestMetrics(strategy.getId());
            Double btWinRate = doubleOrNull(metrics, "win_rate_pct");
            Double btReturn = doubleOrNull(metrics, "total_return_pct");

            return new StrategyScore(strategy.getId(), strategy.getName(), trades, wins,
                    liveWinRate, pnl, btWinRate, btReturn,
                    verdict(trades, liveWinRate, btWinRate));
        }).toList();
    }

    private String verdict(int liveTrades, Double liveWinRate, Double backtestWinRate) {
        if (liveTrades < MIN_LIVE_TRADES || liveWinRate == null) {
            return "NOT_ENOUGH_DATA";
        }
        if (backtestWinRate == null) {
            return "NO_BACKTEST";
        }
        return liveWinRate + DECAY_TOLERANCE_PCT >= backtestWinRate ? "ON_TRACK" : "DECAYING";
    }

    private JsonNode latestBacktestMetrics(Long strategyId) {
        return backtests.findByStrategyIdOrderByStartedAtDesc(strategyId).stream()
                .filter(b -> "SUCCESS".equals(b.getStatus()) && b.getMetrics() != null)
                .findFirst()
                .map(Backtest::getMetrics)
                .map(json -> {
                    try {
                        return objectMapper.readTree(json);
                    } catch (Exception ex) {
                        return null;
                    }
                })
                .orElse(null);
    }

    private static Double doubleOrNull(JsonNode node, String field) {
        return node != null && node.hasNonNull(field) ? node.get(field).asDouble() : null;
    }
}
