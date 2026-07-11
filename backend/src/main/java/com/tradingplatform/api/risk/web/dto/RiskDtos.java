package com.tradingplatform.api.risk.web.dto;

import java.math.BigDecimal;
import java.util.List;

public final class RiskDtos {

    private RiskDtos() {}

    public record SettingsDto(BigDecimal maxPositionPct, BigDecimal maxSectorPct,
                              BigDecimal riskPerTradePct, boolean blockOnBreach) {}

    public record PositionSizeRequest(BigDecimal entryPrice, BigDecimal stopPrice,
                                      BigDecimal equityOverride) {}

    public record PositionSizeResult(int quantity, BigDecimal riskAmount,
                                     BigDecimal perShareRisk, BigDecimal positionValue,
                                     boolean cappedByPositionLimit) {}

    public record RiskReport(BigDecimal equity, BigDecimal cash, BigDecimal cashPct,
                             List<Exposure> positions, List<Exposure> sectors,
                             List<String> breaches, BigDecimal maxPositionPct,
                             BigDecimal maxSectorPct) {

        public record Exposure(String name, BigDecimal value, BigDecimal pct) {}
    }
}
