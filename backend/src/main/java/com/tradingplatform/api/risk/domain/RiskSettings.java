package com.tradingplatform.api.risk.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;

/** Single seeded row (id=1) — the platform's risk limits. */
@Entity
@Table(name = "risk_settings")
public class RiskSettings {

    @Id
    private Long id;

    @Column(name = "max_position_pct", nullable = false)
    private BigDecimal maxPositionPct;

    @Column(name = "max_sector_pct", nullable = false)
    private BigDecimal maxSectorPct;

    @Column(name = "risk_per_trade_pct", nullable = false)
    private BigDecimal riskPerTradePct;

    @Column(name = "block_on_breach", nullable = false)
    private boolean blockOnBreach;

    @Column(name = "updated_at")
    private Instant updatedAt;

    protected RiskSettings() {
        // JPA
    }

    public void update(BigDecimal maxPositionPct, BigDecimal maxSectorPct,
                       BigDecimal riskPerTradePct, boolean blockOnBreach) {
        this.maxPositionPct = maxPositionPct;
        this.maxSectorPct = maxSectorPct;
        this.riskPerTradePct = riskPerTradePct;
        this.blockOnBreach = blockOnBreach;
    }

    @PreUpdate
    void touch() {
        updatedAt = Instant.now();
    }

    public Long getId() { return id; }
    public BigDecimal getMaxPositionPct() { return maxPositionPct; }
    public BigDecimal getMaxSectorPct() { return maxSectorPct; }
    public BigDecimal getRiskPerTradePct() { return riskPerTradePct; }
    public boolean isBlockOnBreach() { return blockOnBreach; }
    public Instant getUpdatedAt() { return updatedAt; }
}
