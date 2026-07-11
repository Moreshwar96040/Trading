package com.tradingplatform.api.screener.web;

import com.tradingplatform.api.screener.service.ScreenerFields;
import com.tradingplatform.api.screener.service.ScreenerService;
import com.tradingplatform.api.screener.web.dto.ScreenRequest;
import com.tradingplatform.api.screener.web.dto.ScreenRowDto;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/screener")
public class ScreenerController {

    private final ScreenerService screenerService;

    public ScreenerController(ScreenerService screenerService) {
        this.screenerService = screenerService;
    }

    /**
     * POST /api/v1/screener/run
     * body: {"conditions":[{"field":"rsi_14","op":"lt","value":30},
     *                      {"field":"close","op":"gt","ref":"sma_200"}],
     *        "sortBy":"rsi_14","sortDir":"asc","limit":50}
     */
    @PostMapping("/run")
    public List<ScreenRowDto> run(@RequestBody ScreenRequest request) {
        return screenerService.run(request);
    }

    /** Field metadata so the UI builds its dropdowns from the single source of truth. */
    @GetMapping("/fields")
    public Map<String, Object> fields() {
        return Map.of(
                "numeric", ScreenerFields.NUMERIC.keySet().stream().sorted().toList(),
                "string", ScreenerFields.STRING.stream().sorted().toList(),
                "ops", ScreenerFields.OPS.stream().sorted().toList());
    }
}
