package com.tradingplatform.api.paper.repository;

import com.tradingplatform.api.paper.domain.PaperAccount;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PaperAccountRepository extends JpaRepository<PaperAccount, Long> {
}
