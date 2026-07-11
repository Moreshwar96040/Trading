package com.tradingplatform.api.alerts.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Alert definition (Spring-owned columns). Lifecycle columns (status transitions to
 * TRIGGERED, triggered_at/value) are written by the Python evaluator — re-arm here
 * only resets them.
 */
@Entity
@Table(name = "alerts")
public class Alert {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "symbol_id", nullable = false)
    private Long symbolId;

    @Column(nullable = false)
    private String field;

    @Column(nullable = false)
    private String op;

    @Column(nullable = false)
    private BigDecimal value;

    private String note;

    @Column(nullable = false)
    private String status;

    @Column(name = "created_at")
    private Instant createdAt;

    @Column(name = "triggered_at")
    private Instant triggeredAt;

    @Column(name = "triggered_value")
    private BigDecimal triggeredValue;

    protected Alert() {
        // JPA
    }

    public Alert(Long symbolId, String field, String op, BigDecimal value, String note) {
        this.symbolId = symbolId;
        this.field = field;
        this.op = op;
        this.value = value;
        this.note = note;
        this.status = "ACTIVE";
        this.createdAt = Instant.now();
    }

    public void rearm() {
        this.status = "ACTIVE";
        this.triggeredAt = null;
        this.triggeredValue = null;
    }

    public Long getId() { return id; }
    public Long getSymbolId() { return symbolId; }
    public String getField() { return field; }
    public String getOp() { return op; }
    public BigDecimal getValue() { return value; }
    public String getNote() { return note; }
    public String getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getTriggeredAt() { return triggeredAt; }
    public BigDecimal getTriggeredValue() { return triggeredValue; }
}
