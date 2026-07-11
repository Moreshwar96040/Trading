package com.tradingplatform.api.journal.web;

import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.common.error.NotFoundException;
import com.tradingplatform.api.journal.domain.JournalEntry;
import com.tradingplatform.api.journal.repository.JournalEntryRepository;
import com.tradingplatform.api.marketdata.service.SymbolService;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** Journal CRUD — thin enough that a separate service layer would be ceremony. */
@RestController
@RequestMapping("/api/v1/journal")
public class JournalController {

    public record EntryRequest(String ticker, Long paperOrderId, String title, String body,
                               String tags) {}

    public record EntryDto(Long id, String ticker, Long paperOrderId, String title, String body,
                           String tags, Instant createdAt, Instant updatedAt) {}

    private final JournalEntryRepository entries;
    private final SymbolService symbolService;

    public JournalController(JournalEntryRepository entries, SymbolService symbolService) {
        this.entries = entries;
        this.symbolService = symbolService;
    }

    @GetMapping
    @Transactional(readOnly = true)
    public List<EntryDto> list(@RequestParam(required = false) String ticker) {
        List<JournalEntry> found = (ticker == null || ticker.isBlank())
                ? entries.findAllByOrderByCreatedAtDesc()
                : entries.findBySymbolIdOrderByCreatedAtDesc(
                        symbolService.getByTicker(ticker).getId());
        Map<Long, String> tickers = new HashMap<>();
        return found.stream().map(e -> toDto(e, tickers)).toList();
    }

    @PostMapping
    @Transactional
    @ResponseStatus(HttpStatus.CREATED)
    public EntryDto create(@RequestBody EntryRequest request) {
        validate(request);
        Long symbolId = resolveSymbolId(request.ticker());
        JournalEntry saved = entries.save(new JournalEntry(symbolId, request.paperOrderId(),
                request.title().trim(), request.body(), normalizeTags(request.tags())));
        return toDto(saved, new HashMap<>());
    }

    @PutMapping("/{id}")
    @Transactional
    public EntryDto update(@PathVariable Long id, @RequestBody EntryRequest request) {
        validate(request);
        JournalEntry entry = entries.findById(id)
                .orElseThrow(() -> new NotFoundException("Unknown journal entry: " + id));
        entry.update(resolveSymbolId(request.ticker()), request.title().trim(),
                request.body(), normalizeTags(request.tags()));
        return toDto(entries.save(entry), new HashMap<>());
    }

    @DeleteMapping("/{id}")
    @Transactional
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable Long id) {
        if (!entries.existsById(id)) {
            throw new NotFoundException("Unknown journal entry: " + id);
        }
        entries.deleteById(id);
    }

    private void validate(EntryRequest request) {
        if (request.title() == null || request.title().isBlank()) {
            throw new BadRequestException("title is required");
        }
        if (request.body() == null || request.body().isBlank()) {
            throw new BadRequestException("body is required");
        }
    }

    private Long resolveSymbolId(String ticker) {
        return (ticker == null || ticker.isBlank())
                ? null : symbolService.getByTicker(ticker).getId();
    }

    private static String normalizeTags(String tags) {
        return tags == null ? null : tags.toLowerCase().replaceAll("\\s*,\\s*", ",").trim();
    }

    private EntryDto toDto(JournalEntry e, Map<Long, String> tickerCache) {
        String ticker = e.getSymbolId() == null ? null
                : tickerCache.computeIfAbsent(e.getSymbolId(),
                        id -> symbolService.getById(id).getTicker());
        return new EntryDto(e.getId(), ticker, e.getPaperOrderId(), e.getTitle(), e.getBody(),
                e.getTags(), e.getCreatedAt(), e.getUpdatedAt());
    }
}
