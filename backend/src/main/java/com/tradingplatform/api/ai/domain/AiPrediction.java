package com.tradingplatform.api.ai.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

/** Read model — predictions are written by the Python AI engine. */
@Entity
@Table(name = "ai_predictions")
public class AiPrediction {

    @Id
    @Column(name = "symbol_id")
    private Long symbolId;

    @Column(name = "as_of_date", nullable = false)
    private LocalDate asOfDate;

    @Column(name = "predicted_return_pct", nullable = false)
    private BigDecimal predictedReturnPct;

    @Column(nullable = false)
    private String direction;

    @Column(name = "test_direction_accuracy")
    private BigDecimal testDirectionAccuracy;

    @Column(name = "test_mae_pct")
    private BigDecimal testMaePct;

    @Column(name = "train_rows")
    private Integer trainRows;

    @Column(name = "model_name")
    private String modelName;

    @Column(name = "trained_at")
    private Instant trainedAt;

    protected AiPrediction() {
        // JPA
    }

    public Long getSymbolId() { return symbolId; }
    public LocalDate getAsOfDate() { return asOfDate; }
    public BigDecimal getPredictedReturnPct() { return predictedReturnPct; }
    public String getDirection() { return direction; }
    public BigDecimal getTestDirectionAccuracy() { return testDirectionAccuracy; }
    public BigDecimal getTestMaePct() { return testMaePct; }
    public Integer getTrainRows() { return trainRows; }
    public String getModelName() { return modelName; }
    public Instant getTrainedAt() { return trainedAt; }
}
