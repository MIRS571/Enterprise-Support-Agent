package com.mirs.agent.business.order.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.mirs.agent.business.order.domain.OrderStatus;
import com.mirs.agent.business.order.dto.OrderResponse;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;

class RefundIdempotencyServiceTests {

    private final ObjectMapper objectMapper = JsonMapper.builder()
            .findAndAddModules()
            .build();

    @Test
    void shouldExecuteFirstRequestAndStoreCompletedResult() {
        StringRedisTemplate redisTemplate = mock(StringRedisTemplate.class);
        doAnswer(invocation -> {
            RedisScript<?> script = invocation.getArgument(0);
            if (script.getResultType() == String.class) {
                return "__ACQUIRED__";
            }
            return 1L;
        }).when(redisTemplate).execute(
                any(RedisScript.class),
                anyList(),
                any(Object[].class)
        );
        RefundIdempotencyService service = createService(redisTemplate);
        AtomicInteger executions = new AtomicInteger();

        OrderResponse response = service.execute(
                "company_001",
                "U1001",
                "A1001",
                "refund-001",
                () -> {
                    executions.incrementAndGet();
                    return refundingOrder();
                }
        );

        assertEquals(OrderStatus.REFUNDING, response.status());
        assertEquals(1, executions.get());
    }

    @Test
    void shouldReportUnknownOutcomeWhenCompletedResultCannotBeStored() {
        StringRedisTemplate redisTemplate = mock(StringRedisTemplate.class);
        doAnswer(invocation -> {
            RedisScript<?> script = invocation.getArgument(0);
            if (script.getResultType() == String.class) {
                return "__ACQUIRED__";
            }
            return 0L;
        }).when(redisTemplate).execute(
                any(RedisScript.class),
                anyList(),
                any(Object[].class)
        );
        RefundIdempotencyService service = createService(redisTemplate);
        AtomicInteger executions = new AtomicInteger();

        assertThrows(
                IdempotencyOutcomeUnknownException.class,
                () -> service.execute(
                        "company_001",
                        "U1001",
                        "A1001",
                        "refund-001",
                        () -> {
                            executions.incrementAndGet();
                            return refundingOrder();
                        }
                )
        );
        assertEquals(1, executions.get());
    }

    @Test
    void shouldRejectSameRequestWhileProcessing() {
        StringRedisTemplate redisTemplate = mock(StringRedisTemplate.class);
        doAnswer(invocation -> processingJson("A1001"))
                .when(redisTemplate)
                .execute(
                        any(RedisScript.class),
                        anyList(),
                        any(Object[].class)
                );
        RefundIdempotencyService service = createService(redisTemplate);

        assertThrows(
                IdempotencyInProgressException.class,
                () -> service.execute(
                        "company_001",
                        "U1001",
                        "A1001",
                        "refund-001",
                        this::refundingOrder
                )
        );
    }

    @Test
    void shouldRejectSameKeyForDifferentOrder() {
        StringRedisTemplate redisTemplate = mock(StringRedisTemplate.class);
        doAnswer(invocation -> processingJson("A1001"))
                .when(redisTemplate)
                .execute(
                        any(RedisScript.class),
                        anyList(),
                        any(Object[].class)
                );
        RefundIdempotencyService service = createService(redisTemplate);

        assertThrows(
                IdempotencyConflictException.class,
                () -> service.execute(
                        "company_001",
                        "U1001",
                        "A1002",
                        "refund-001",
                        this::refundingOrder
                )
        );
    }

    @Test
    void shouldReplayCompletedResponseWithoutExecutingAgain()
            throws Exception {
        StringRedisTemplate redisTemplate = mock(StringRedisTemplate.class);
        doAnswer(invocation -> completedJson("A1001"))
                .when(redisTemplate)
                .execute(
                        any(RedisScript.class),
                        anyList(),
                        any(Object[].class)
                );
        RefundIdempotencyService service = createService(redisTemplate);
        AtomicInteger executions = new AtomicInteger();

        OrderResponse response = service.execute(
                "company_001",
                "U1001",
                "A1001",
                "refund-001",
                () -> {
                    executions.incrementAndGet();
                    return refundingOrder();
                }
        );

        assertEquals(OrderStatus.REFUNDING, response.status());
        assertEquals(0, executions.get());
    }

    private RefundIdempotencyService createService(
            StringRedisTemplate redisTemplate
    ) {
        return new RefundIdempotencyService(
                redisTemplate,
                objectMapper,
                "esa",
                "test",
                60,
                86400
        );
    }

    private String processingJson(String orderId) {
        return "{\"fingerprint\":\"request_refund:" + orderId
                + "\",\"status\":\"PROCESSING\",\"response\":null}";
    }

    private String completedJson(String orderId) throws Exception {
        return objectMapper.writeValueAsString(
                new TestStoredRecord(
                        "request_refund:" + orderId,
                        "COMPLETED",
                        refundingOrder()
                )
        );
    }

    private OrderResponse refundingOrder() {
        return new OrderResponse(
                "A1001",
                "机械键盘",
                1,
                new BigDecimal("299.00"),
                OrderStatus.REFUNDING,
                Instant.parse("2026-08-20T02:30:00Z"),
                false,
                false
        );
    }

    private record TestStoredRecord(
            String fingerprint,
            String status,
            OrderResponse response
    ) {
    }
}
