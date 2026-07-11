package com.tradingplatform.api.marketdata.web.dto;

import com.tradingplatform.api.marketdata.domain.Symbol;

public record SymbolDto(Long id, String ticker, String name, String sector,
                        String exchange, String currency) {

    public static SymbolDto from(Symbol s) {
        return new SymbolDto(s.getId(), s.getTicker(), s.getName(), s.getSector(),
                s.getExchange(), s.getCurrency());
    }
}
