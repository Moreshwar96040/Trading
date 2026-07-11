package com.tradingplatform.api.paper.service;

import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import com.tradingplatform.api.marketdata.domain.OhlcvDaily;
import com.tradingplatform.api.marketdata.domain.Symbol;
import com.tradingplatform.api.marketdata.repository.OhlcvDailyRepository;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Reference price for paper fills: live delayed quote when Yahoo is reachable,
 * otherwise the latest stored close. Paper trading works fully offline on EOD data.
 */
@Service
public class PriceService {

    private static final Logger log = LoggerFactory.getLogger(PriceService.class);

    public record ReferencePrice(BigDecimal price, String source) {}

    private final MarketDataServiceClient marketData;
    private final OhlcvDailyRepository candles;

    public PriceService(MarketDataServiceClient marketData, OhlcvDailyRepository candles) {
        this.marketData = marketData;
        this.candles = candles;
    }

    public ReferencePrice getReferencePrice(Symbol symbol) {
        try {
            var quote = marketData.getQuote(symbol.getTicker());
            if (quote != null && quote.price() != null && quote.price().signum() > 0) {
                return new ReferencePrice(quote.price(), "QUOTE");
            }
        } catch (Exception ex) {
            log.warn("Quote unavailable for {} — falling back to last close ({})",
                    symbol.getTicker(), ex.getMessage());
        }

        LocalDate latest = candles.findLatestTradeDate(symbol.getId())
                .orElseThrow(() -> new BadRequestException(
                        "No price data for " + symbol.getTicker() + " — run the data sync first"));
        List<OhlcvDaily> rows = candles.findBySymbolIdAndTradeDateBetweenOrderByTradeDateAsc(
                symbol.getId(), latest, latest);
        return new ReferencePrice(rows.get(rows.size() - 1).getClose(), "CLOSE");
    }
}
