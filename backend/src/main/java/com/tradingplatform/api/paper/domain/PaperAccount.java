package com.tradingplatform.api.paper.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "paper_accounts")
public class PaperAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(name = "initial_cash", nullable = false)
    private BigDecimal initialCash;

    @Column(nullable = false)
    private BigDecimal cash;

    @Column(name = "realized_pnl", nullable = false)
    private BigDecimal realizedPnl;

    @Column(name = "created_at")
    private Instant createdAt;

    protected PaperAccount() {
        // JPA
    }

    public void debitCash(BigDecimal amount) {
        this.cash = this.cash.subtract(amount);
    }

    public void creditCash(BigDecimal amount) {
        this.cash = this.cash.add(amount);
    }

    public void addRealizedPnl(BigDecimal amount) {
        this.realizedPnl = this.realizedPnl.add(amount);
    }

    public void reset(BigDecimal newInitialCash) {
        this.initialCash = newInitialCash;
        this.cash = newInitialCash;
        this.realizedPnl = BigDecimal.ZERO;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getInitialCash() { return initialCash; }
    public BigDecimal getCash() { return cash; }
    public BigDecimal getRealizedPnl() { return realizedPnl; }
    public Instant getCreatedAt() { return createdAt; }
}
