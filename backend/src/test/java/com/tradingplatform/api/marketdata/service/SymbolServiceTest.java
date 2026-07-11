package com.tradingplatform.api.marketdata.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.tradingplatform.api.common.error.NotFoundException;
import com.tradingplatform.api.marketdata.domain.Symbol;
import com.tradingplatform.api.marketdata.repository.SymbolRepository;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class SymbolServiceTest {

    @Mock
    private SymbolRepository repository;

    @InjectMocks
    private SymbolService service;

    @Test
    void blankQueryReturnsAllActiveSymbols() {
        when(repository.findByActiveTrueOrderByTickerAsc()).thenReturn(List.of(mock(Symbol.class)));

        assertThat(service.search("  ")).hasSize(1);
        verify(repository).findByActiveTrueOrderByTickerAsc();
    }

    @Test
    void queryIsTrimmedAndDelegatedToSearch() {
        when(repository.search("rel")).thenReturn(List.of(mock(Symbol.class)));

        assertThat(service.search(" rel ")).hasSize(1);
        verify(repository).search("rel");
    }

    @Test
    void unknownTickerThrowsNotFound() {
        when(repository.findByTickerIgnoreCaseAndActiveTrue("NOPE")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.getByTicker("NOPE"))
                .isInstanceOf(NotFoundException.class)
                .hasMessageContaining("NOPE");
    }
}
