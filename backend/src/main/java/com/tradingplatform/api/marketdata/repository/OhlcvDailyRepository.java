package com.tradingplatform.api.marketdata.repository;

import com.tradingplatform.api.marketdata.domain.OhlcvDaily;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface OhlcvDailyRepository extends JpaRepository<OhlcvDaily, Long> {

    List<OhlcvDaily> findBySymbolIdAndTradeDateBetweenOrderByTradeDateAsc(
            Long symbolId, LocalDate from, LocalDate to);

    @Query("SELECT MAX(o.tradeDate) FROM OhlcvDaily o WHERE o.symbolId = :symbolId")
    Optional<LocalDate> findLatestTradeDate(@Param("symbolId") Long symbolId);
}
