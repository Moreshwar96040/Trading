package com.tradingplatform.api.screener.web.dto;

import java.util.List;

public record ScreenRequest(List<ScreenCondition> conditions, String sortBy,
                            String sortDir, Integer limit) {}
