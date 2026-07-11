package com.tradingplatform.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.http.ResponseEntity;
import org.testcontainers.DockerClientFactory;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * Full-stack round trip: Flyway migration (schema + 20-symbol seed) → JPA → REST.
 * Requires Docker; auto-skips when unavailable (e.g. restricted CI sandboxes).
 */
@Testcontainers(disabledWithoutDocker = true)
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApiIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private TestRestTemplate rest;

    @BeforeAll
    static void requiresDocker() {
        assumeTrue(DockerClientFactory.instance().isDockerAvailable(), "Docker not available");
    }

    @Test
    void symbolsAreSeededByFlywayAndServedOverRest() {
        ResponseEntity<String> response = rest.getForEntity("/api/v1/symbols?query=RELIANCE", String.class);

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(response.getBody()).contains("Reliance Industries");
    }

    @Test
    void candlesEndpointReturnsEmptySeriesBeforeIngestion() {
        ResponseEntity<String> response =
                rest.getForEntity("/api/v1/symbols/TCS/candles?from=2026-01-01&to=2026-01-31", String.class);

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(response.getBody()).contains("\"candles\":[]");
    }

    @Test
    void unknownSymbolReturns404() {
        ResponseEntity<String> response = rest.getForEntity("/api/v1/symbols/NOPE/candles", String.class);

        assertThat(response.getStatusCode().value()).isEqualTo(404);
    }
}
