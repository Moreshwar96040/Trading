package com.tradingplatform.api.screener.service;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.tradingplatform.api.common.error.BadRequestException;
import com.tradingplatform.api.screener.repository.ScreenerSnapshotRepository;
import com.tradingplatform.api.screener.web.dto.ScreenCondition;
import com.tradingplatform.api.screener.web.dto.ScreenRequest;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.jpa.domain.Specification;

@ExtendWith(MockitoExtension.class)
class ScreenerServiceTest {

    @Mock
    private ScreenerSnapshotRepository repository;

    @InjectMocks
    private ScreenerService service;

    private static ScreenRequest req(ScreenCondition... conditions) {
        return new ScreenRequest(List.of(conditions), null, null, null);
    }

    @Test
    void validNumericConditionPasses() {
        when(repository.findAll(any(Specification.class), any(PageRequest.class)))
                .thenReturn(Page.empty());

        assertThatCode(() -> service.run(req(
                new ScreenCondition("rsi_14", "lt", 30, null))))
                .doesNotThrowAnyException();
    }

    @Test
    void crossFieldRefPasses() {
        when(repository.findAll(any(Specification.class), any(PageRequest.class)))
                .thenReturn(Page.empty());

        assertThatCode(() -> service.run(req(
                new ScreenCondition("close", "gt", null, "sma_200"))))
                .doesNotThrowAnyException();
    }

    @Test
    void unknownFieldIsRejected() {
        assertThatThrownBy(() -> service.run(req(
                new ScreenCondition("evil_column; DROP TABLE", "gt", 1, null))))
                .isInstanceOf(BadRequestException.class)
                .hasMessageContaining("Unknown screener field");
    }

    @Test
    void unknownOperatorIsRejected() {
        assertThatThrownBy(() -> service.run(req(
                new ScreenCondition("close", "like", 1, null))))
                .isInstanceOf(BadRequestException.class)
                .hasMessageContaining("Unknown operator");
    }

    @Test
    void valueAndRefTogetherRejected() {
        assertThatThrownBy(() -> service.run(req(
                new ScreenCondition("close", "gt", 100, "sma_50"))))
                .isInstanceOf(BadRequestException.class)
                .hasMessageContaining("exactly one");
    }

    @Test
    void neitherValueNorRefRejected() {
        assertThatThrownBy(() -> service.run(req(
                new ScreenCondition("close", "gt", null, null))))
                .isInstanceOf(BadRequestException.class);
    }

    @Test
    void stringFieldOnlySupportsEq() {
        assertThatThrownBy(() -> service.run(req(
                new ScreenCondition("sector", "gt", "IT", null))))
                .isInstanceOf(BadRequestException.class)
                .hasMessageContaining("only supports eq");
    }

    @Test
    void nonNumericValueOnNumericFieldRejected() {
        assertThatThrownBy(() -> service.run(req(
                new ScreenCondition("close", "gt", "abc", null))))
                .isInstanceOf(BadRequestException.class)
                .hasMessageContaining("numeric value");
    }

    @Test
    void limitIsClampedToMax() {
        when(repository.findAll(any(Specification.class), any(PageRequest.class)))
                .thenReturn(Page.empty());

        service.run(new ScreenRequest(List.of(), null, null, 9999));

        ArgumentCaptor<PageRequest> captor = ArgumentCaptor.forClass(PageRequest.class);
        verify(repository).findAll(any(Specification.class), captor.capture());
        org.assertj.core.api.Assertions.assertThat(captor.getValue().getPageSize())
                .isEqualTo(ScreenerService.MAX_LIMIT);
    }

    @Test
    void sortByUnknownFieldRejected() {
        assertThatThrownBy(() -> service.run(new ScreenRequest(List.of(), "evil", "asc", null)))
                .isInstanceOf(BadRequestException.class)
                .hasMessageContaining("Cannot sort by");
    }
}
