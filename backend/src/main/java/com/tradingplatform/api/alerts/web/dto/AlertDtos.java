package com.tradingplatform.api.alerts.web.dto;

import com.tradingplatform.api.alerts.domain.Alert;
import java.math.BigDecimal;
import java.time.Instant;

public final class AlertDtos {

    private AlertDtos() {}

    public record AlertRequest(String ticker, String field, String op, BigDecimal value,
                               String note) {}

    public record AlertDto(Long id, String ticker, String field, String op, BigDecimal value,
                           String note, String status, Instant createdAt, Instant triggeredAt,
                           BigDecimal triggeredValue) {

        public static AlertDto from(Alert a, String ticker) {
            return new AlertDto(a.getId(), ticker, a.getField(), a.getOp(), a.getValue(),
                    a.getNote(), a.getStatus(), a.getCreatedAt(), a.getTriggeredAt(),
                    a.getTriggeredValue());
        }
    }
}
