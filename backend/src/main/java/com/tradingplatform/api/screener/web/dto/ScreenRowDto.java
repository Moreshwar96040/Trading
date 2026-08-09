package com.tradingplatform.api.screener.web.dto;

import com.tradingplatform.api.screener.domain.ScreenerSnapshot;
import java.math.BigDecimal;
import java.time.LocalDate;

public record ScreenRowDto(String ticker, String name, String sector, LocalDate asOfDate,
                           BigDecimal close, BigDecimal change1dPct, BigDecimal volumeRatio,
                           BigDecimal rsi14, BigDecimal sma50, BigDecimal sma200,
                           BigDecimal pctFrom52wHigh, BigDecimal return1mPct,
                           BigDecimal return3mPct, BigDecimal return1yPct,
                           // Ichimoku: shown so a cloud-breakout screen is readable
                           // at a glance without opening each chart.
                           BigDecimal tkCrossAgeDays, BigDecimal pctAboveCloud,
                           BigDecimal ichimokuBullish,
                           // Major swing support: level + % distance above it.
                           BigDecimal support, BigDecimal pctFromSupport) {

    public static ScreenRowDto from(ScreenerSnapshot s) {
        return new ScreenRowDto(s.getSymbol().getTicker(), s.getSymbol().getName(),
                s.getSymbol().getSector(), s.getAsOfDate(), s.getClose(), s.getChange1dPct(),
                s.getVolumeRatio(), s.getRsi14(), s.getSma50(), s.getSma200(),
                s.getPctFrom52wHigh(), s.getReturn1mPct(), s.getReturn3mPct(),
                s.getReturn1yPct(), s.getTkCrossAgeDays(), s.getPctAboveCloud(),
                s.getIchimokuBullish(), s.getSupport(), s.getPctFromSupport());
    }
}
