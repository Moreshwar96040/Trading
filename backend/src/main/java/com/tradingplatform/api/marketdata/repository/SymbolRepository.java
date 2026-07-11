package com.tradingplatform.api.marketdata.repository;

import com.tradingplatform.api.marketdata.domain.Symbol;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface SymbolRepository extends JpaRepository<Symbol, Long> {

    Optional<Symbol> findByTickerIgnoreCaseAndActiveTrue(String ticker);

    List<Symbol> findByActiveTrueOrderByTickerAsc();

    @Query("""
            SELECT s FROM Symbol s
            WHERE s.active = true
              AND (UPPER(s.ticker) LIKE UPPER(CONCAT('%', :q, '%'))
                   OR UPPER(s.name) LIKE UPPER(CONCAT('%', :q, '%')))
            ORDER BY s.ticker
            """)
    List<Symbol> search(@Param("q") String query);
}
