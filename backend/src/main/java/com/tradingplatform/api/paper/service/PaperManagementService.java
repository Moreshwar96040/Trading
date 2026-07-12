package com.tradingplatform.api.paper.service;

import com.tradingplatform.api.alerts.domain.Alert;
import com.tradingplatform.api.alerts.repository.AlertRepository;
import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import com.tradingplatform.api.marketdata.domain.Symbol;
import com.tradingplatform.api.marketdata.service.SymbolService;
import com.tradingplatform.api.paper.domain.PaperPosition;
import com.tradingplatform.api.paper.repository.PaperPositionRepository;
import com.tradingplatform.api.paper.web.dto.PaperDtos.OrderRequest;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Applies the adaptive-risk engine to live paper positions (Phase C of the loop):
 * ratchets trailing stops upward, and when price has crossed a stop or target,
 * either raises an in-app alert or (opt-in) exits the position automatically.
 */
@Service
public class PaperManagementService {

    private static final Logger log = LoggerFactory.getLogger(PaperManagementService.class);

    public record ManageAction(String ticker, String action, String detail) {}
    public record ManageResult(int positionsChecked, boolean autoExit, List<ManageAction> actions) {}

    private final PaperPositionRepository positions;
    private final PaperTradingService paperTrading;
    private final SymbolService symbolService;
    private final PriceService priceService;
    private final MarketDataServiceClient marketData;
    private final AlertRepository alerts;

    public PaperManagementService(PaperPositionRepository positions,
                                  PaperTradingService paperTrading, SymbolService symbolService,
                                  PriceService priceService, MarketDataServiceClient marketData,
                                  AlertRepository alerts) {
        this.positions = positions;
        this.paperTrading = paperTrading;
        this.symbolService = symbolService;
        this.priceService = priceService;
        this.marketData = marketData;
        this.alerts = alerts;
    }

    @Transactional
    public ManageResult manage(boolean autoExit) {
        List<PaperPosition> open = positions.findByAccountIdAndQuantityGreaterThan(
                PaperTradingService.DEFAULT_ACCOUNT_ID, 0);
        List<ManageAction> actions = new ArrayList<>();

        for (PaperPosition position : open) {
            Symbol symbol = symbolService.getById(position.getSymbolId());
            try {
                managePosition(position, symbol, autoExit, actions);
            } catch (Exception ex) {
                log.warn("Position management skipped for {}: {}", symbol.getTicker(), ex.getMessage());
                actions.add(new ManageAction(symbol.getTicker(), "SKIPPED", ex.getMessage()));
            }
        }
        return new ManageResult(open.size(), autoExit, actions);
    }

    private void managePosition(PaperPosition position, Symbol symbol, boolean autoExit,
                                List<ManageAction> actions) {
        String ticker = symbol.getTicker();
        BigDecimal price = priceService.getReferencePrice(symbol).price();
        Map<String, Object> risk = marketData.getAiRisk(ticker, null);
        BigDecimal suggestedStop = decimal(risk.get("stop_price"));
        BigDecimal suggestedTarget = decimal(risk.get("take_profit_price"));
        boolean trail = Boolean.TRUE.equals(risk.get("trail"));

        if (position.getStopPrice() == null) {
            position.applyRiskPlan(null, suggestedStop, suggestedTarget);
            positions.save(position);
            actions.add(new ManageAction(ticker, "PLAN_SET",
                    "Stop ₹%s%s (%s)".formatted(suggestedStop,
                            suggestedTarget != null ? ", target ₹" + suggestedTarget : ", trailing",
                            risk.get("regime"))));
        } else if (trail && position.raiseStop(suggestedStop)) {
            positions.save(position);
            actions.add(new ManageAction(ticker, "STOP_RAISED",
                    "Trailing stop ratcheted up to ₹" + suggestedStop));
        }

        BigDecimal stop = position.getStopPrice();
        BigDecimal target = position.getTargetPrice();
        if (stop != null && price.compareTo(stop) <= 0) {
            exitOrAlert(position, symbol, autoExit, actions, "STOP",
                    "Price ₹%s at/below stop ₹%s".formatted(price, stop), stop);
        } else if (target != null && price.compareTo(target) >= 0) {
            exitOrAlert(position, symbol, autoExit, actions, "TARGET",
                    "Price ₹%s at/above target ₹%s — book profit".formatted(price, target), target);
        }
    }

    private void exitOrAlert(PaperPosition position, Symbol symbol, boolean autoExit,
                             List<ManageAction> actions, String kind, String detail,
                             BigDecimal level) {
        String ticker = symbol.getTicker();
        if (autoExit) {
            var order = paperTrading.placeOrder(new OrderRequest(
                    ticker, "SELL", position.getQuantity(), position.getStrategyId(), null, null));
            actions.add(new ManageAction(ticker, "EXITED_" + kind,
                    detail + " → sold %d @ ₹%s".formatted(order.quantity(), order.price())));
            return;
        }
        String op = "STOP".equals(kind) ? "lte" : "gte";
        boolean exists = alerts.findAll().stream().anyMatch(a ->
                a.getSymbolId().equals(symbol.getId()) && "close".equals(a.getField())
                && op.equals(a.getOp()) && a.getValue().compareTo(level) == 0);
        if (!exists) {
            alerts.save(new Alert(symbol.getId(), "close", op, level,
                    "AI position management: " + detail));
            actions.add(new ManageAction(ticker, kind + "_HIT_ALERT", detail));
        }
    }

    private static BigDecimal decimal(Object value) {
        return value instanceof Number n
                ? BigDecimal.valueOf(n.doubleValue()).setScale(2, RoundingMode.HALF_UP)
                : null;
    }
}
