package com.tradingplatform.api.strategy.repository;

import com.tradingplatform.api.strategy.domain.StrategySignal;
import com.tradingplatform.api.strategy.web.dto.SignalDto;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface StrategySignalRepository extends JpaRepository<StrategySignal, Long> {

    @Query("""
            select new com.tradingplatform.api.strategy.web.dto.SignalDto(
                sig.id, st.id, st.name, sy.ticker, sy.name, sig.signal,
                sig.asOfDate, sig.close, sig.evaluatedAt)
            from StrategySignal sig
            join com.tradingplatform.api.strategy.domain.Strategy st on st.id = sig.strategyId
            join com.tradingplatform.api.marketdata.domain.Symbol sy on sy.id = sig.symbolId
            order by sig.asOfDate desc, st.name asc, sy.ticker asc
            """)
    List<SignalDto> findAllForDisplay();
}
