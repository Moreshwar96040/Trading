package com.tradingplatform.api.strategy.repository;

import com.tradingplatform.api.strategy.domain.Backtest;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BacktestRepository extends JpaRepository<Backtest, Long> {

    List<Backtest> findByStrategyIdOrderByStartedAtDesc(Long strategyId);
}
