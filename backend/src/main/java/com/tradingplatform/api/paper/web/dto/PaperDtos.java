package com.tradingplatform.api.paper.web.dto;

import com.tradingplatform.api.paper.domain.PaperOrder;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public final class PaperDtos {

    private PaperDtos() {}

    /** strategyId/stopPrice/targetPrice are optional — set when the order comes
     *  from a strategy signal (the "Trade it" flow). */
    public record OrderRequest(String ticker, String side, Integer quantity,
                               Long strategyId, BigDecimal stopPrice, BigDecimal targetPrice) {}

    public record ResetRequest(BigDecimal initialCash) {}

    public record OrderDto(Long id, String ticker, String side, Integer quantity,
                           BigDecimal price, String priceSource, BigDecimal commission,
                           BigDecimal realizedPnl, String status, String rejectReason,
                           Instant placedAt, Long strategyId, BigDecimal stopPrice,
                           BigDecimal targetPrice) {

        public static OrderDto from(PaperOrder o, String ticker) {
            return new OrderDto(o.getId(), ticker, o.getSide(), o.getQuantity(), o.getPrice(),
                    o.getPriceSource(), o.getCommission(), o.getRealizedPnl(), o.getStatus(),
                    o.getRejectReason(), o.getPlacedAt(), o.getStrategyId(), o.getStopPrice(),
                    o.getTargetPrice());
        }
    }

    public record PositionDto(String ticker, String name, Integer quantity, BigDecimal avgCost,
                              BigDecimal lastPrice, BigDecimal marketValue,
                              BigDecimal unrealizedPnl, Long strategyId, String strategyName,
                              BigDecimal stopPrice, BigDecimal targetPrice) {}

    public record AccountDto(String name, BigDecimal initialCash, BigDecimal cash,
                             BigDecimal equity, BigDecimal realizedPnl,
                             BigDecimal unrealizedPnl, List<PositionDto> positions) {}
}
