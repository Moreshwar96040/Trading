package com.tradingplatform.api.integration.upstox;

import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.common.error.UpstreamException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * Upstox API v2, READ-ONLY by design: OAuth login + holdings/positions import.
 * Deliberately no order methods — real-money execution stays with the user
 * until a strategy has passed the Edge Gates (and even then: confirm-per-order).
 *
 * Upstox access tokens expire daily (~03:30 IST) — reconnect is one click.
 */
@Service
public class UpstoxService {

    private static final Logger log = LoggerFactory.getLogger(UpstoxService.class);
    private static final String API = "https://api.upstox.com/v2";

    private final RestClient http = RestClient.create();
    private final String clientId;
    private final String clientSecret;
    private final String redirectUri;

    /** Single-user app: token held in memory; dies with the process (and daily). */
    private volatile String accessToken;
    private volatile Instant obtainedAt;

    public UpstoxService(@Value("${app.upstox.client-id:}") String clientId,
                         @Value("${app.upstox.client-secret:}") String clientSecret,
                         @Value("${app.upstox.redirect-uri:http://localhost:8080/api/v1/upstox/callback}")
                         String redirectUri) {
        this.clientId = clientId;
        this.clientSecret = clientSecret;
        this.redirectUri = redirectUri;
    }

    public boolean configured() {
        return clientId != null && !clientId.isBlank()
                && clientSecret != null && !clientSecret.isBlank();
    }

    public boolean connected() {
        return accessToken != null;
    }

    public String loginUrl() {
        if (!configured()) {
            throw new BadRequestException(
                    "Upstox not configured — set UPSTOX_CLIENT_ID / UPSTOX_CLIENT_SECRET in .env");
        }
        return API + "/login/authorization/dialog?response_type=code&client_id="
                + URLEncoder.encode(clientId, StandardCharsets.UTF_8)
                + "&redirect_uri=" + URLEncoder.encode(redirectUri, StandardCharsets.UTF_8);
    }

    @SuppressWarnings("unchecked")
    public void exchangeCode(String code) {
        var form = new LinkedMultiValueMap<String, String>();
        form.add("code", code);
        form.add("client_id", clientId);
        form.add("client_secret", clientSecret);
        form.add("redirect_uri", redirectUri);
        form.add("grant_type", "authorization_code");
        try {
            Map<String, Object> body = http.post().uri(API + "/login/authorization/token")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .body(form)
                    .retrieve().body(Map.class);
            Object token = body == null ? null : body.get("access_token");
            if (token == null) {
                throw new UpstreamException("Upstox token exchange returned no access_token", null);
            }
            this.accessToken = token.toString();
            this.obtainedAt = Instant.now();
            log.info("Upstox connected (read-only)");
        } catch (RestClientException ex) {
            throw new UpstreamException("Upstox token exchange failed", ex);
        }
    }

    public Map<String, Object> status() {
        Map<String, Object> out = new HashMap<>();
        out.put("configured", configured());
        out.put("connected", connected());
        out.put("connectedAt", obtainedAt == null ? null : obtainedAt.toString());
        out.put("note", connected()
                ? "Read-only — this integration cannot place orders"
                : "Tokens expire daily around 03:30 IST; reconnect each morning");
        return out;
    }

    public void disconnect() {
        accessToken = null;
        obtainedAt = null;
    }

    /** Long-term holdings + open intraday positions, normalized to the Guardian's
     *  shape: {ticker, quantity, avg_cost, last_price, pnl}. NSE equities only. */
    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> livePositions() {
        if (!connected()) {
            return List.of();
        }
        List<Map<String, Object>> out = new ArrayList<>();
        out.addAll(fetch("/portfolio/long-term-holdings"));
        out.addAll(fetch("/portfolio/short-term-positions"));
        return out;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> fetch(String path) {
        try {
            Map<String, Object> body = http.get().uri(API + path)
                    .header("Authorization", "Bearer " + accessToken)
                    .header("Accept", "application/json")
                    .retrieve().body(Map.class);
            Object data = body == null ? null : body.get("data");
            if (!(data instanceof List<?> list)) {
                return List.of();
            }
            List<Map<String, Object>> rows = new ArrayList<>();
            for (Object item : list) {
                if (!(item instanceof Map<?, ?> m)) continue;
                Map<String, Object> row = normalize((Map<String, Object>) m);
                if (row != null) rows.add(row);
            }
            return rows;
        } catch (RestClientException ex) {
            if (ex.getMessage() != null && ex.getMessage().contains("401")) {
                log.info("Upstox token expired — disconnecting");
                disconnect();
                return List.of();
            }
            log.warn("Upstox fetch {} failed: {}", path, ex.getMessage());
            return List.of();
        }
    }

    private Map<String, Object> normalize(Map<String, Object> m) {
        // holdings use tradingsymbol/quantity/average_price/last_price/pnl;
        // positions use similar keys with net quantity ("quantity")
        Object symbol = m.getOrDefault("tradingsymbol", m.get("trading_symbol"));
        Object qty = m.get("quantity");
        if (symbol == null || qty == null) return null;
        int quantity = (int) Double.parseDouble(qty.toString());
        if (quantity <= 0) return null;                    // long-only Guardian for now
        Object exchange = m.get("exchange");
        if (exchange != null && !"NSE".equalsIgnoreCase(exchange.toString())) return null;
        Map<String, Object> row = new HashMap<>();
        row.put("ticker", symbol.toString().toUpperCase());
        row.put("quantity", quantity);
        row.put("avg_cost", toDouble(m.getOrDefault("average_price", m.get("avg_price"))));
        row.put("last_price", toDouble(m.get("last_price")));
        row.put("pnl", toDouble(m.get("pnl")));
        return row;
    }

    private static Double toDouble(Object v) {
        try {
            return v == null ? null : Double.parseDouble(v.toString());
        } catch (NumberFormatException ex) {
            return null;
        }
    }
}
