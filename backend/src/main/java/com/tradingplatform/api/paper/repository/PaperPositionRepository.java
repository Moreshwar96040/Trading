package com.tradingplatform.api.paper.repository;

import com.tradingplatform.api.paper.domain.PaperPosition;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PaperPositionRepository extends JpaRepository<PaperPosition, Long> {

    Optional<PaperPosition> findByAccountIdAndSymbolId(Long accountId, Long symbolId);

    List<PaperPosition> findByAccountIdAndQuantityGreaterThan(Long accountId, Integer quantity);
}
