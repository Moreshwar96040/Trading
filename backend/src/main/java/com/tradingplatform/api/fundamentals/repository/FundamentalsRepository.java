package com.tradingplatform.api.fundamentals.repository;

import com.tradingplatform.api.fundamentals.domain.Fundamentals;
import org.springframework.data.jpa.repository.JpaRepository;

public interface FundamentalsRepository extends JpaRepository<Fundamentals, Long> {
}
