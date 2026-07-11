package com.tradingplatform.api.strategy.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tradingplatform.api.common.error.NotFoundException;
import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import com.tradingplatform.api.strategy.domain.Backtest;
import com.tradingplatform.api.strategy.repository.BacktestRepository;
import com.tradingplatform.api.strategy.repository.BacktestTradeRepository;
import com.tradingplatform.api.strategy.web.dto.StrategyDtos.BacktestDetailDto;
import com.tradingplatform.api.strategy.web.dto.StrategyDtos.BacktestSummaryDto;
import com.tradingplatform.api.strategy.web.dto.StrategyDtos.TradeDto;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BacktestService {

    private final BacktestRepository backtests;
    private final BacktestTradeRepository trades;
    private final StrategyService strategyService;
    private final MarketDataServiceClient marketData;
    private final ObjectMapper objectMapper;

    public BacktestService(BacktestRepository backtests, BacktestTradeRepository trades,
                           StrategyService strategyService, MarketDataServiceClient marketData,
                           ObjectMapper objectMapper) {
        this.backtests = backtests;
        this.trades = trades;
        this.strategyService = strategyService;
        this.marketData = marketData;
        this.objectMapper = objectMapper;
    }

    /** Runs synchronously in the Python engine; returns the run summary. */
    public Map<String, Object> run(Long strategyId, Map<String, Object> params) {
        strategyService.getEntity(strategyId);           // 404 before calling Python
        return marketData.runBacktest(strategyId, params);
    }

    @Transactional(readOnly = true)
    public List<BacktestSummaryDto> listForStrategy(Long strategyId) {
        strategyService.getEntity(strategyId);
        return backtests.findByStrategyIdOrderByStartedAtDesc(strategyId).stream()
                .map(b -> BacktestSummaryDto.from(b, this::parse)).toList();
    }

    @Transactional(readOnly = true)
    public BacktestDetailDto get(Long backtestId) {
        Backtest b = backtests.findById(backtestId)
                .orElseThrow(() -> new NotFoundException("Unknown backtest: " + backtestId));
        List<TradeDto> tradeDtos = trades.findByBacktestIdOrderByEntryDateAsc(backtestId)
                .stream().map(TradeDto::from).toList();
        return new BacktestDetailDto(b.getId(), b.getStrategyId(), b.getStatus(),
                b.getStartedAt(), b.getFinishedAt(), parse(b.getParams()),
                parse(b.getMetrics()), parse(b.getEquityCurve()), b.getError(), tradeDtos);
    }

    private JsonNode parse(String json) {
        if (json == null) {
            return null;
        }
        try {
            return objectMapper.readTree(json);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Corrupt JSON in database", ex);
        }
    }
}
