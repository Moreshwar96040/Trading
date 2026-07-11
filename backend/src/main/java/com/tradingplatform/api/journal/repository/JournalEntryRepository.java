package com.tradingplatform.api.journal.repository;

import com.tradingplatform.api.journal.domain.JournalEntry;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface JournalEntryRepository extends JpaRepository<JournalEntry, Long> {

    List<JournalEntry> findAllByOrderByCreatedAtDesc();

    List<JournalEntry> findBySymbolIdOrderByCreatedAtDesc(Long symbolId);
}
