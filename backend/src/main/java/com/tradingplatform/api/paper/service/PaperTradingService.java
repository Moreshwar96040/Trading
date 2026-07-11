package com.tradingplatform.api.paper.service;

import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.common.error.NotFoundException;
import com.tradingplatform.api.marketdata.domain.Symbol;
import com.tradingplatform.api.marketdata.service.SymbolService;
import com.tradingplatform.api.paper.domain.PaperAccount;
import com.tradingplatform.api.paper.domain.PaperOrder;
import com.tradingplatform.api.paper.domain.PaperPosition;
import com.tradingplatform.api.paper.repository.PaperAccountRepository;
import com.tradingplatform.api.paper.repository.PaperOrderRepository;
import com.tradingplatform.api.paper.repository.PaperPositionRepository;
import com.tradingplatform.api.paper.web.dto.PaperDtos.AccountDto;
import com.tradingplatform.api.paper.web.dto.PaperDtos.OrderDto;
import com.tradingplatform.api.paper.web.dto.PaperDtos.OrderRequest;
import com.tradingplatform.api.paper.web.dto.PaperDtos.PositionDto;
import com.tradingplatform.api.risk.service.RiskService;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaperTradingService {

    /** Single-user phase: everything happens on the seeded default account. */
    static final long DEFAULT_ACCOUNT_ID = 1L;

    private final PaperAccountRepository accounts;
    private final PaperPositionRepository positions;
    private final PaperOrderRepository orders;
    private final SymbolService symbolService;
    private final PriceService priceService;
    private final RiskService riskService;
    private final BigDecimal commissionPct;

    public PaperTradingService(PaperAccountRepository accounts, PaperPositionRepository positions,
                               PaperOrderRepository orders, SymbolService symbolService,
                               PriceService priceService, RiskService riskService,
                               @Value("${app.paper.commission-pct:0.05}") BigDecimal commissionPct) {
        this.accounts = accounts;
        this.positions = positions;
        this.orders = orders;
        this.symbolService = symbolService;
        this.priceService = priceService;
        this.riskService = riskService;
        this.commissionPct = commissionPct;
    }

    // ------------------------------------------------------------------ order
    @Transactional
    public OrderDto placeOrder(OrderRequest request) {
        validateRequest(request);
        PaperAccount account = defaultAccount();
        Symbol symbol = symbolService.getByTicker(request.ticker());
        String side = request.side().toUpperCase();
        int quantity = request.quantity();

        var reference = priceService.getReferencePrice(symbol);
        BigDecimal price = reference.price();
        BigDecimal gross = price.multiply(BigDecimal.valueOf(quantity));
        BigDecimal commission = gross.multiply(commissionPct)
                .divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);

        PaperOrder order;
        if ("BUY".equals(side)) {
            order = fillBuy(account, symbol, quantity, price, reference.source(), gross, commission);
        } else {
            order = fillSell(account, symbol, quantity, price, reference.source(), gross, commission);
        }
        return OrderDto.from(orders.save(order), symbol.getTicker());
    }

    private PaperOrder fillBuy(PaperAccount account, Symbol symbol, int quantity,
                               BigDecimal price, String source, BigDecimal gross,
                               BigDecimal commission) {
        BigDecimal totalCost = gross.add(commission);
        if (account.getCash().compareTo(totalCost) < 0) {
            return PaperOrder.rejected(account.getId(), symbol.getId(), "BUY", quantity,
                    "Insufficient cash: need ₹%s, have ₹%s".formatted(totalCost, account.getCash()));
        }
        PaperPosition position = positions.findByAccountIdAndSymbolId(account.getId(), symbol.getId())
                .orElseGet(() -> new PaperPosition(account.getId(), symbol.getId()));

        // Phase 6: risk gate — book-value equity, no network calls inside the txn.
        BigDecimal positionValueAfter = price.multiply(BigDecimal.valueOf(
                position.getQuantity() + quantity));
        BigDecimal bookEquity = account.getCash().add(bookValueOfPositions(account.getId()));
        String breach = riskService.checkBuyAgainstLimits(positionValueAfter, bookEquity);
        if (breach != null) {
            return PaperOrder.rejected(account.getId(), symbol.getId(), "BUY", quantity, breach);
        }

        position.applyBuy(quantity, price);
        positions.save(position);
        account.debitCash(totalCost);
        accounts.save(account);
        return PaperOrder.filled(account.getId(), symbol.getId(), "BUY", quantity, price,
                source, commission, null);
    }

    private PaperOrder fillSell(PaperAccount account, Symbol symbol, int quantity,
                                BigDecimal price, String source, BigDecimal gross,
                                BigDecimal commission) {
        PaperPosition position = positions.findByAccountIdAndSymbolId(account.getId(), symbol.getId())
                .orElse(null);
        if (position == null || position.getQuantity() < quantity) {
            int held = position == null ? 0 : position.getQuantity();
            return PaperOrder.rejected(account.getId(), symbol.getId(), "SELL", quantity,
                    "Insufficient quantity: have %d, tried to sell %d".formatted(held, quantity));
        }
        BigDecimal costBasis = position.getAvgCost().multiply(BigDecimal.valueOf(quantity));
        BigDecimal realized = gross.subtract(commission).subtract(costBasis)
                .setScale(2, RoundingMode.HALF_UP);

        position.applySell(quantity);
        positions.save(position);
        account.creditCash(gross.subtract(commission));
        account.addRealizedPnl(realized);
        accounts.save(account);
        return PaperOrder.filled(account.getId(), symbol.getId(), "SELL", quantity, price,
                source, commission, realized);
    }

    // ---------------------------------------------------------------- queries
    @Transactional(readOnly = true)
    public AccountDto getAccount() {
        PaperAccount account = defaultAccount();
        List<PaperPosition> open = positions.findByAccountIdAndQuantityGreaterThan(
                account.getId(), 0);

        Map<Long, Symbol> symbolsById = new HashMap<>();
        List<PositionDto> positionDtos = open.stream().map(p -> {
            Symbol symbol = symbolsById.computeIfAbsent(p.getSymbolId(),
                    id -> symbolService.getById(id));
            BigDecimal last = lastPriceOrAvgCost(symbol, p);
            BigDecimal marketValue = last.multiply(BigDecimal.valueOf(p.getQuantity()));
            BigDecimal unrealized = marketValue.subtract(
                    p.getAvgCost().multiply(BigDecimal.valueOf(p.getQuantity())))
                    .setScale(2, RoundingMode.HALF_UP);
            return new PositionDto(symbol.getTicker(), symbol.getName(), p.getQuantity(),
                    p.getAvgCost(), last, marketValue.setScale(2, RoundingMode.HALF_UP),
                    unrealized);
        }).toList();

        BigDecimal positionsValue = positionDtos.stream()
                .map(PositionDto::marketValue)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        BigDecimal unrealizedTotal = positionDtos.stream()
                .map(PositionDto::unrealizedPnl)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new AccountDto(account.getName(), account.getInitialCash(), account.getCash(),
                account.getCash().add(positionsValue).setScale(2, RoundingMode.HALF_UP),
                account.getRealizedPnl(), unrealizedTotal, positionDtos);
    }

    @Transactional(readOnly = true)
    public List<OrderDto> listOrders() {
        Map<Long, String> tickers = new HashMap<>();
        return orders.findTop200ByAccountIdOrderByPlacedAtDesc(DEFAULT_ACCOUNT_ID).stream()
                .map(o -> OrderDto.from(o, tickers.computeIfAbsent(o.getSymbolId(),
                        id -> symbolService.getById(id).getTicker())))
                .toList();
    }

    @Transactional
    public AccountDto resetAccount(BigDecimal initialCash) {
        PaperAccount account = defaultAccount();
        BigDecimal cash = initialCash != null && initialCash.signum() > 0
                ? initialCash : account.getInitialCash();
        account.reset(cash);
        accounts.save(account);
        positions.deleteAll(positions.findByAccountIdAndQuantityGreaterThan(account.getId(), -1));
        return getAccount();
    }

    // ---------------------------------------------------------------- helpers
    private BigDecimal bookValueOfPositions(Long accountId) {
        return positions.findByAccountIdAndQuantityGreaterThan(accountId, 0).stream()
                .map(p -> p.getAvgCost().multiply(BigDecimal.valueOf(p.getQuantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    private PaperAccount defaultAccount() {
        return accounts.findById(DEFAULT_ACCOUNT_ID)
                .orElseThrow(() -> new NotFoundException("Paper account missing — check V6 migration"));
    }

    private BigDecimal lastPriceOrAvgCost(Symbol symbol, PaperPosition position) {
        try {
            return priceService.getReferencePrice(symbol).price();
        } catch (Exception ex) {
            return position.getAvgCost();
        }
    }

    private void validateRequest(OrderRequest request) {
        if (request == null || request.ticker() == null || request.ticker().isBlank()) {
            throw new BadRequestException("ticker is required");
        }
        if (request.side() == null
                || !List.of("BUY", "SELL").contains(request.side().toUpperCase())) {
            throw new BadRequestException("side must be BUY or SELL");
        }
        if (request.quantity() == null || request.quantity() < 1) {
            throw new BadRequestException("quantity must be >= 1");
        }
    }
}
