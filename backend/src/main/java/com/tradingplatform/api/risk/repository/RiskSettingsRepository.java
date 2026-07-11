package com.tradingplatform.api.risk.repository;

import com.tradingplatform.api.risk.domain.RiskSettings;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RiskSettingsRepository extends JpaRepository<RiskSettings, Long> {
}
