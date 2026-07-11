package com.tradingplatform.api.journal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.time.Instant;

@Entity
@Table(name = "journal_entries")
public class JournalEntry {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "symbol_id")
    private Long symbolId;

    @Column(name = "paper_order_id")
    private Long paperOrderId;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private String body;

    private String tags;

    @Column(name = "created_at")
    private Instant createdAt;

    @Column(name = "updated_at")
    private Instant updatedAt;

    protected JournalEntry() {
        // JPA
    }

    public JournalEntry(Long symbolId, Long paperOrderId, String title, String body, String tags) {
        this.symbolId = symbolId;
        this.paperOrderId = paperOrderId;
        this.title = title;
        this.body = body;
        this.tags = tags;
    }

    public void update(Long symbolId, String title, String body, String tags) {
        this.symbolId = symbolId;
        this.title = title;
        this.body = body;
        this.tags = tags;
    }

    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
        updatedAt = createdAt;
    }

    @PreUpdate
    void onUpdate() {
        updatedAt = Instant.now();
    }

    public Long getId() { return id; }
    public Long getSymbolId() { return symbolId; }
    public Long getPaperOrderId() { return paperOrderId; }
    public String getTitle() { return title; }
    public String getBody() { return body; }
    public String getTags() { return tags; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
