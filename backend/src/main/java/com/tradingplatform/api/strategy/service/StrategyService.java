package com.tradingplatform.api.strategy.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.common.error.NotFoundException;
import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import com.tradingplatform.api.strategy.domain.Strategy;
import com.tradingplatform.api.strategy.repository.StrategyRepository;
import com.tradingplatform.api.strategy.web.dto.StrategyDtos.StrategyDto;
import com.tradingplatform.api.strategy.web.dto.StrategyDtos.StrategyRequest;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StrategyService {

    private final StrategyRepository strategies;
    private final MarketDataServiceClient marketData;
    private final ObjectMapper objectMapper;

    public StrategyService(StrategyRepository strategies, MarketDataServiceClient marketData,
                           ObjectMapper objectMapper) {
        this.strategies = strategies;
        this.marketData = marketData;
        this.objectMapper = objectMapper;
    }

    @Transactional(readOnly = true)
    public List<StrategyDto> list() {
        return strategies.findAll().stream()
                .map(s -> StrategyDto.from(s, this::parse)).toList();
    }

    @Transactional(readOnly = true)
    public StrategyDto get(Long id) {
        return StrategyDto.from(getEntity(id), this::parse);
    }

    @Transactional
    public StrategyDto create(StrategyRequest request) {
        validateRequest(request, null);
        Strategy saved = strategies.save(new Strategy(request.name().trim(),
                request.description(), request.definition().toString()));
        return StrategyDto.from(saved, this::parse);
    }

    @Transactional
    public StrategyDto update(Long id, StrategyRequest request) {
        Strategy strategy = getEntity(id);
        validateRequest(request, id);
        strategy.update(request.name().trim(), request.description(),
                request.definition().toString());
        return StrategyDto.from(strategies.save(strategy), this::parse);
    }

    @Transactional
    public void delete(Long id) {
        strategies.delete(getEntity(id));
    }

    Strategy getEntity(Long id) {
        return strategies.findById(id)
                .orElseThrow(() -> new NotFoundException("Unknown strategy: " + id));
    }

    // ---------------------------------------------------------------- helpers
    private void validateRequest(StrategyRequest request, Long selfId) {
        if (request.name() == null || request.name().isBlank()) {
            throw new BadRequestException("Strategy name is required");
        }
        if (request.definition() == null || request.definition().isNull()) {
            throw new BadRequestException("Strategy definition is required");
        }
        strategies.findByNameIgnoreCase(request.name().trim())
                .filter(existing -> selfId == null || !selfId.equals(existing.getId()))
                .ifPresent(existing -> {
                    throw new BadRequestException("Strategy name already exists: " + request.name());
                });

        // The Python engine is the source of truth for definition validity.
        var validation = marketData.validateStrategy(request.definition());
        if (!validation.valid()) {
            throw new BadRequestException("Invalid strategy: "
                    + String.join("; ", validation.problems()));
        }
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
