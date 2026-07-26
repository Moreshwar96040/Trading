package com.tradingplatform.api.common.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Optional API-key gate for the whole REST surface.
 *
 * Why: exposing the backend through a tunnel (ngrok, for the TradingView bridge)
 * exposes EVERY endpoint — orders, account reset, strategy deletion — not just
 * the webhook. The webhook carries its own token; nothing else did.
 *
 * Behaviour:
 *  - API_KEY unset (local default)  -> filter is inert, everything works as before.
 *  - API_KEY set                    -> every /api/** request must carry
 *    X-Api-Key: <key> (or ?api_key=), EXCEPT /api/v1/webhooks/** which keeps its
 *    own body-token scheme (TradingView cannot send headers).
 */
@Component
public class ApiKeyFilter extends OncePerRequestFilter {

    private final String apiKey;

    public ApiKeyFilter(@Value("${app.api-key:}") String apiKey) {
        this.apiKey = apiKey;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        if (apiKey == null || apiKey.isBlank()) {
            return true;                                       // gate disabled
        }
        String path = request.getRequestURI();
        if (!path.startsWith("/api/")) {
            return true;                                       // static assets etc.
        }
        if (path.startsWith("/api/v1/webhooks/")) {
            return true;                                       // token-in-body scheme
        }
        if (path.equals("/api/v1/upstox/callback")) {
            return true;   // OAuth redirect arrives from the browser without headers
        }
        return "OPTIONS".equalsIgnoreCase(request.getMethod()); // CORS preflight
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String provided = request.getHeader("X-Api-Key");
        if (provided == null || provided.isBlank()) {
            provided = request.getParameter("api_key");
        }
        if (provided == null || !constantTimeEquals(apiKey, provided)) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json");
            response.getWriter().write(
                    "{\"message\":\"Missing or invalid X-Api-Key (API_KEY is set on this server)\"}");
            return;
        }
        chain.doFilter(request, response);
    }

    private static boolean constantTimeEquals(String a, String b) {
        return MessageDigest.isEqual(a.getBytes(StandardCharsets.UTF_8),
                                     b.getBytes(StandardCharsets.UTF_8));
    }
}
