package com.tradingplatform.api.screener.service;

import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.screener.domain.ScreenerSnapshot;
import com.tradingplatform.api.screener.repository.ScreenerSnapshotRepository;
import com.tradingplatform.api.screener.web.dto.ScreenCondition;
import com.tradingplatform.api.screener.web.dto.ScreenRequest;
import com.tradingplatform.api.screener.web.dto.ScreenRowDto;
import jakarta.persistence.criteria.Expression;
import jakarta.persistence.criteria.Path;
import jakarta.persistence.criteria.Predicate;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ScreenerService {

    static final int DEFAULT_LIMIT = 100;
    static final int MAX_LIMIT = 500;

    private final ScreenerSnapshotRepository repository;

    public ScreenerService(ScreenerSnapshotRepository repository) {
        this.repository = repository;
    }

    public List<ScreenRowDto> run(ScreenRequest request) {
        List<ScreenCondition> conditions =
                request.conditions() == null ? List.of() : request.conditions();
        conditions.forEach(this::validate);

        Sort sort = buildSort(request.sortBy(), request.sortDir());
        int limit = clampLimit(request.limit());

        return repository.findAll(buildSpecification(conditions), PageRequest.of(0, limit, sort))
                .stream().map(ScreenRowDto::from).toList();
    }

    // ------------------------------------------------------------ validation
    private void validate(ScreenCondition c) {
        if (c.field() == null || !(ScreenerFields.isNumeric(c.field()) || ScreenerFields.isString(c.field()))) {
            throw new BadRequestException("Unknown screener field: " + c.field());
        }
        if (c.op() == null || !ScreenerFields.OPS.contains(c.op())) {
            throw new BadRequestException("Unknown operator: " + c.op() + " (use gt|gte|lt|lte|eq)");
        }
        boolean hasValue = c.value() != null;
        boolean hasRef = c.ref() != null && !c.ref().isBlank();
        if (hasValue == hasRef) {
            throw new BadRequestException("Condition on '%s' needs exactly one of value or ref"
                    .formatted(c.field()));
        }
        if (hasRef && !ScreenerFields.isNumeric(c.ref())) {
            throw new BadRequestException("ref must be a numeric field, got: " + c.ref());
        }
        if (ScreenerFields.isString(c.field())) {
            if (!"eq".equals(c.op())) {
                throw new BadRequestException("String field '%s' only supports eq".formatted(c.field()));
            }
            if (!hasValue || !(c.value() instanceof String)) {
                throw new BadRequestException("String field '%s' needs a string value".formatted(c.field()));
            }
        } else if (hasValue && !(c.value() instanceof Number)) {
            throw new BadRequestException("Numeric field '%s' needs a numeric value".formatted(c.field()));
        }
    }

    // --------------------------------------------------------- specification
    private Specification<ScreenerSnapshot> buildSpecification(List<ScreenCondition> conditions) {
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();
            for (ScreenCondition c : conditions) {
                if (ScreenerFields.isString(c.field())) {
                    predicates.add(cb.equal(cb.upper(root.get("symbol").get(c.field())),
                            ((String) c.value()).toUpperCase()));
                    continue;
                }
                Path<BigDecimal> left = root.get(ScreenerFields.NUMERIC.get(c.field()));
                Expression<BigDecimal> right = (c.ref() != null && !c.ref().isBlank())
                        ? root.get(ScreenerFields.NUMERIC.get(c.ref()))
                        : cb.literal(BigDecimal.valueOf(((Number) c.value()).doubleValue()));
                predicates.add(switch (c.op()) {
                    case "gt" -> cb.greaterThan(left, right);
                    case "gte" -> cb.greaterThanOrEqualTo(left, right);
                    case "lt" -> cb.lessThan(left, right);
                    case "lte" -> cb.lessThanOrEqualTo(left, right);
                    default -> cb.equal(left, right);
                });
            }
            return cb.and(predicates.toArray(new Predicate[0]));
        };
    }

    private Sort buildSort(String sortBy, String sortDir) {
        if (sortBy == null || sortBy.isBlank()) {
            return Sort.by(Sort.Direction.ASC, "symbol.ticker");
        }
        if (!ScreenerFields.isNumeric(sortBy)) {
            throw new BadRequestException("Cannot sort by: " + sortBy);
        }
        Sort.Direction dir = "desc".equalsIgnoreCase(sortDir) ? Sort.Direction.DESC : Sort.Direction.ASC;
        return Sort.by(dir, ScreenerFields.NUMERIC.get(sortBy));
    }

    private int clampLimit(Integer limit) {
        if (limit == null || limit <= 0) {
            return DEFAULT_LIMIT;
        }
        return Math.min(limit, MAX_LIMIT);
    }
}
