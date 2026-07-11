package com.tradingplatform.api.ai.web;

import com.tradingplatform.api.ai.domain.AiPrediction;
import com.tradingplatform.api.ai.repository.AiPredictionRepository;
import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import com.tradingplatform.api.marketdata.service.SymbolService;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/ai")
public class AiController {

    public record PredictionDto(String ticker, String name, LocalDate asOfDate,
                                BigDecimal predictedReturnPct, String direction,
                                BigDecimal testDirectionAccuracy, BigDecimal testMaePct,
                                Integer trainRows, String modelName, Instant trainedAt) {}

    private final AiPredictionRepository predictions;
    private final SymbolService symbolService;
    private final MarketDataServiceClient marketData;

    public AiController(AiPredictionRepository predictions, SymbolService symbolService,
                        MarketDataServiceClient marketData) {
        this.predictions = predictions;
        this.symbolService = symbolService;
        this.marketData = marketData;
    }

    @GetMapping("/predictions")
    @Transactional(readOnly = true)
    public List<PredictionDto> list() {
        Map<Long, com.tradingplatform.api.marketdata.domain.Symbol> cache = new HashMap<>();
        return predictions.findAll().stream()
                .map(p -> {
                    var symbol = cache.computeIfAbsent(p.getSymbolId(), symbolService::getById);
                    return new PredictionDto(symbol.getTicker(), symbol.getName(), p.getAsOfDate(),
                            p.getPredictedReturnPct(), p.getDirection(),
                            p.getTestDirectionAccuracy(), p.getTestMaePct(), p.getTrainRows(),
                            p.getModelName(), p.getTrainedAt());
                })
                .sorted((a, b) -> b.predictedReturnPct().compareTo(a.predictedReturnPct()))
                .toList();
    }

    /** Train models for all (or selected) symbols. Takes ~10-30s for 20 symbols. */
    @PostMapping("/train")
    public Map<String, Object> train(@RequestBody(required = false) Map<String, List<String>> body) {
        List<String> tickers = body == null ? List.of() : body.getOrDefault("tickers", List.of());
        return marketData.trainAi(tickers);
    }
}
