package com.tradingplatform.api.marketdata.web;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.tradingplatform.api.common.error.NotFoundException;
import com.tradingplatform.api.marketdata.service.CandleService;
import com.tradingplatform.api.marketdata.service.SymbolService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers = {SymbolController.class, CandleController.class})
@AutoConfigureMockMvc(addFilters = false)   // security disabled in the slice; permit-all in Phase 1 anyway
class SymbolControllerTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private SymbolService symbolService;

    @MockitoBean
    private CandleService candleService;

    @Test
    void searchReturnsJsonArray() throws Exception {
        when(symbolService.search(any())).thenReturn(List.of());

        mvc.perform(get("/api/v1/symbols?query=rel"))
                .andExpect(status().isOk());
    }

    @Test
    void unknownTickerMapsTo404WithApiErrorBody() throws Exception {
        when(candleService.getDailyCandles(any(), any(), any()))
                .thenThrow(new NotFoundException("Unknown symbol: NOPE"));

        mvc.perform(get("/api/v1/symbols/NOPE/candles"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.message").value("Unknown symbol: NOPE"));
    }

    @Test
    void malformedDateMapsTo400() throws Exception {
        mvc.perform(get("/api/v1/symbols/RELIANCE/candles?from=notadate"))
                .andExpect(status().isBadRequest());
    }
}
