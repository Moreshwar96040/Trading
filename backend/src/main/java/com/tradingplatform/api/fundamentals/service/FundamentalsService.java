package com.tradingplatform.api.fundamentals.service;

import com.tradingplatform.api.fundamentals.repository.FinancialStatementRepository;
import com.tradingplatform.api.fundamentals.repository.FundamentalsRepository;
import com.tradingplatform.api.fundamentals.web.dto.FundamentalsDto;
import com.tradingplatform.api.marketdata.domain.Symbol;
import com.tradingplatform.api.marketdata.service.SymbolService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class FundamentalsService {

    private final FundamentalsRepository fundamentals;
    private final FinancialStatementRepository statements;
    private final SymbolService symbolService;

    public FundamentalsService(FundamentalsRepository fundamentals,
                               FinancialStatementRepository statements,
                               SymbolService symbolService) {
        this.fundamentals = fundamentals;
        this.statements = statements;
        this.symbolService = symbolService;
    }

    /** Ratios may be null if fundamentals were never refreshed for this symbol. */
    public FundamentalsDto getFundamentals(String ticker) {
        Symbol symbol = symbolService.getByTicker(ticker);

        FundamentalsDto.Ratios ratios = FundamentalsDto.Ratios.from(
                fundamentals.findById(symbol.getId()).orElse(null));

        var annual = statements
                .findBySymbolIdAndPeriodTypeOrderByPeriodEndDesc(symbol.getId(), "ANNUAL")
                .stream().map(FundamentalsDto.StatementRow::from).toList();
        var quarterly = statements
                .findBySymbolIdAndPeriodTypeOrderByPeriodEndDesc(symbol.getId(), "QUARTERLY")
                .stream().map(FundamentalsDto.StatementRow::from).toList();

        return new FundamentalsDto(symbol.getTicker(), symbol.getName(), symbol.getSector(),
                ratios, annual, quarterly);
    }
}
