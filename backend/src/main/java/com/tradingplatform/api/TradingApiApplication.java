package com.tradingplatform.api;

import com.tradingplatform.api.common.config.AppProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(AppProperties.class)
public class TradingApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(TradingApiApplication.class, args);
    }
}
