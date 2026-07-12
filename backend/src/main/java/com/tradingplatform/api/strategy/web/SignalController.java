package com.tradingplatform.api.strategy.web;

import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import com.tradingplatform.api.strategy.repository.StrategySignalRepository;
import com.tradingplatform.api.strategy.web.dto.SignalDto;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Live strategy signals: read the latest evaluations, or trigger a re-evaluation. */
@RestController
@RequestMapping("/api/v1/signals")
public class SignalController {

    private final StrategySignalRepository signals;
    private final MarketDataServiceClient marketData;

    public SignalController(StrategySignalRepository signals, MarketDataServiceClient marketData) {
        this.signals = signals;
        this.marketData = marketData;
    }

    @GetMapping
    public List<SignalDto> list() {
        return signals.findAllForDisplay();
    }

    /** Re-run every strategy's rules against the latest bar (synchronous, fast). */
    @PostMapping("/evaluate")
    public Map<String, Object> evaluate() {
        return marketData.evaluateSignals();
    }
}
