package com.tradingplatform.api.marketdata.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

import com.tradingplatform.api.common.config.AppProperties;
import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.common.error.NotFoundException;
import com.tradingplatform.api.marketdata.domain.Symbol;
import com.tradingplatform.api.marketdata.repository.OhlcvDailyRepository;
import com.tradingplatform.api.marketdata.web.dto.CandleSeriesDto;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

@ExtendWith(MockitoExtension.class)
// Lenient: givenRelianceExists() stubs more than each individual test consumes,
// which strict stubbing would (wrongly, here) report as an error.
@MockitoSettings(strictness = Strictness.LENIENT)
class CandleServiceTest {

    private static final LocalDate LATEST = LocalDate.of(2026, 6, 30);

    @Mock
    private OhlcvDailyRepository candleRepo;

    @Mock
    private SymbolService symbolService;

    @Mock
    private Symbol reliance;

    private CandleService service;

    @BeforeEach
    void setUp() {
        AppProperties props = new AppProperties(
                new AppProperties.MarketDataService("http://localhost:8000", 30),
                new AppProperties.Cors(List.of("http://localhost:4200")),
                new AppProperties.Candles(365, 3700));
        service = new CandleService(candleRepo, symbolService, props);
    }

    private void givenRelianceExists() {
        when(reliance.getId()).thenReturn(1L);
        when(reliance.getTicker()).thenReturn("RELIANCE");
        when(symbolService.getByTicker("RELIANCE")).thenReturn(reliance);
    }

    @Test
    void defaultsToLatestStoredDateMinusConfiguredRange() {
        givenRelianceExists();
        when(candleRepo.findLatestTradeDate(1L)).thenReturn(Optional.of(LATEST));
        when(candleRepo.findBySymbolIdAndTradeDateBetweenOrderByTradeDateAsc(
                anyLong(), any(), any())).thenReturn(List.of());

        CandleSeriesDto result = service.getDailyCandles("RELIANCE", null, null);

        assertThat(result.to()).isEqualTo(LATEST);
        assertThat(result.from()).isEqualTo(LATEST.minusDays(365));
        assertThat(result.ticker()).isEqualTo("RELIANCE");
    }

    @Test
    void explicitRangeIsUsedAsIs() {
        givenRelianceExists();
        LocalDate from = LocalDate.of(2026, 1, 1);
        LocalDate to = LocalDate.of(2026, 3, 1);
        when(candleRepo.findBySymbolIdAndTradeDateBetweenOrderByTradeDateAsc(1L, from, to))
                .thenReturn(List.of());

        CandleSeriesDto result = service.getDailyCandles("RELIANCE", from, to);

        assertThat(result.from()).isEqualTo(from);
        assertThat(result.to()).isEqualTo(to);
    }

    @Test
    void fromAfterToIsRejected() {
        givenRelianceExists();

        assertThatThrownBy(() -> service.getDailyCandles("RELIANCE",
                LocalDate.of(2026, 5, 1), LocalDate.of(2026, 1, 1)))
                .isInstanceOf(BadRequestException.class);
    }

    @Test
    void oversizedRangeIsRejected() {
        givenRelianceExists();

        assertThatThrownBy(() -> service.getDailyCandles("RELIANCE",
                LocalDate.of(2000, 1, 1), LocalDate.of(2026, 1, 1)))
                .isInstanceOf(BadRequestException.class)
                .hasMessageContaining("Range too large");
    }

    @Test
    void unknownTickerPropagatesNotFound() {
        when(symbolService.getByTicker(eq("NOPE"))).thenThrow(new NotFoundException("Unknown symbol: NOPE"));

        assertThatThrownBy(() -> service.getDailyCandles("NOPE", null, null))
                .isInstanceOf(NotFoundException.class);
    }
}
