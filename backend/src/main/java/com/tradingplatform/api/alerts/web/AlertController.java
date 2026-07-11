package com.tradingplatform.api.alerts.web;

import com.tradingplatform.api.alerts.service.AlertService;
import com.tradingplatform.api.alerts.web.dto.AlertDtos.AlertDto;
import com.tradingplatform.api.alerts.web.dto.AlertDtos.AlertRequest;
import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/alerts")
public class AlertController {

    private final AlertService alertService;
    private final MarketDataServiceClient marketData;

    public AlertController(AlertService alertService, MarketDataServiceClient marketData) {
        this.alertService = alertService;
        this.marketData = marketData;
    }

    @GetMapping
    public List<AlertDto> list() {
        return alertService.list();
    }

    /** body: {"ticker":"TCS","field":"rsi_14","op":"lt","value":30,"note":"oversold"} */
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public AlertDto create(@RequestBody AlertRequest request) {
        return alertService.create(request);
    }

    @PostMapping("/{id}/rearm")
    public AlertDto rearm(@PathVariable Long id) {
        return alertService.rearm(id);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable Long id) {
        alertService.delete(id);
    }

    /** Evaluate all ACTIVE alerts now (also runs automatically after each daily sync). */
    @PostMapping("/evaluate")
    public Map<String, Object> evaluate() {
        return marketData.evaluateAlerts();
    }
}
