package com.tradingplatform.api.common.error;

/** The internal market-data service (Python) failed or is unreachable. */
public class UpstreamException extends RuntimeException {
    public UpstreamException(String message, Throwable cause) {
        super(message, cause);
    }
}
