package com.tradingplatform.api.risk.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.risk.domain.RiskSettings;
import com.tradingplatform.api.risk.repository.RiskSettingsRepository;
import com.tradingplatform.api.risk.web.dto.RiskDtos.PositionSizeRequest;
import com.tradingplatform.api.risk.web.dto.RiskDtos.PositionSizeResult;
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
class RiskServiceTest {

    @Mock
    private RiskSettingsRepository repository;

    private RiskService service;

    @BeforeEach
    void setUp() throws Exception {
        service = new RiskService(repository);
        RiskSettings settings = newSettings("20.00", "40.00", "1.00", true);
        when(repository.findById(1L)).thenReturn(Optional.of(settings));
    }

    private static RiskSettings newSettings(String maxPos, String maxSector, String riskPct,
                                            boolean block) throws Exception {
        var ctor = RiskSettings.class.getDeclaredConstructor();
        ctor.setAccessible(true);
        RiskSettings s = ctor.newInstance();
        set(s, "id", 1L);
        set(s, "maxPositionPct", new BigDecimal(maxPos));
        set(s, "maxSectorPct", new BigDecimal(maxSector));
        set(s, "riskPerTradePct", new BigDecimal(riskPct));
        set(s, "blockOnBreach", block);
        return s;
    }

    private static void set(Object target, String field, Object value) throws Exception {
        Field f = target.getClass().getDeclaredField(field);
        f.setAccessible(true);
        f.set(target, value);
    }

    @Test
    void positionSizeUsesRiskPerTrade() {
        // equity 1,000,000 × 1% = 10,000 risk; entry 100, stop 95 → 5/share → 2000 shares
        // cap: 20% × 1,000,000 = 200,000 / 100 = 2000 shares → exactly at cap
        PositionSizeResult result = service.positionSize(
                new PositionSizeRequest(new BigDecimal("100"), new BigDecimal("95"), null),
                new BigDecimal("1000000"));

        assertThat(result.quantity()).isEqualTo(2000);
        assertThat(result.riskAmount()).isEqualByComparingTo("10000.00");
    }

    @Test
    void positionSizeCappedByMaxPositionLimit() {
        // tight stop -> huge risk-based qty; cap kicks in: 200,000 / 100 = 2000
        PositionSizeResult result = service.positionSize(
                new PositionSizeRequest(new BigDecimal("100"), new BigDecimal("99.9"), null),
                new BigDecimal("1000000"));

        assertThat(result.quantity()).isEqualTo(2000);
        assertThat(result.cappedByPositionLimit()).isTrue();
    }

    @Test
    void stopAboveEntryIsRejected() {
        assertThatThrownBy(() -> service.positionSize(
                new PositionSizeRequest(new BigDecimal("100"), new BigDecimal("105"), null),
                new BigDecimal("1000000")))
                .isInstanceOf(BadRequestException.class)
                .hasMessageContaining("below entryPrice");
    }

    @Test
    void buyGateBlocksOversizedPosition() {
        String breach = service.checkBuyAgainstLimits(
                new BigDecimal("300000"), new BigDecimal("1000000"));   // 30% > 20%

        assertThat(breach).contains("Risk limit");
    }

    @Test
    void buyGateAllowsWithinLimit() {
        assertThat(service.checkBuyAgainstLimits(
                new BigDecimal("150000"), new BigDecimal("1000000"))).isNull();   // 15%
    }

    @Test
    void buyGateDisabledWhenBlockOff() throws Exception {
        when(repository.findById(1L))
                .thenReturn(Optional.of(newSettings("20.00", "40.00", "1.00", false)));

        assertThat(service.checkBuyAgainstLimits(
                new BigDecimal("900000"), new BigDecimal("1000000"))).isNull();
    }

    @Test
    void settingsValidationRejectsOutOfRange() {
        assertThatThrownBy(() -> service.updateSettings(new BigDecimal("150"),
                new BigDecimal("40"), new BigDecimal("1"), true))
                .isInstanceOf(BadRequestException.class);
    }
}
