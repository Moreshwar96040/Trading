package com.tradingplatform.api.common.error;

import java.time.Instant;

/** Uniform error body for every non-2xx response. */
public record ApiError(Instant timestamp, int status, String error, String message, String path) {

    public static ApiError of(int status, String error, String message, String path) {
        return new ApiError(Instant.now(), status, error, message, path);
    }
}
