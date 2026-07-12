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
@Table(name = "paper_orders")
public class PaperOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "account_id", nullable = false)
    private Long accountId;

    @Column(name = "symbol_id", nullable = false)
    private Long symbolId;

    @Column(nullable = false)
    private String side;

    @Column(nullable = false)
    private Integer quantity;

    private BigDecimal price;

    @Column(name = "price_source")
    private String priceSource;

    private BigDecimal commission;

    @Column(name = "realized_pnl")
    private BigDecimal realizedPnl;

    @Column(nullable = false)
    private String status;

    @Column(name = "reject_reason")
    private String rejectReason;

    @Column(name = "placed_at")
    private Instant placedAt;

    @Column(name = "strategy_id")
    private Long strategyId;

    @Column(name = "stop_price")
    private BigDecimal stopPrice;

    @Column(name = "target_price")
    private BigDecimal targetPrice;

    protected PaperOrder() {
        // JPA
    }

    public void attachRiskPlan(Long strategyId, BigDecimal stopPrice, BigDecimal targetPrice) {
        this.strategyId = strategyId;
        this.stopPrice = stopPrice;
        this.targetPrice = targetPrice;
    }

    private PaperOrder(Long accountId, Long symbolId, String side, Integer quantity) {
        this.accountId = accountId;
        this.symbolId = symbolId;
        this.side = side;
        this.quantity = quantity;
        this.placedAt = Instant.now();
    }

    public static PaperOrder filled(Long accountId, Long symbolId, String side, int quantity,
                                    BigDecimal price, String priceSource, BigDecimal commission,
                                    BigDecimal realizedPnl) {
        PaperOrder order = new PaperOrder(accountId, symbolId, side, quantity);
        order.price = price;
        order.priceSource = priceSource;
        order.commission = commission;
        order.realizedPnl = realizedPnl;
        order.status = "FILLED";
        return order;
    }

    public static PaperOrder rejected(Long accountId, Long symbolId, String side, int quantity,
                                      String reason) {
        PaperOrder order = new PaperOrder(accountId, symbolId, side, quantity);
        order.status = "REJECTED";
        order.rejectReason = reason;
        return order;
    }

    public Long getId() { return id; }
    public Long getAccountId() { return accountId; }
    public Long getSymbolId() { return symbolId; }
    public String getSide() { return side; }
    public Integer getQuantity() { return quantity; }
    public BigDecimal getPrice() { return price; }
    public String getPriceSource() { return priceSource; }
    public BigDecimal getCommission() { return commission; }
    public BigDecimal getRealizedPnl() { return realizedPnl; }
    public String getStatus() { return status; }
    public String getRejectReason() { return rejectReason; }
    public Instant getPlacedAt() { return placedAt; }
    public Long getStrategyId() { return strategyId; }
    public BigDecimal getStopPrice() { return stopPrice; }
    public BigDecimal getTargetPrice() { return targetPrice; }
}
