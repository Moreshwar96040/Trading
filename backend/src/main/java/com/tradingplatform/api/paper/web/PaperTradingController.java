package com.tradingplatform.api.paper.web;

import com.tradingplatform.api.paper.service.PaperManagementService;
import com.tradingplatform.api.paper.service.PaperManagementService.ManageResult;
import com.tradingplatform.api.paper.service.PaperTradingService;
import java.util.Map;
import com.tradingplatform.api.paper.web.dto.PaperDtos.AccountDto;
import com.tradingplatform.api.paper.web.dto.PaperDtos.OrderDto;
import com.tradingplatform.api.paper.web.dto.PaperDtos.OrderRequest;
import com.tradingplatform.api.paper.web.dto.PaperDtos.ResetRequest;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/paper")
public class PaperTradingController {

    private final PaperTradingService paperTrading;
    private final PaperManagementService management;

    public PaperTradingController(PaperTradingService paperTrading,
                                  PaperManagementService management) {
        this.paperTrading = paperTrading;
        this.management = management;
    }

    /** POST /api/v1/paper/positions/RELIANCE/stop  body: {"stopPrice": 2890.5}
     *  Guardian one-click action: move a position's stop. */
    @PostMapping("/positions/{ticker}/stop")
    public Map<String, Object> updateStop(
            @org.springframework.web.bind.annotation.PathVariable String ticker,
            @RequestBody Map<String, Object> body) {
        Object raw = body == null ? null : body.get("stopPrice");
        java.math.BigDecimal stop = raw == null ? null : new java.math.BigDecimal(raw.toString());
        return paperTrading.updateStop(ticker, stop);
    }

    /** AI position management: ratchet trailing stops; alert or (opt-in) exit on
     *  stop/target hits. body (optional): {"autoExit": true} */
    @PostMapping("/manage")
    public ManageResult manage(@RequestBody(required = false) Map<String, Boolean> body) {
        boolean autoExit = body != null && Boolean.TRUE.equals(body.get("autoExit"));
        return management.manage(autoExit);
    }

    /** Account summary: cash, equity, realized/unrealized P&L, open positions. */
    @GetMapping("/account")
    public AccountDto account() {
        return paperTrading.getAccount();
    }

    /** Place a market order. body: {"ticker":"RELIANCE","side":"BUY","quantity":10} */
    @PostMapping("/orders")
    @ResponseStatus(HttpStatus.CREATED)
    public OrderDto placeOrder(@RequestBody OrderRequest request) {
        return paperTrading.placeOrder(request);
    }

    /** Last 200 orders, newest first (fills and rejections). */
    @GetMapping("/orders")
    public List<OrderDto> orders() {
        return paperTrading.listOrders();
    }

    /** Wipe positions and restore cash. body (optional): {"initialCash": 500000} */
    @PostMapping("/account/reset")
    public AccountDto reset(@RequestBody(required = false) ResetRequest request) {
        return paperTrading.resetAccount(request == null ? null : request.initialCash());
    }
}
