package com.tradingplatform.api.strategy.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.common.error.NotFoundException;
import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient.ValidationResult;
import com.tradingplatform.api.strategy.domain.Strategy;
import com.tradingplatform.api.strategy.repository.StrategyRepository;
import com.tradingplatform.api.strategy.web.dto.StrategyDtos.StrategyRequest;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class StrategyServiceTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Mock
    private StrategyRepository repository;

    @Mock
    private MarketDataServiceClient marketData;

    private StrategyService service;

    @BeforeEach
    void setUp() {
        service = new StrategyService(repository, marketData, MAPPER);
    }

    private StrategyRequest request(String name) throws Exception {
        return new StrategyRequest(name, "desc",
                MAPPER.readTree("{\"entry\":[{\"left\":\"rsi_14\",\"op\":\"lt\",\"right\":30}],\"stop_loss_pct\":5}"));
    }

    @Test
    void createValidatesViaPythonAndSaves() throws Exception {
        when(marketData.validateStrategy(any())).thenReturn(new ValidationResult(true, List.of()));
        when(repository.findByNameIgnoreCase("Dip Buyer")).thenReturn(Optional.empty());
        when(repository.save(any(Strategy.class))).thenAnswer(inv -> inv.getArgument(0));

        var dto = service.create(request("Dip Buyer"));

        assertThat(dto.name()).isEqualTo("Dip Buyer");
        assertThat(dto.definition().get("stop_loss_pct").asInt()).isEqualTo(5);
        verify(marketData).validateStrategy(any());
    }

    @Test
    void invalidDefinitionIsRejectedAndNotSaved() throws Exception {
        when(marketData.validateStrategy(any()))
                .thenReturn(new ValidationResult(false, List.of("entry: unknown left series 'x'")));

        assertThatThrownBy(() -> service.create(request("Bad")))
                .isInstanceOf(BadRequestException.class)
                .hasMessageContaining("unknown left series");
        verify(repository, never()).save(any());
    }

    @Test
    void duplicateNameIsRejected() throws Exception {
        Strategy existing = new Strategy("Dip Buyer", null, "{}");
        when(repository.findByNameIgnoreCase("Dip Buyer")).thenReturn(Optional.of(existing));

        assertThatThrownBy(() -> service.create(request("Dip Buyer")))
                .isInstanceOf(BadRequestException.class)
                .hasMessageContaining("already exists");
    }

    @Test
    void blankNameIsRejected() throws Exception {
        assertThatThrownBy(() -> service.create(request("  ")))
                .isInstanceOf(BadRequestException.class)
                .hasMessageContaining("name is required");
    }

    @Test
    void getUnknownIdThrowsNotFound() {
        when(repository.findById(42L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.get(42L)).isInstanceOf(NotFoundException.class);
    }
}
