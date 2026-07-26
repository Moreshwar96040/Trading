package com.tradingplatform.api.integration.upstox;

import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Upstox read-only connect + live holdings. No order endpoints — by design. */
@RestController
@RequestMapping("/api/v1/upstox")
public class UpstoxController {

    private final UpstoxService upstox;

    public UpstoxController(UpstoxService upstox) {
        this.upstox = upstox;
    }

    /** GET /api/v1/upstox/login-url — where the frontend sends the user to authorize. */
    @GetMapping("/login-url")
    public Map<String, String> loginUrl() {
        return Map.of("url", upstox.loginUrl());
    }

    /** OAuth redirect target (configure the same URI in the Upstox developer app). */
    @GetMapping("/callback")
    public ResponseEntity<Void> callback(@RequestParam String code) {
        upstox.exchangeCode(code);
        return ResponseEntity.status(HttpStatus.FOUND)
                .header("Location", "http://localhost:4200/portfolio?upstox=connected")
                .build();
    }

    /** GET /api/v1/upstox/status — configured / connected / when. */
    @GetMapping("/status")
    public Map<String, Object> status() {
        return upstox.status();
    }

    /** GET /api/v1/upstox/holdings — normalized live NSE positions (read-only). */
    @GetMapping("/holdings")
    public List<Map<String, Object>> holdings() {
        return upstox.livePositions();
    }

    /** POST /api/v1/upstox/disconnect — drop the in-memory token. */
    @PostMapping("/disconnect")
    public Map<String, Object> disconnect() {
        upstox.disconnect();
        return upstox.status();
    }
}
