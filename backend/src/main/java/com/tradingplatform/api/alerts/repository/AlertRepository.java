package com.tradingplatform.api.alerts.repository;

import com.tradingplatform.api.alerts.domain.Alert;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AlertRepository extends JpaRepository<Alert, Long> {

    List<Alert> findAllByOrderByCreatedAtDesc();
}
