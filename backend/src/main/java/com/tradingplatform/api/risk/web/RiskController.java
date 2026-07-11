package com.tradingplatform.api.risk.web;

import com.tradingplatform.api.paper.service.PaperTradingService;
import com.tradingplatform.api.risk.domain.RiskSettings;
import com.tradingplatform.api.risk.service.RiskService;
import com.tradingplatform.api.risk.web.dto.RiskDtos.PositionSizeRequest;
import com.tradingplatform.api.risk.web.dto.RiskDtos.PositionSizeResult;
import com.tradingplatform.api.risk.web.dto.RiskDtos.RiskReport;
import com.tradingplatform.api.risk.web.dto.RiskDtos.SettingsDto;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/risk")
public class RiskController {

    private final RiskService riskService;
    private final PaperTradingService paperTrading;

    public RiskController(RiskService riskService, PaperTradingService paperTrading) {
        this.riskService = riskService;
        this.paperTrading = paperTrading;
    }

    @GetMapping("/settings")
    public SettingsDto settings() {
        RiskSettings s = riskService.getSettings();
        return new SettingsDto(s.getMaxPositionPct(), s.getMaxSectorPct(),
                s.getRiskPerTradePct(), s.isBlockOnBreach());
    }

    @PutMapping("/settings")
    public SettingsDto update(@RequestBody SettingsDto dto) {
        RiskSettings s = riskService.updateSettings(dto.maxPositionPct(), dto.maxSectorPct(),
                dto.riskPerTradePct(), dto.blockOnBreach());
        return new SettingsDto(s.getMaxPositionPct(), s.getMaxSectorPct(),
                s.getRiskPerTradePct(), s.isBlockOnBreach());
    }

    /** Marked-to-market exposure vs limits (uses the paper account). */
    @GetMapping("/report")
    public RiskReport report() {
        return riskService.buildReport(paperTrading.getAccount());
    }

    /** Position-size calculator. body: {entryPrice, stopPrice, equityOverride?} */
    @PostMapping("/position-size")
    public PositionSizeResult positionSize(@RequestBody PositionSizeRequest request) {
        return riskService.positionSize(request, paperTrading.getAccount().equity());
    }
}
