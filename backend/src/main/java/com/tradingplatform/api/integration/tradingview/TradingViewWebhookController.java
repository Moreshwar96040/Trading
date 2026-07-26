package com.tradingplatform.api.integration.tradingview;

import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import com.tradingplatform.api.journal.domain.JournalEntry;
import com.tradingplatform.api.journal.repository.JournalEntryRepository;
import com.tradingplatform.api.marketdata.domain.Symbol;
import com.tradingplatform.api.marketdata.service.SymbolService;
import com.tradingplatform.api.paper.service.PaperTradingService;
import com.tradingplatform.api.paper.web.dto.PaperDtos.AccountDto;
import com.tradingplatform.api.paper.web.dto.PaperDtos.OrderDto;
import com.tradingplatform.api.paper.web.dto.PaperDtos.OrderRequest;
import com.tradingplatform.api.risk.service.RiskService;
import com.tradingplatform.api.risk.web.dto.RiskDtos.PositionSizeRequest;
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * TradingView alert webhook -> the paper engine.
 *
 * TradingView (paid plans) can POST an alert's message to any URL. Point it at
 * this endpoint with a JSON message and the trade executes through the same
 * pipeline as a manual one: risk-sized when quantity is omitted, stop/target
 * attached, and auto-journaled with the alert's note.
 *
 * Alert message template (TradingView -> alert -> "Message" box):
 * <pre>
 * {"token":"YOUR_SECRET","ticker":"{{ticker}}","action":"buy",
 *  "stopPrice": 0, "note":"{{strategy.order.comment}}"}
 * </pre>
 *
 * Security: TradingView cannot send custom headers, so the shared secret rides
 * in the body (or ?token=). Configure TRADINGVIEW_WEBHOOK_SECRET in .env —
 * with no secret configured the endpoint refuses everything.
 */
@RestController
@RequestMapping("/api/v1/webhooks")
public class TradingViewWebhookController {

    private static final Logger log = LoggerFactory.getLogger(TradingViewWebhookController.class);

    private final PaperTradingService paperTrading;
    private final RiskService riskService;
    private final SymbolService symbolService;
    private final JournalEntryRepository journal;
    private final MarketDataServiceClient marketData;
    private final String secret;

    public TradingViewWebhookController(PaperTradingService paperTrading,
                                        RiskService riskService,
                                        SymbolService symbolService,
                                        JournalEntryRepository journal,
                                        MarketDataServiceClient marketData,
                                        @Value("${app.tradingview.webhook-secret:}") String secret) {
        this.paperTrading = paperTrading;
        this.riskService = riskService;
        this.symbolService = symbolService;
        this.journal = journal;
        this.marketData = marketData;
        this.secret = secret;
    }

    public record TvAlert(String token, String ticker, String action, Integer quantity,
                          BigDecimal stopPrice, BigDecimal targetPrice, String note) {}

    @PostMapping("/tradingview")
    public Map<String, Object> tradingview(@RequestBody TvAlert alert,
                                           @RequestParam(required = false) String token) {
        authorize(alert, token);
        if (alert.ticker() == null || alert.ticker().isBlank()) {
            throw new BadRequestException("ticker is required");
        }
        String action = alert.action() == null ? "" : alert.action().trim().toUpperCase();
        if (!action.equals("BUY") && !action.equals("SELL")) {
            throw new BadRequestException("action must be buy or sell");
        }
        // strip TradingView's exchange prefix / suffix quirks: NSE:RELIANCE, RELIANCE.NS
        String ticker = alert.ticker().trim().toUpperCase()
                .replaceFirst("^NSE:", "").replaceFirst("\\.NS$", "");

        int quantity = resolveQuantity(alert, action, ticker);
        OrderDto order = paperTrading.placeOrder(new OrderRequest(
                ticker, action, quantity, null, alert.stopPrice(), alert.targetPrice()));

        autoJournal(ticker, action, order, alert);
        log.info("TradingView webhook: {} {} x{} -> {}", action, ticker, quantity,
                 order.status());

        Map<String, Object> out = new HashMap<>();
        out.put("status", order.status());
        out.put("ticker", order.ticker());
        out.put("side", order.side());
        out.put("quantity", order.quantity());
        out.put("price", order.price());
        out.put("rejectReason", order.rejectReason());
        return out;
    }

    /** Quantity precedence: explicit -> risk-sized from stop (BUY) -> whole position (SELL). */
    private int resolveQuantity(TvAlert alert, String action, String ticker) {
        if (alert.quantity() != null && alert.quantity() > 0) {
            return alert.quantity();
        }
        if (action.equals("SELL")) {
            AccountDto account = paperTrading.getAccount();
            return account.positions().stream()
                    .filter(p -> p.ticker().equalsIgnoreCase(ticker))
                    .map(p -> p.quantity())
                    .findFirst()
                    .orElseThrow(() -> new BadRequestException(
                            "No open position in " + ticker + " to sell — send quantity explicitly"));
        }
        // BUY without quantity: size by risk rules; needs a stop to size against.
        if (alert.stopPrice() == null || alert.stopPrice().signum() <= 0) {
            throw new BadRequestException(
                    "BUY needs either quantity or stopPrice (used for risk sizing). "
                    + "Add \"stopPrice\": {{plot_0}} or a number to the alert JSON.");
        }
        BigDecimal entry = marketData.getQuote(ticker).price();
        var size = riskService.positionSize(
                new PositionSizeRequest(entry, alert.stopPrice(), null),
                paperTrading.getAccount().equity());
        if (size.quantity() < 1) {
            throw new BadRequestException("Risk sizing produced 0 shares — stop too tight");
        }
        return size.quantity();
    }

    private void autoJournal(String ticker, String action, OrderDto order, TvAlert alert) {
        try {
            Symbol symbol = symbolService.getByTicker(ticker);
            String note = alert.note() == null || alert.note().isBlank()
                    ? "(no note in alert)" : alert.note().trim();
            journal.save(new JournalEntry(symbol.getId(),
                    "FILLED".equals(order.status()) ? order.id() : null,
                    "TradingView ▸ %s %s".formatted(action, ticker),
                    "%s\n\n— webhook fill: %d @ ₹%s%s%s".formatted(
                            note, order.quantity(), order.price(),
                            alert.stopPrice() != null ? ", stop ₹" + alert.stopPrice() : "",
                            alert.targetPrice() != null ? ", target ₹" + alert.targetPrice() : ""),
                    "tradingview,webhook," + action.toLowerCase()));
        } catch (Exception ex) {   // journaling must never fail the fill
            log.warn("TradingView webhook journal failed for {}: {}", ticker, ex.getMessage());
        }
    }

    private void authorize(TvAlert alert, String queryToken) {
        if (secret == null || secret.isBlank()) {
            throw new BadRequestException(
                    "TradingView bridge disabled — set TRADINGVIEW_WEBHOOK_SECRET in .env first");
        }
        String provided = alert.token() != null && !alert.token().isBlank()
                ? alert.token() : queryToken;
        if (provided == null || !constantTimeEquals(secret, provided)) {
            throw new BadRequestException("Invalid webhook token");
        }
    }

    private static boolean constantTimeEquals(String a, String b) {
        byte[] x = a.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        byte[] y = b.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        return java.security.MessageDigest.isEqual(x, y);
    }
}
