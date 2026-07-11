package com.tradingplatform.api.fundamentals.web;

import com.tradingplatform.api.fundamentals.service.FundamentalsService;
import com.tradingplatform.api.fundamentals.web.dto.FundamentalsDto;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/fundamentals")
public class FundamentalsController {

    private final FundamentalsService fundamentalsService;

    public FundamentalsController(FundamentalsService fundamentalsService) {
        this.fundamentalsService = fundamentalsService;
    }

    /** GET /api/v1/fundamentals/RELIANCE — ratios + annual/quarterly statements. */
    @GetMapping("/{ticker}")
    public FundamentalsDto get(@PathVariable String ticker) {
        return fundamentalsService.getFundamentals(ticker);
    }
}
