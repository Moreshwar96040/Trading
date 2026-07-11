package com.tradingplatform.api.strategy.web;

import com.tradingplatform.api.strategy.service.BacktestService;
import com.tradingplatform.api.strategy.service.StrategyService;
import com.tradingplatform.api.strategy.web.dto.StrategyDtos.BacktestSummaryDto;
import com.tradingplatform.api.strategy.web.dto.StrategyDtos.StrategyDto;
import com.tradingplatform.api.strategy.web.dto.StrategyDtos.StrategyRequest;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/strategies")
public class StrategyController {

    private final StrategyService strategyService;
    private final BacktestService backtestService;

    public StrategyController(StrategyService strategyService, BacktestService backtestService) {
        this.strategyService = strategyService;
        this.backtestService = backtestService;
    }

    @GetMapping
    public List<StrategyDto> list() {
        return strategyService.list();
    }

    @GetMapping("/{id}")
    public StrategyDto get(@PathVariable Long id) {
        return strategyService.get(id);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public StrategyDto create(@RequestBody StrategyRequest request) {
        return strategyService.create(request);
    }

    @PutMapping("/{id}")
    public StrategyDto update(@PathVariable Long id, @RequestBody StrategyRequest request) {
        return strategyService.update(id, request);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable Long id) {
        strategyService.delete(id);
    }

    /** Run a backtest. body: {tickers?, from?, to?, initial_capital?, max_positions?, commission_pct?} */
    @PostMapping("/{id}/backtests")
    public Map<String, Object> runBacktest(@PathVariable Long id,
                                           @RequestBody(required = false) Map<String, Object> params) {
        return backtestService.run(id, params == null ? Map.of() : params);
    }

    @GetMapping("/{id}/backtests")
    public List<BacktestSummaryDto> listBacktests(@PathVariable Long id) {
        return backtestService.listForStrategy(id);
    }
}
