package com.tradingplatform.api.fundamentals.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;

/** Read model: latest fundamental ratios per symbol (written by the Python service). */
@Entity
@Table(name = "fundamentals")
public class Fundamentals {

    @Id
    @Column(name = "symbol_id")
    private Long symbolId;

    @Column(name = "market_cap")
    private BigDecimal marketCap;

    @Column(name = "pe_trailing")
    private BigDecimal peTrailing;

    @Column(name = "pe_forward")
    private BigDecimal peForward;

    private BigDecimal pb;

    private BigDecimal ps;

    @Column(name = "dividend_yield_pct")
    private BigDecimal dividendYieldPct;

    @Column(name = "roe_pct")
    private BigDecimal roePct;

    @Column(name = "debt_to_equity")
    private BigDecimal debtToEquity;

    @Column(name = "profit_margin_pct")
    private BigDecimal profitMarginPct;

    @Column(name = "operating_margin_pct")
    private BigDecimal operatingMarginPct;

    @Column(name = "revenue_growth_pct")
    private BigDecimal revenueGrowthPct;

    @Column(name = "earnings_growth_pct")
    private BigDecimal earningsGrowthPct;

    @Column(name = "eps_trailing")
    private BigDecimal epsTrailing;

    @Column(name = "book_value")
    private BigDecimal bookValue;

    private BigDecimal beta;

    @Column(name = "computed_at")
    private Instant computedAt;

    protected Fundamentals() {
        // JPA
    }

    public Long getSymbolId() { return symbolId; }
    public BigDecimal getMarketCap() { return marketCap; }
    public BigDecimal getPeTrailing() { return peTrailing; }
    public BigDecimal getPeForward() { return peForward; }
    public BigDecimal getPb() { return pb; }
    public BigDecimal getPs() { return ps; }
    public BigDecimal getDividendYieldPct() { return dividendYieldPct; }
    public BigDecimal getRoePct() { return roePct; }
    public BigDecimal getDebtToEquity() { return debtToEquity; }
    public BigDecimal getProfitMarginPct() { return profitMarginPct; }
    public BigDecimal getOperatingMarginPct() { return operatingMarginPct; }
    public BigDecimal getRevenueGrowthPct() { return revenueGrowthPct; }
    public BigDecimal getEarningsGrowthPct() { return earningsGrowthPct; }
    public BigDecimal getEpsTrailing() { return epsTrailing; }
    public BigDecimal getBookValue() { return bookValue; }
    public BigDecimal getBeta() { return beta; }
    public Instant getComputedAt() { return computedAt; }
}
