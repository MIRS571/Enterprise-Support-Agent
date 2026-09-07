package com.mirs.agent.business.order.controller;

import com.mirs.agent.business.order.dto.OrderResponse;
import com.mirs.agent.business.order.service.IdempotencyConflictException;
import com.mirs.agent.business.order.service.IdempotencyInProgressException;
import com.mirs.agent.business.order.service.RefundIdempotencyService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.annotation.Transactional;

import java.util.function.Supplier;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class OrderControllerTests {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private RefundIdempotencyService idempotencyService;

    @BeforeEach
    void executeRefundActionByDefault() {
        doAnswer(invocation -> {
            Supplier<OrderResponse> action = invocation.getArgument(4);
            return action.get();
        }).when(idempotencyService).execute(
                anyString(),
                anyString(),
                anyString(),
                anyString(),
                any()
        );
    }

    @Test
    void shouldReturnOwnedOrder() throws Exception {
        mockMvc.perform(
                        get("/api/v1/orders/A1001")
                                .header("X-Tenant-Id", "company_001")
                                .header("X-User-Id", "U1001")
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("A1001"))
                .andExpect(jsonPath("$.status").value("SHIPPED"))
                .andExpect(jsonPath("$.createdAt").value("2026-08-20T02:30:00Z"))
                .andExpect(jsonPath("$.cancelable").value(false))
                .andExpect(jsonPath("$.refundable").value(true));
    }

    @Test
    void shouldReturnNotFoundForUnknownOrder() throws Exception {
        mockMvc.perform(
                        get("/api/v1/orders/UNKNOWN")
                                .header("X-Tenant-Id", "company_001")
                                .header("X-User-Id", "U1001")
                )
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }

    @Test
    void shouldHideOrderOwnedByAnotherUser() throws Exception {
        mockMvc.perform(
                        get("/api/v1/orders/A1001")
                                .header("X-Tenant-Id", "company_001")
                                .header("X-User-Id", "U9999")
                )
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }

    @Test
    void shouldHideOrderOwnedByAnotherTenant() throws Exception {
        mockMvc.perform(
                        get("/api/v1/orders/A1001")
                                .header("X-Tenant-Id", "company_999")
                                .header("X-User-Id", "U1001")
                )
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }

    @Test
    void shouldAcceptRefundForOwnedEligibleOrder() throws Exception {
        mockMvc.perform(
                        post("/api/v1/orders/A1001/refund-requests")
                                .header("X-Tenant-Id", "company_001")
                                .header("X-User-Id", "U1001")
                                .header("Idempotency-Key", "refund-001")
                )
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.orderId").value("A1001"))
                .andExpect(jsonPath("$.status").value("REFUNDING"))
                .andExpect(jsonPath("$.refundable").value(false));
    }

    @Test
    void shouldReturnConflictForIneligibleOwnedOrder() throws Exception {
        mockMvc.perform(
                        post("/api/v1/orders/A1002/refund-requests")
                                .header("X-Tenant-Id", "company_001")
                                .header("X-User-Id", "U1001")
                                .header("Idempotency-Key", "refund-002")
                )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("REFUND_NOT_ALLOWED"));
    }

    @Test
    void shouldHideRefundOrderOwnedByAnotherUser() throws Exception {
        mockMvc.perform(
                        post("/api/v1/orders/A1001/refund-requests")
                                .header("X-Tenant-Id", "company_001")
                                .header("X-User-Id", "U9999")
                                .header("Idempotency-Key", "refund-003")
                )
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }

    @Test
    void shouldRequireIdempotencyKeyForRefund() throws Exception {
        mockMvc.perform(
                        post("/api/v1/orders/A1001/refund-requests")
                                .header("X-Tenant-Id", "company_001")
                                .header("X-User-Id", "U1001")
                )
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturnConflictForReusedKeyWithDifferentRequest()
            throws Exception {
        doThrow(new IdempotencyConflictException())
                .when(idempotencyService)
                .execute(
                        anyString(),
                        anyString(),
                        anyString(),
                        anyString(),
                        any()
                );

        mockMvc.perform(
                        post("/api/v1/orders/A1002/refund-requests")
                                .header("X-Tenant-Id", "company_001")
                                .header("X-User-Id", "U1001")
                                .header("Idempotency-Key", "refund-001")
                )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code")
                        .value("IDEMPOTENCY_CONFLICT"));
    }

    @Test
    void shouldReturnConflictWhileSameRequestIsProcessing()
            throws Exception {
        doThrow(new IdempotencyInProgressException())
                .when(idempotencyService)
                .execute(
                        anyString(),
                        anyString(),
                        anyString(),
                        anyString(),
                        any()
                );

        mockMvc.perform(
                        post("/api/v1/orders/A1001/refund-requests")
                                .header("X-Tenant-Id", "company_001")
                                .header("X-User-Id", "U1001")
                                .header("Idempotency-Key", "refund-001")
                )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code")
                        .value("IDEMPOTENCY_IN_PROGRESS"));
    }
}
