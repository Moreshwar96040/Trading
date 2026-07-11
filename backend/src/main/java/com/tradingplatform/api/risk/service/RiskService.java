package com.tradingplatform.api.risk.service;

import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.common.error.NotFoundException;
import com.tradingplatform.api.paper.web.dto.PaperDtos.AccountDto;
import com.tradingplatform.api.paper.web.dto.PaperDtos.PositionDto;
import com.tradingplatform.api.risk.domain.RiskSettings;
import com.tradingplatform.api.risk.repository.RiskSettingsRepository;
import com.tradingplatform.api.risk.web.dto.RiskDtos.PositionSizeRequest;
import com.tradingplatform.api.risk.web.dto.RiskDtos.PositionSizeResult;
import com.tradingplatform.api.risk.web.dto.RiskDtos.RiskReport;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RiskService {

    private static final long SETTINGS_ID = 1L;

    private final RiskSettingsRepository settingsRepository;

    public RiskService(RiskSettingsRepository settingsRepository) {
        this.settingsRepository = settingsRepository;
    }

    @Transactional(readOnly = true)
    public RiskSettings getSettings() {
        return settingsRepository.findById(SETTINGS_ID)
                .orElseThrow(() -> new NotFoundException("Risk settings missing — check V7 migration"));
    }

    @Transactional
    public RiskSettings updateSettings(BigDecimal maxPositionPct, BigDecimal maxSectorPct,
                                       BigDecimal riskPerTradePct, boolean blockOnBreach) {
        validatePct("maxPositionPct", maxPositionPct);
        validatePct("maxSectorPct", maxSectorPct);
        validatePct("riskPerTradePct", riskPerTradePct);
        RiskSettings settings = getSettings();
        settings.update(maxPositionPct, maxSectorPct, riskPerTradePct, blockOnBreach);
        return settingsRepository.save(settings);
    }

    /**
     * Risk-based position size: qty = floor(equity × risk% / (entry − stop)),
     * capped so the position value never exceeds maxPositionPct of equity.
     */
    public PositionSizeResult positionSize(PositionSizeRequest request, BigDecimal equity) {
        if (request.entryPrice() == null || request.entryPrice().signum() <= 0) {
            throw new BadRequestException("entryPrice must be > 0");
        }
        if (request.stopPrice() == null || request.stopPrice().signum() <= 0
                || request.stopPrice().compareTo(request.entryPrice()) >= 0) {
            throw new BadRequestException("stopPrice must be > 0 and below entryPrice (long-only)");
        }
        RiskSettings settings = getSettings();
        BigDecimal effectiveEquity = request.equityOverride() != null
                && request.equityOverride().signum() > 0 ? request.equityOverride() : equity;

        BigDecimal riskAmount = effectiveEquity.multiply(settings.getRiskPerTradePct())
                .divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);
        BigDecimal perShareRisk = request.entryPrice().subtract(request.stopPrice());
        int riskQty = riskAmount.divide(perShareRisk, 0, RoundingMode.DOWN).intValue();

        BigDecimal maxPositionValue = effectiveEquity.multiply(settings.getMaxPositionPct())
                .divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);
        int capQty = maxPositionValue.divide(request.entryPrice(), 0, RoundingMode.DOWN).intValue();

        int quantity = Math.max(0, Math.min(riskQty, capQty));
        return new PositionSizeResult(quantity, riskAmount, perShareRisk,
                request.entryPrice().multiply(BigDecimal.valueOf(quantity)),
                quantity == capQty && capQty < riskQty);
    }

    /** Exposure report from a marked-to-market account snapshot. */
    public RiskReport buildReport(AccountDto account) {
        RiskSettings settings = getSettings();
        BigDecimal equity = account.equity();
        List<RiskReport.Exposure> positions = new ArrayList<>();
        Map<String, BigDecimal> sectorValues = new LinkedHashMap<>();
        List<String> breaches = new ArrayList<>();

        for (PositionDto position : account.positions()) {
            BigDecimal pct = pctOf(position.marketValue(), equity);
            positions.add(new RiskReport.Exposure(position.ticker(), position.marketValue(), pct));
            if (pct.compareTo(settings.getMaxPositionPct()) > 0) {
                breaches.add("%s is %.1f%% of equity (limit %.1f%%)"
                        .formatted(position.ticker(), pct, settings.getMaxPositionPct()));
            }
        }
        // sector exposure needs the sector, which PositionDto doesn't carry; the
        // controller enriches names → sectors. Kept simple: name field reused upstream.

        BigDecimal cashPct = pctOf(account.cash(), equity);
        return new RiskReport(equity, account.cash(), cashPct, positions,
                List.of(), breaches, settings.getMaxPositionPct(), settings.getMaxSectorPct());
    }

    /** Order-time gate for paper BUYs, using book-value equity (no network calls). */
    public String checkBuyAgainstLimits(BigDecimal positionValueAfterFill, BigDecimal bookEquity) {
        RiskSettings settings = getSettings();
        if (!settings.isBlockOnBreach() || bookEquity.signum() <= 0) {
            return null;
        }
        BigDecimal pct = pctOf(positionValueAfterFill, bookEquity);
        if (pct.compareTo(settings.getMaxPositionPct()) > 0) {
            return "Risk limit: position would be %.1f%% of equity (max %.1f%%)"
                    .formatted(pct, settings.getMaxPositionPct());
        }
        return null;
    }

    private static BigDecimal pctOf(BigDecimal part, BigDecimal whole) {
        if (whole == null || whole.signum() == 0) {
            return BigDecimal.ZERO;
        }
        return part.multiply(BigDecimal.valueOf(100)).divide(whole, 2, RoundingMode.HALF_UP);
    }

    private void validatePct(String name, BigDecimal value) {
        if (value == null || value.signum() <= 0 || value.compareTo(BigDecimal.valueOf(100)) > 0) {
            throw new BadRequestException(name + " must be between 0 and 100");
        }
    }
}
