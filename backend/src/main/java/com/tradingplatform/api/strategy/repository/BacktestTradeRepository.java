package com.tradingplatform.api.strategy.repository;

import com.tradingplatform.api.strategy.domain.BacktestTrade;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BacktestTradeRepository extends JpaRepository<BacktestTrade, Long> {

    List<BacktestTrade> findByBacktestIdOrderByEntryDateAsc(Long backtestId);
}
