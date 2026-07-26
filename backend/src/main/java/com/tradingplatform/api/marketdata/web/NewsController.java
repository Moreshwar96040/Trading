package com.tradingplatform.api.marketdata.web;

import com.tradingplatform.api.integration.marketdata.MarketDataServiceClient;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Per-symbol news headlines + AI digest (proxied from the Python service). */
@RestController
@RequestMapping("/api/v1/news")
public class NewsController {

    private final MarketDataServiceClient marketData;

    public NewsController(MarketDataServiceClient marketData) {
        this.marketData = marketData;
    }

    /** GET /api/v1/news/market?refresh= — market-wide headlines + AI macro digest.
     *  (Declared before the {ticker} route so "market" isn't treated as a symbol.) */
    @GetMapping("/market")
    public Map<String, Object> market(@RequestParam(defaultValue = "false") boolean refresh) {
        return marketData.getMarketNews(refresh);
    }

    /** POST /api/v1/news/refresh — re-pull all market feeds, regenerate the macro
     *  digest and refresh news for signaled/held stocks. (No clash with the
     *  {ticker} route below: that one is GET-only.) */
    @PostMapping("/refresh")
    public Map<String, Object> refreshAll() {
        return marketData.refreshAllNews();
    }

    /** GET /api/v1/news/RELIANCE?refresh=true — headlines + AI insight for one symbol. */
    @GetMapping("/{ticker}")
    public Map<String, Object> news(@PathVariable String ticker,
                                    @RequestParam(defaultValue = "false") boolean refresh) {
        return marketData.getNews(ticker, refresh);
    }
}
