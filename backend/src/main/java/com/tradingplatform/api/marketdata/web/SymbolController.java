package com.tradingplatform.api.marketdata.web;

import com.tradingplatform.api.marketdata.service.SymbolService;
import com.tradingplatform.api.marketdata.web.dto.SymbolDto;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/symbols")
public class SymbolController {

    private final SymbolService symbolService;

    public SymbolController(SymbolService symbolService) {
        this.symbolService = symbolService;
    }

    /** List/search active symbols. GET /api/v1/symbols?query=rel */
    @GetMapping
    public List<SymbolDto> search(@RequestParam(required = false) String query) {
        return symbolService.search(query).stream().map(SymbolDto::from).toList();
    }
}
