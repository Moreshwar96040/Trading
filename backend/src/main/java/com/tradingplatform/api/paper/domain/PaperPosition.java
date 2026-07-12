package com.tradingplatform.api.paper.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;

@Entity
@Table(name = "paper_positions")
public class PaperPosition {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "account_id", nullable = false)
    private Long accountId;

    @Column(name = "symbol_id", nullable = false)
    private Long symbolId;

    @Column(nullable = false)
    private Integer quantity;

    @Column(name = "avg_cost", nullable = false)
    private BigDecimal avgCost;

    @Column(name = "updated_at")
    private Instant updatedAt;

    @Column(name = "strategy_id")
    private Long strategyId;

    @Column(name = "stop_price")
    private BigDecimal stopPrice;

    @Column(name = "target_price")
    private BigDecimal targetPrice;

    protected PaperPosition() {
        // JPA
    }

    public void applyRiskPlan(Long strategyId, BigDecimal stopPrice, BigDecimal targetPrice) {
        if (strategyId != null) this.strategyId = strategyId;
        if (stopPrice != null) this.stopPrice = stopPrice;
        if (targetPrice != null) this.targetPrice = targetPrice;
    }

    /** Self-adjusting stop: only ever moves up (locks in gains, never widens risk). */
    public boolean raiseStop(BigDecimal newStop) {
        if (newStop == null || (stopPrice != null && newStop.compareTo(stopPrice) <= 0)) {
            return false;
        }
        this.stopPrice = newStop;
        return true;
    }

    private void clearRiskPlan() {
        this.strategyId = null;
        this.stopPrice = null;
        this.targetPrice = null;
    }

    public PaperPosition(Long accountId, Long symbolId) {
        this.accountId = accountId;
        this.symbolId = symbolId;
        this.quantity = 0;
        this.avgCost = BigDecimal.ZERO;
    }

    /** Weighted-average cost basis on buys. */
    public void applyBuy(int buyQty, BigDecimal price) {
        BigDecimal oldValue = avgCost.multiply(BigDecimal.valueOf(quantity));
        BigDecimal newValue = price.multiply(BigDecimal.valueOf(buyQty));
        int total = quantity + buyQty;
        this.avgCost = oldValue.add(newValue)
                .divide(BigDecimal.valueOf(total), 4, RoundingMode.HALF_UP);
        this.quantity = total;
    }

    /** Reduces quantity; avg cost unchanged. Caller validates sellQty <= quantity. */
    public void applySell(int sellQty) {
        this.quantity = this.quantity - sellQty;
        if (this.quantity == 0) {
            this.avgCost = BigDecimal.ZERO;
            clearRiskPlan();
        }
    }

    @PrePersist
    @PreUpdate
    void touch() {
        updatedAt = Instant.now();
    }

    public Long getId() { return id; }
    public Long getAccountId() { return accountId; }
    public Long getSymbolId() { return symbolId; }
    public Integer getQuantity() { return quantity; }
    public BigDecimal getAvgCost() { return avgCost; }
    public Instant getUpdatedAt() { return updatedAt; }
    public Long getStrategyId() { return strategyId; }
    public BigDecimal getStopPrice() { return stopPrice; }
    public BigDecimal getTargetPrice() { return targetPrice; }
}
