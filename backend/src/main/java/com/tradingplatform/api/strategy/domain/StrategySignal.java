package com.tradingplatform.api.strategy.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

/** Live strategy signal. Python owns all writes; this entity is read-only. */
@Entity
@Table(name = "strategy_signals")
public class StrategySignal {

    @Id
    private Long id;

    @Column(name = "strategy_id", nullable = false)
    private Long strategyId;

    @Column(name = "symbol_id", nullable = false)
    private Long symbolId;

    @Column(nullable = false)
    private String signal;

    @Column(name = "as_of_date", nullable = false)
    private LocalDate asOfDate;

    private BigDecimal close;

    @Column(name = "evaluated_at")
    private Instant evaluatedAt;

    protected StrategySignal() {
        // JPA
    }

    public Long getId() { return id; }
    public Long getStrategyId() { return strategyId; }
    public Long getSymbolId() { return symbolId; }
    public String getSignal() { return signal; }
    public LocalDate getAsOfDate() { return asOfDate; }
    public BigDecimal getClose() { return close; }
    public Instant getEvaluatedAt() { return evaluatedAt; }
}
