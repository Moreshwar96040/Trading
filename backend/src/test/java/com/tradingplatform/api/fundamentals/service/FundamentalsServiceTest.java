package com.tradingplatform.api.fundamentals.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

import com.tradingplatform.api.common.error.NotFoundException;
import com.tradingplatform.api.fundamentals.repository.FinancialStatementRepository;
import com.tradingplatform.api.fundamentals.repository.FundamentalsRepository;
import com.tradingplatform.api.fundamentals.web.dto.FundamentalsDto;
import com.tradingplatform.api.marketdata.domain.Symbol;
import com.tradingplatform.api.marketdata.service.SymbolService;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class FundamentalsServiceTest {

    @Mock
    private FundamentalsRepository fundamentalsRepo;

    @Mock
    private FinancialStatementRepository statementRepo;

    @Mock
    private SymbolService symbolService;

    @Mock
    private Symbol reliance;

    @InjectMocks
    private FundamentalsService service;

    private void givenReliance() {
        when(reliance.getId()).thenReturn(1L);
        when(reliance.getTicker()).thenReturn("RELIANCE");
        when(reliance.getName()).thenReturn("Reliance Industries Ltd");
        when(reliance.getSector()).thenReturn("Oil & Gas");
        when(symbolService.getByTicker("RELIANCE")).thenReturn(reliance);
        when(statementRepo.findBySymbolIdAndPeriodTypeOrderByPeriodEndDesc(anyLong(), eq("ANNUAL")))
                .thenReturn(List.of());
        when(statementRepo.findBySymbolIdAndPeriodTypeOrderByPeriodEndDesc(anyLong(), eq("QUARTERLY")))
                .thenReturn(List.of());
    }

    @Test
    void missingFundamentalsYieldsNullRatiosNotError() {
        givenReliance();
        when(fundamentalsRepo.findById(1L)).thenReturn(Optional.empty());

        FundamentalsDto dto = service.getFundamentals("RELIANCE");

        assertThat(dto.ticker()).isEqualTo("RELIANCE");
        assertThat(dto.ratios()).isNull();
        assertThat(dto.annual()).isEmpty();
    }

    @Test
    void unknownTickerPropagatesNotFound() {
        when(symbolService.getByTicker("NOPE")).thenThrow(new NotFoundException("Unknown symbol: NOPE"));

        assertThatThrownBy(() -> service.getFundamentals("NOPE"))
                .isInstanceOf(NotFoundException.class);
    }
}
