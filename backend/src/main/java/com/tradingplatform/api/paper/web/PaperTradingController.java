package com.tradingplatform.api.paper.web;

import com.tradingplatform.api.paper.service.PaperTradingService;
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

    public PaperTradingController(PaperTradingService paperTrading) {
        this.paperTrading = paperTrading;
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
