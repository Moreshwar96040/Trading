package com.tradingplatform.api.marketdata.service;

import com.tradingplatform.api.common.error.NotFoundException;
import com.tradingplatform.api.marketdata.domain.Symbol;
import com.tradingplatform.api.marketdata.repository.SymbolRepository;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class SymbolService {

    private final SymbolRepository symbols;

    public SymbolService(SymbolRepository symbols) {
        this.symbols = symbols;
    }

    /** Blank query returns all active symbols. */
    public List<Symbol> search(String query) {
        if (query == null || query.isBlank()) {
            return symbols.findByActiveTrueOrderByTickerAsc();
        }
        return symbols.search(query.trim());
    }

    public Symbol getByTicker(String ticker) {
        return symbols.findByTickerIgnoreCaseAndActiveTrue(ticker)
                .orElseThrow(() -> new NotFoundException("Unknown symbol: " + ticker));
    }

    public Symbol getById(Long id) {
        return symbols.findById(id)
                .orElseThrow(() -> new NotFoundException("Unknown symbol id: " + id));
    }
}
