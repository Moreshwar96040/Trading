package com.tradingplatform.api.marketdata.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Read model for the symbol master. Writes happen only in the Python service /
 * Flyway seeds, so this entity is intentionally immutable (no setters).
 */
@Entity
@Table(name = "symbols")
public class Symbol {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String ticker;

    @Column(name = "yahoo_symbol", nullable = false)
    private String yahooSymbol;

    @Column(nullable = false)
    private String name;

    private String sector;

    @Column(nullable = false)
    private String exchange;

    @Column(nullable = false)
    private String currency;

    @Column(nullable = false)
    private boolean active;

    protected Symbol() {
        // JPA
    }

    public Long getId() { return id; }
    public String getTicker() { return ticker; }
    public String getYahooSymbol() { return yahooSymbol; }
    public String getName() { return name; }
    public String getSector() { return sector; }
    public String getExchange() { return exchange; }
    public String getCurrency() { return currency; }
    public boolean isActive() { return active; }
}
