package com.tradingplatform.api.fundamentals.repository;

import com.tradingplatform.api.fundamentals.domain.FinancialStatement;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface FinancialStatementRepository extends JpaRepository<FinancialStatement, Long> {

    List<FinancialStatement> findBySymbolIdAndPeriodTypeOrderByPeriodEndDesc(
            Long symbolId, String periodType);
}
