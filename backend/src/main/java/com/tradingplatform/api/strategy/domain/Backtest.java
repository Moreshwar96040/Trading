package com.tradingplatform.api.strategy.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;

/** Read model — backtest runs are written by the Python service. */
@Entity
@Table(name = "backtests")
public class Backtest {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "strategy_id", nullable = false)
    private Long strategyId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private String params;

    @Column(nullable = false)
    private String status;

    @Column(name = "started_at")
    private Instant startedAt;

    @Column(name = "finished_at")
    private Instant finishedAt;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private String metrics;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "equity_curve", columnDefinition = "jsonb")
    private String equityCurve;

    private String error;

    protected Backtest() {
        // JPA
    }

    public Long getId() { return id; }
    public Long getStrategyId() { return strategyId; }
    public String getParams() { return params; }
    public String getStatus() { return status; }
    public Instant getStartedAt() { return startedAt; }
    public Instant getFinishedAt() { return finishedAt; }
    public String getMetrics() { return metrics; }
    public String getEquityCurve() { return equityCurve; }
    public String getError() { return error; }
}
