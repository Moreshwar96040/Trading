package com.tradingplatform.api.paper.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.marketdata.domain.Symbol;
import com.tradingplatform.api.marketdata.service.SymbolService;
import com.tradingplatform.api.paper.domain.PaperAccount;
import com.tradingplatform.api.paper.domain.PaperOrder;
import com.tradingplatform.api.paper.domain.PaperPosition;
import com.tradingplatform.api.paper.repository.PaperAccountRepository;
import com.tradingplatform.api.paper.repository.PaperOrderRepository;
import com.tradingplatform.api.paper.repository.PaperPositionRepository;
import com.tradingplatform.api.paper.service.PriceService.ReferencePrice;
import com.tradingplatform.api.paper.web.dto.PaperDtos.OrderDto;
import com.tradingplatform.api.paper.web.dto.PaperDtos.OrderRequest;
import com.tradingplatform.api.risk.service.RiskService;
import com.tradingplatform.api.strategy.repository.StrategyRepository;
import com.tradingplatform.api.journal.repository.JournalEntryRepository;
import java.lang.reflect.Field;
import java.math.BigDecimal;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class PaperTradingServiceTest {

    @Mock
    private PaperAccountRepository accounts;

    @Mock
    private PaperPositionRepository positions;

    @Mock
    private PaperOrderRepository orders;

    @Mock
    private SymbolService symbolService;

    @Mock
    private PriceService priceService;

    @Mock
    private RiskService riskService;

    @Mock
    private StrategyRepository strategies;

    @Mock
    private JournalEntryRepository journal;

    @Mock
    private Symbol reliance;

    private PaperTradingService service;
    private PaperAccount account;

    @BeforeEach
    void setUp() throws Exception {
        service = new PaperTradingService(accounts, positions, orders, symbolService,
                priceService, riskService, strategies, journal, new BigDecimal("0.0"));  // zero commission
        // default: no risk breach; individual tests override
        when(riskService.checkBuyAgainstLimits(any(), any())).thenReturn(null);
        when(positions.findByAccountIdAndQuantityGreaterThan(any(), any()))
                .thenReturn(java.util.List.of());

        account = newAccount(new BigDecimal("100000"));
        when(accounts.findById(1L)).thenReturn(Optional.of(account));
        when(accounts.save(any())).thenAnswer(inv -> inv.getArgument(0));
        when(positions.save(any())).thenAnswer(inv -> inv.getArgument(0));
        when(orders.save(any(PaperOrder.class))).thenAnswer(inv -> inv.getArgument(0));

        when(reliance.getId()).thenReturn(10L);
        when(reliance.getTicker()).thenReturn("RELIANCE");
        when(symbolService.getByTicker("RELIANCE")).thenReturn(reliance);
        when(priceService.getReferencePrice(reliance))
                .thenReturn(new ReferencePrice(new BigDecimal("100.00"), "CLOSE"));
    }

    private static PaperAccount newAccount(BigDecimal cash) throws Exception {
        var ctor = PaperAccount.class.getDeclaredConstructor();
        ctor.setAccessible(true);
        PaperAccount acc = ctor.newInstance();
        set(acc, "id", 1L);
        set(acc, "name", "Default");
        set(acc, "initialCash", cash);
        set(acc, "cash", cash);
        set(acc, "realizedPnl", BigDecimal.ZERO);
        return acc;
    }

    private static void set(Object target, String field, Object value) throws Exception {
        Field f = target.getClass().getDeclaredField(field);
        f.setAccessible(true);
        f.set(target, value);
    }

    @Test
    void buyFillsAndDebitsCash() {
        when(positions.findByAccountIdAndSymbolId(1L, 10L)).thenReturn(Optional.empty());

        OrderDto order = service.placeOrder(new OrderRequest("RELIANCE", "BUY", 100, null, null, null));

        assertThat(order.status()).isEqualTo("FILLED");
        assertThat(order.price()).isEqualByComparingTo("100.00");
        assertThat(account.getCash()).isEqualByComparingTo("90000");   // 100k - 10k
    }

    @Test
    void buyBeyondCashIsRejectedAndNothingChanges() {
        when(positions.findByAccountIdAndSymbolId(1L, 10L)).thenReturn(Optional.empty());

        OrderDto order = service.placeOrder(new OrderRequest("RELIANCE", "BUY", 2000, null, null, null));

        assertThat(order.status()).isEqualTo("REJECTED");
        assertThat(order.rejectReason()).contains("Insufficient cash");
        assertThat(account.getCash()).isEqualByComparingTo("100000");
    }

    @Test
    void averageCostIsWeightedAcrossBuys() {
        PaperPosition position = new PaperPosition(1L, 10L);
        position.applyBuy(100, new BigDecimal("100.00"));            // existing 100 @ 100
        when(positions.findByAccountIdAndSymbolId(1L, 10L)).thenReturn(Optional.of(position));
        when(priceService.getReferencePrice(reliance))
                .thenReturn(new ReferencePrice(new BigDecimal("120.00"), "CLOSE"));

        service.placeOrder(new OrderRequest("RELIANCE", "BUY", 50, null, null, null));

        // (100*100 + 50*120) / 150 = 106.6667
        assertThat(position.getQuantity()).isEqualTo(150);
        assertThat(position.getAvgCost()).isEqualByComparingTo("106.6667");
    }

    @Test
    void sellRealizesPnlAndCreditsCash() {
        PaperPosition position = new PaperPosition(1L, 10L);
        position.applyBuy(100, new BigDecimal("80.00"));             // basis 80
        when(positions.findByAccountIdAndSymbolId(1L, 10L)).thenReturn(Optional.of(position));

        OrderDto order = service.placeOrder(new OrderRequest("RELIANCE", "SELL", 40, null, null, null));

        assertThat(order.status()).isEqualTo("FILLED");
        assertThat(order.realizedPnl()).isEqualByComparingTo("800.00");  // 40 * (100-80)
        assertThat(position.getQuantity()).isEqualTo(60);
        assertThat(account.getCash()).isEqualByComparingTo("104000");    // +40*100
        assertThat(account.getRealizedPnl()).isEqualByComparingTo("800.00");
    }

    @Test
    void oversellIsRejected() {
        PaperPosition position = new PaperPosition(1L, 10L);
        position.applyBuy(10, new BigDecimal("100.00"));
        when(positions.findByAccountIdAndSymbolId(1L, 10L)).thenReturn(Optional.of(position));

        OrderDto order = service.placeOrder(new OrderRequest("RELIANCE", "SELL", 50, null, null, null));

        assertThat(order.status()).isEqualTo("REJECTED");
        assertThat(order.rejectReason()).contains("have 10");
        assertThat(position.getQuantity()).isEqualTo(10);
    }

    @Test
    void sellingUnownedSymbolIsRejected() {
        when(positions.findByAccountIdAndSymbolId(1L, 10L)).thenReturn(Optional.empty());

        OrderDto order = service.placeOrder(new OrderRequest("RELIANCE", "SELL", 5, null, null, null));

        assertThat(order.status()).isEqualTo("REJECTED");
        assertThat(order.rejectReason()).contains("have 0");
    }

    @Test
    void buyBreachingRiskLimitIsRejected() {
        when(positions.findByAccountIdAndSymbolId(1L, 10L)).thenReturn(Optional.empty());
        when(riskService.checkBuyAgainstLimits(any(), any()))
                .thenReturn("Risk limit: position would be 50.0% of equity (max 20.0%)");

        OrderDto order = service.placeOrder(new OrderRequest("RELIANCE", "BUY", 500, null, null, null));

        assertThat(order.status()).isEqualTo("REJECTED");
        assertThat(order.rejectReason()).contains("Risk limit");
        assertThat(account.getCash()).isEqualByComparingTo("100000");   // untouched
    }

    @Test
    void invalidRequestsAreRejectedUpfront() {
        assertThatThrownBy(() -> service.placeOrder(new OrderRequest(" ", "BUY", 1, null, null, null)))
                .isInstanceOf(BadRequestException.class);
        assertThatThrownBy(() -> service.placeOrder(new OrderRequest("RELIANCE", "HOLD", 1, null, null, null)))
                .isInstanceOf(BadRequestException.class);
        assertThatThrownBy(() -> service.placeOrder(new OrderRequest("RELIANCE", "BUY", 0, null, null, null)))
                .isInstanceOf(BadRequestException.class);
    }
}
