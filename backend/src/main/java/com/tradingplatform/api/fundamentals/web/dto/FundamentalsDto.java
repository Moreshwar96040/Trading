package com.tradingplatform.api.fundamentals.web.dto;

import com.tradingplatform.api.fundamentals.domain.FinancialStatement;
import com.tradingplatform.api.fundamentals.domain.Fundamentals;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;

public record FundamentalsDto(String ticker, String name, String sector,
                              Ratios ratios,
                              List<StatementRow> annual,
                              List<StatementRow> quarterly) {

    public record Ratios(BigDecimal marketCap, BigDecimal peTrailing, BigDecimal peForward,
                         BigDecimal pb, BigDecimal ps, BigDecimal dividendYieldPct,
                         BigDecimal roePct, BigDecimal debtToEquity, BigDecimal profitMarginPct,
                         BigDecimal operatingMarginPct, BigDecimal revenueGrowthPct,
                         BigDecimal earningsGrowthPct, BigDecimal epsTrailing,
                         BigDecimal bookValue, BigDecimal beta, Instant computedAt) {

        public static Ratios from(Fundamentals f) {
            if (f == null) {
                return null;
            }
            return new Ratios(f.getMarketCap(), f.getPeTrailing(), f.getPeForward(),
                    f.getPb(), f.getPs(), f.getDividendYieldPct(), f.getRoePct(),
                    f.getDebtToEquity(), f.getProfitMarginPct(), f.getOperatingMarginPct(),
                    f.getRevenueGrowthPct(), f.getEarningsGrowthPct(), f.getEpsTrailing(),
                    f.getBookValue(), f.getBeta(), f.getComputedAt());
        }
    }

    public record StatementRow(LocalDate periodEnd, BigDecimal revenue,
                               BigDecimal operatingIncome, BigDecimal netIncome, BigDecimal eps,
                               BigDecimal totalAssets, BigDecimal totalLiabilities,
                               BigDecimal shareholdersEquity, BigDecimal operatingCashFlow,
                               BigDecimal freeCashFlow) {

        public static StatementRow from(FinancialStatement s) {
            return new StatementRow(s.getPeriodEnd(), s.getRevenue(), s.getOperatingIncome(),
                    s.getNetIncome(), s.getEps(), s.getTotalAssets(), s.getTotalLiabilities(),
                    s.getShareholdersEquity(), s.getOperatingCashFlow(), s.getFreeCashFlow());
        }
    }
}
