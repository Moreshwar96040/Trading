package com.tradingplatform.api.paper.repository;

import com.tradingplatform.api.paper.domain.PaperOrder;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PaperOrderRepository extends JpaRepository<PaperOrder, Long> {

    List<PaperOrder> findTop200ByAccountIdOrderByPlacedAtDesc(Long accountId);

    List<PaperOrder> findByStrategyIdIsNotNullAndStatus(String status);
}
