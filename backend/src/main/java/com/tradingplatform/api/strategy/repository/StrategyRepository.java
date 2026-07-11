package com.tradingplatform.api.strategy.repository;

import com.tradingplatform.api.strategy.domain.Strategy;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface StrategyRepository extends JpaRepository<Strategy, Long> {

    Optional<Strategy> findByNameIgnoreCase(String name);
}
