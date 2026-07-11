package com.tradingplatform.api.paper.web.dto;

import com.tradingplatform.api.paper.domain.PaperOrder;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public final class PaperDtos {

    private PaperDtos() {}

    public record OrderRequest(String ticker, String side, Integer quantity) {}

    public record ResetRequest(BigDecimal initialCash) {}

    public record OrderDto(Long id, String ticker, String side, Integer quantity,
                           BigDecimal price, String priceSource, BigDecimal commission,
                           BigDecimal realizedPnl, String status, String rejectReason,
                           Instant placedAt) {

        public static OrderDto from(PaperOrder o, String ticker) {
            return new OrderDto(o.getId(), ticker, o.getSide(), o.getQuantity(), o.getPrice(),
                    o.getPriceSource(), o.getCommission(), o.getRealizedPnl(), o.getStatus(),
                    o.getRejectReason(), o.getPlacedAt());
        }
    }

    public record PositionDto(String ticker, String name, Integer quantity, BigDecimal avgCost,
                              BigDecimal lastPrice, BigDecimal marketValue,
                              BigDecimal unrealizedPnl) {}

    public record AccountDto(String name, BigDecimal initialCash, BigDecimal cash,
                             BigDecimal equity, BigDecimal realizedPnl,
                             BigDecimal unrealizedPnl, List<PositionDto> positions) {}
}
