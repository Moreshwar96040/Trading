package com.tradingplatform.api.ai.repository;

import com.tradingplatform.api.ai.domain.AiPrediction;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AiPredictionRepository extends JpaRepository<AiPrediction, Long> {
}
