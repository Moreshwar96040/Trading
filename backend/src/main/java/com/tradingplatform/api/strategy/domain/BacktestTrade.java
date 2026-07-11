package com.tradingplatform.api.strategy.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.LocalDate;

/** Read model — trades are written by the Python service. */
@Entity
@Table(name = "backtest_trades")
public class BacktestTrade {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "backtest_id", nullable = false)
    private Long backtestId;

    @Column(nullable = false)
    private String ticker;

    @Column(name = "entry_date", nullable = false)
    private LocalDate entryDate;

    @Column(name = "entry_price", nullable = false)
    private BigDecimal entryPrice;

    @Column(name = "exit_date")
    private LocalDate exitDate;

    @Column(name = "exit_price")
    private BigDecimal exitPrice;

    @Column(nullable = false)
    private Integer quantity;

    private BigDecimal pnl;

    @Column(name = "pnl_pct")
    private BigDecimal pnlPct;

    @Column(name = "exit_reason")
    private String exitReason;

    protected BacktestTrade() {
        // JPA
    }

    public Long getId() { return id; }
    public Long getBacktestId() { return backtestId; }
    public String getTicker() { return ticker; }
    public LocalDate getEntryDate() { return entryDate; }
    public BigDecimal getEntryPrice() { return entryPrice; }
    public LocalDate getExitDate() { return exitDate; }
    public BigDecimal getExitPrice() { return exitPrice; }
    public Integer getQuantity() { return quantity; }
    public BigDecimal getPnl() { return pnl; }
    public BigDecimal getPnlPct() { return pnlPct; }
    public String getExitReason() { return exitReason; }
}
