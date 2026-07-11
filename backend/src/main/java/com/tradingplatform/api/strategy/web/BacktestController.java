package com.tradingplatform.api.strategy.web;

import com.tradingplatform.api.strategy.service.BacktestService;
import com.tradingplatform.api.strategy.web.dto.StrategyDtos.BacktestDetailDto;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/backtests")
public class BacktestController {

    private final BacktestService backtestService;

    public BacktestController(BacktestService backtestService) {
        this.backtestService = backtestService;
    }

    /** Full result: metrics + equity curve + trade list. */
    @GetMapping("/{id}")
    public BacktestDetailDto get(@PathVariable Long id) {
        return backtestService.get(id);
    }
}
