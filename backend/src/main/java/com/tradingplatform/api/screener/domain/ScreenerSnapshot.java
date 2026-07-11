package com.tradingplatform.api.screener.domain;

import com.tradingplatform.api.marketdata.domain.Symbol;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.LocalDate;

/** Read model: latest indicator values per symbol (written by the Python service). */
@Entity
@Table(name = "screener_snapshot")
public class ScreenerSnapshot {

    @Id
    @Column(name = "symbol_id")
    private Long symbolId;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "symbol_id", insertable = false, updatable = false)
    private Symbol symbol;

    @Column(name = "as_of_date", nullable = false)
    private LocalDate asOfDate;

    @Column(nullable = false)
    private BigDecimal close;

    @Column(name = "change_1d_pct")
    private BigDecimal change1dPct;

    private Long volume;

    @Column(name = "avg_volume_20")
    private BigDecimal avgVolume20;

    @Column(name = "volume_ratio")
    private BigDecimal volumeRatio;

    @Column(name = "sma_20")
    private BigDecimal sma20;

    @Column(name = "sma_50")
    private BigDecimal sma50;

    @Column(name = "sma_200")
    private BigDecimal sma200;

    @Column(name = "ema_20")
    private BigDecimal ema20;

    @Column(name = "rsi_14")
    private BigDecimal rsi14;

    private BigDecimal macd;

    @Column(name = "macd_signal")
    private BigDecimal macdSignal;

    @Column(name = "macd_hist")
    private BigDecimal macdHist;

    @Column(name = "bb_upper")
    private BigDecimal bbUpper;

    @Column(name = "bb_lower")
    private BigDecimal bbLower;

    @Column(name = "atr_14")
    private BigDecimal atr14;

    @Column(name = "high_52w")
    private BigDecimal high52w;

    @Column(name = "low_52w")
    private BigDecimal low52w;

    @Column(name = "pct_from_52w_high")
    private BigDecimal pctFrom52wHigh;

    @Column(name = "pct_from_52w_low")
    private BigDecimal pctFrom52wLow;

    @Column(name = "return_1m_pct")
    private BigDecimal return1mPct;

    @Column(name = "return_3m_pct")
    private BigDecimal return3mPct;

    @Column(name = "return_1y_pct")
    private BigDecimal return1yPct;

    // --- fundamentals, denormalized by the Python snapshot refresher (V4) ---

    @Column(name = "market_cap")
    private BigDecimal marketCap;

    @Column(name = "pe_trailing")
    private BigDecimal peTrailing;

    private BigDecimal pb;

    @Column(name = "dividend_yield_pct")
    private BigDecimal dividendYieldPct;

    @Column(name = "roe_pct")
    private BigDecimal roePct;

    @Column(name = "debt_to_equity")
    private BigDecimal debtToEquity;

    @Column(name = "profit_margin_pct")
    private BigDecimal profitMarginPct;

    @Column(name = "revenue_growth_pct")
    private BigDecimal revenueGrowthPct;

    protected ScreenerSnapshot() {
        // JPA
    }

    public Long getSymbolId() { return symbolId; }
    public Symbol getSymbol() { return symbol; }
    public LocalDate getAsOfDate() { return asOfDate; }
    public BigDecimal getClose() { return close; }
    public BigDecimal getChange1dPct() { return change1dPct; }
    public Long getVolume() { return volume; }
    public BigDecimal getAvgVolume20() { return avgVolume20; }
    public BigDecimal getVolumeRatio() { return volumeRatio; }
    public BigDecimal getSma20() { return sma20; }
    public BigDecimal getSma50() { return sma50; }
    public BigDecimal getSma200() { return sma200; }
    public BigDecimal getEma20() { return ema20; }
    public BigDecimal getRsi14() { return rsi14; }
    public BigDecimal getMacd() { return macd; }
    public BigDecimal getMacdSignal() { return macdSignal; }
    public BigDecimal getMacdHist() { return macdHist; }
    public BigDecimal getBbUpper() { return bbUpper; }
    public BigDecimal getBbLower() { return bbLower; }
    public BigDecimal getAtr14() { return atr14; }
    public BigDecimal getHigh52w() { return high52w; }
    public BigDecimal getLow52w() { return low52w; }
    public BigDecimal getPctFrom52wHigh() { return pctFrom52wHigh; }
    public BigDecimal getPctFrom52wLow() { return pctFrom52wLow; }
    public BigDecimal getReturn1mPct() { return return1mPct; }
    public BigDecimal getReturn3mPct() { return return3mPct; }
    public BigDecimal getReturn1yPct() { return return1yPct; }
    public BigDecimal getMarketCap() { return marketCap; }
    public BigDecimal getPeTrailing() { return peTrailing; }
    public BigDecimal getPb() { return pb; }
    public BigDecimal getDividendYieldPct() { return dividendYieldPct; }
    public BigDecimal getRoePct() { return roePct; }
    public BigDecimal getDebtToEquity() { return debtToEquity; }
    public BigDecimal getProfitMarginPct() { return profitMarginPct; }
    public BigDecimal getRevenueGrowthPct() { return revenueGrowthPct; }
}
