package com.tradingplatform.api.fundamentals.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.LocalDate;

/** Read model: one financial-statement period (annual or quarterly). */
@Entity
@Table(name = "financial_statements")
public class FinancialStatement {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "symbol_id", nullable = false)
    private Long symbolId;

    @Column(name = "period_end", nullable = false)
    private LocalDate periodEnd;

    @Column(name = "period_type", nullable = false)
    private String periodType;

    private BigDecimal revenue;

    @Column(name = "operating_income")
    private BigDecimal operatingIncome;

    @Column(name = "net_income")
    private BigDecimal netIncome;

    private BigDecimal eps;

    @Column(name = "total_assets")
    private BigDecimal totalAssets;

    @Column(name = "total_liabilities")
    private BigDecimal totalLiabilities;

    @Column(name = "shareholders_equity")
    private BigDecimal shareholdersEquity;

    @Column(name = "operating_cash_flow")
    private BigDecimal operatingCashFlow;

    @Column(name = "free_cash_flow")
    private BigDecimal freeCashFlow;

    protected FinancialStatement() {
        // JPA
    }

    public Long getId() { return id; }
    public Long getSymbolId() { return symbolId; }
    public LocalDate getPeriodEnd() { return periodEnd; }
    public String getPeriodType() { return periodType; }
    public BigDecimal getRevenue() { return revenue; }
    public BigDecimal getOperatingIncome() { return operatingIncome; }
    public BigDecimal getNetIncome() { return netIncome; }
    public BigDecimal getEps() { return eps; }
    public BigDecimal getTotalAssets() { return totalAssets; }
    public BigDecimal getTotalLiabilities() { return totalLiabilities; }
    public BigDecimal getShareholdersEquity() { return shareholdersEquity; }
    public BigDecimal getOperatingCashFlow() { return operatingCashFlow; }
    public BigDecimal getFreeCashFlow() { return freeCashFlow; }
}
