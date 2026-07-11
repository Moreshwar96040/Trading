package com.tradingplatform.api.marketdata.service;

import com.tradingplatform.api.common.config.AppProperties;
import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.marketdata.domain.Symbol;
import com.tradingplatform.api.marketdata.repository.OhlcvDailyRepository;
import com.tradingplatform.api.marketdata.web.dto.CandleDto;
import com.tradingplatform.api.marketdata.web.dto.CandleSeriesDto;
import java.time.LocalDate;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class CandleService {

    private final OhlcvDailyRepository candles;
    private final SymbolService symbolService;
    private final AppProperties props;

    public CandleService(OhlcvDailyRepository candles, SymbolService symbolService,
                         AppProperties props) {
        this.candles = candles;
        this.symbolService = symbolService;
        this.props = props;
    }

    /**
     * Daily candles for a ticker. Defaults: to = latest stored date (or today),
     * from = to - app.candles.default-range-days.
     */
    public CandleSeriesDto getDailyCandles(String ticker, LocalDate from, LocalDate to) {
        Symbol symbol = symbolService.getByTicker(ticker);

        LocalDate effectiveTo = (to != null) ? to
                : candles.findLatestTradeDate(symbol.getId()).orElse(LocalDate.now());
        LocalDate effectiveFrom = (from != null) ? from
                : effectiveTo.minusDays(props.candles().defaultRangeDays());

        if (effectiveFrom.isAfter(effectiveTo)) {
            throw new BadRequestException(
                    "'from' (%s) must not be after 'to' (%s)".formatted(effectiveFrom, effectiveTo));
        }
        if (effectiveFrom.plusDays(props.candles().maxRangeDays()).isBefore(effectiveTo)) {
            throw new BadRequestException(
                    "Range too large: max %d days".formatted(props.candles().maxRangeDays()));
        }

        List<CandleDto> rows = candles
                .findBySymbolIdAndTradeDateBetweenOrderByTradeDateAsc(symbol.getId(),
                        effectiveFrom, effectiveTo)
                .stream().map(CandleDto::from).toList();

        return new CandleSeriesDto(symbol.getTicker(), effectiveFrom, effectiveTo, rows);
    }
}
