package com.tradingplatform.api.alerts.service;

import com.tradingplatform.api.alerts.domain.Alert;
import com.tradingplatform.api.alerts.repository.AlertRepository;
import com.tradingplatform.api.alerts.web.dto.AlertDtos.AlertDto;
import com.tradingplatform.api.alerts.web.dto.AlertDtos.AlertRequest;
import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.common.error.NotFoundException;
import com.tradingplatform.api.marketdata.domain.Symbol;
import com.tradingplatform.api.marketdata.service.SymbolService;
import com.tradingplatform.api.screener.service.ScreenerFields;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AlertService {

    private final AlertRepository alerts;
    private final SymbolService symbolService;

    public AlertService(AlertRepository alerts, SymbolService symbolService) {
        this.alerts = alerts;
        this.symbolService = symbolService;
    }

    @Transactional
    public AlertDto create(AlertRequest request) {
        if (request.field() == null || !ScreenerFields.isNumeric(request.field())) {
            throw new BadRequestException("Unknown alert field: " + request.field());
        }
        if (request.op() == null || !ScreenerFields.OPS.contains(request.op())) {
            throw new BadRequestException("Unknown operator: " + request.op());
        }
        if (request.value() == null) {
            throw new BadRequestException("value is required");
        }
        Symbol symbol = symbolService.getByTicker(request.ticker());
        Alert saved = alerts.save(new Alert(symbol.getId(), request.field(), request.op(),
                request.value(), request.note()));
        return AlertDto.from(saved, symbol.getTicker());
    }

    @Transactional(readOnly = true)
    public List<AlertDto> list() {
        Map<Long, String> tickers = new HashMap<>();
        return alerts.findAllByOrderByCreatedAtDesc().stream()
                .map(a -> AlertDto.from(a, tickers.computeIfAbsent(a.getSymbolId(),
                        id -> symbolService.getById(id).getTicker())))
                .toList();
    }

    @Transactional
    public AlertDto rearm(Long id) {
        Alert alert = alerts.findById(id)
                .orElseThrow(() -> new NotFoundException("Unknown alert: " + id));
        alert.rearm();
        return AlertDto.from(alerts.save(alert), symbolService.getById(alert.getSymbolId()).getTicker());
    }

    @Transactional
    public void delete(Long id) {
        if (!alerts.existsById(id)) {
            throw new NotFoundException("Unknown alert: " + id);
        }
        alerts.deleteById(id);
    }
}
