package com.tradingplatform.api.marketdata.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.LocalDate;

/** Read model for daily candles (written by the Python ingestion service). */
@Entity
@Table(name = "ohlcv_daily")
public class OhlcvDaily {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "symbol_id", nullable = false)
    private Long symbolId;

    @Column(name = "trade_date", nullable = false)
    private LocalDate tradeDate;

    @Column(nullable = false)
    private BigDecimal open;

    @Column(nullable = false)
    private BigDecimal high;

    @Column(nullable = false)
    private BigDecimal low;

    @Column(nullable = false)
    private BigDecimal close;

    @Column(name = "adj_close")
    private BigDecimal adjClose;

    @Column(nullable = false)
    private Long volume;

    protected OhlcvDaily() {
        // JPA
    }

    public Long getId() { return id; }
    public Long getSymbolId() { return symbolId; }
    public LocalDate getTradeDate() { return tradeDate; }
    public BigDecimal getOpen() { return open; }
    public BigDecimal getHigh() { return high; }
    public BigDecimal getLow() { return low; }
    public BigDecimal getClose() { return close; }
    public BigDecimal getAdjClose() { return adjClose; }
    public Long getVolume() { return volume; }
}
