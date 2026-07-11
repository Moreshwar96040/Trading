package com.tradingplatform.api.marketdata.web.dto;

import com.tradingplatform.api.marketdata.domain.OhlcvDaily;
import java.math.BigDecimal;
import java.time.LocalDate;

/** Shaped for TradingView lightweight-charts: `time` is an ISO yyyy-MM-dd date. */
public record CandleDto(LocalDate time, BigDecimal open, BigDecimal high, BigDecimal low,
                        BigDecimal close, BigDecimal adjClose, Long volume) {

    public static CandleDto from(OhlcvDaily o) {
        return new CandleDto(o.getTradeDate(), o.getOpen(), o.getHigh(), o.getLow(),
                o.getClose(), o.getAdjClose(), o.getVolume());
    }
}
