package com.tradingplatform.api.marketdata.web.dto;

import java.time.LocalDate;
import java.util.List;

public record CandleSeriesDto(String ticker, LocalDate from, LocalDate to,
                              List<CandleDto> candles) {}
