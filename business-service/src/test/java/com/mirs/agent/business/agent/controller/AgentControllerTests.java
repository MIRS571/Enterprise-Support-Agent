package com.mirs.agent.business.agent.controller;

import com.mirs.agent.business.agent.client.AgentServiceClient;
import com.mirs.agent.business.agent.dto.AgentApprovalDecisionRequest;
import com.mirs.agent.business.agent.dto.AgentChatResponse;
import com.mirs.agent.business.agent.dto.AgentThreadResponse;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.UUID;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AgentControllerTests {

    private static final String REQUEST_ID =
            "c1ac5efd-1bb4-4dbf-b0e6-3a8320c4f30b";

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private AgentServiceClient agentServiceClient;

    @Test
    void shouldCreateThreadThroughJavaBoundary() throws Exception {
        UUID threadId = UUID.fromString(
                "95a3ff0f-0fe1-4ed4-b6c4-f0a221403a9a"
        );
        when(agentServiceClient.createThread(
                "evaluation_001",
                "EVAL_U1001",
                REQUEST_ID
        )).thenReturn(Mono.just(
                ResponseEntity.status(201).body(
                        new AgentThreadResponse(threadId)
                )
        ));

        MvcResult pending = mockMvc.perform(
                        post("/api/v1/agent/threads")
                                .header("X-Tenant-Id", "evaluation_001")
                                .header("X-User-Id", "EVAL_U1001")
                                .header("X-Request-Id", REQUEST_ID)
                )
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isCreated())
                .andExpect(header().string("X-Request-Id", REQUEST_ID))
                .andExpect(jsonPath("$.thread_id")
                        .value(threadId.toString()));
    }

    @Test
    void shouldForwardSseEvents() throws Exception {
        Flux<ServerSentEvent<String>> events = Flux.just(
                ServerSentEvent.builder("{\"content\":\"订单\"}")
                        .event("token")
                        .build(),
                ServerSentEvent.builder("{\"status\":\"completed\"}")
                        .event("done")
                        .build()
        );
        when(agentServiceClient.streamChat(
                eq("company_001"),
                eq("U1001"),
                eq(REQUEST_ID),
                any()
        )).thenReturn(Mono.just(
                ResponseEntity.ok()
                        .contentType(MediaType.TEXT_EVENT_STREAM)
                        .body(events)
        ));

        MvcResult pending = mockMvc.perform(
                        post("/api/v1/agent/chat/stream")
                                .header("X-Tenant-Id", "company_001")
                                .header("X-User-Id", "U1001")
                                .header("X-Request-Id", REQUEST_ID)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("""
                                        {
                                          "thread_id": "thread_001",
                                          "message": "查询订单A1001"
                                        }
                                        """)
                )
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-Id", REQUEST_ID))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM
                ))
                .andExpect(content().string(
                        org.hamcrest.Matchers.containsString(
                                "event:token"
                        )
                ));
    }

    @Test
    void shouldPreserveRateLimitStatusBeforeStreamStarts()
            throws Exception {
        WebClientResponseException upstreamError =
                WebClientResponseException.create(
                        429,
                        "Too Many Requests",
                        HttpHeaders.EMPTY,
                        new byte[0],
                        null
                );
        when(agentServiceClient.streamChat(
                eq("company_001"),
                eq("U1001"),
                eq(REQUEST_ID),
                any()
        )).thenReturn(Mono.error(upstreamError));

        MvcResult pending = mockMvc.perform(
                        post("/api/v1/agent/chat/stream")
                                .header("X-Tenant-Id", "company_001")
                                .header("X-User-Id", "U1001")
                                .header("X-Request-Id", REQUEST_ID)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("""
                                        {
                                          "thread_id": "thread_001",
                                          "message": "查询订单A1001"
                                        }
                                        """)
                )
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isTooManyRequests())
                .andExpect(jsonPath("$.code")
                        .value("AGENT_RATE_LIMITED"));
    }

    @Test
    void shouldResumeThreadThroughJavaBoundary() throws Exception {
        when(agentServiceClient.resumeThread(
                eq("company_001"),
                eq("U1001"),
                eq(REQUEST_ID),
                eq("thread_001"),
                eq("refund-001"),
                any(AgentApprovalDecisionRequest.class)
        )).thenReturn(Mono.just(
                ResponseEntity.ok(
                        new AgentChatResponse(
                                "thread_001",
                                "订单 A1001 的退款申请已提交。",
                                "refund",
                                "A1001",
                                List.of()
                        )
                )
        ));

        MvcResult pending = mockMvc.perform(
                        post(
                                "/api/v1/agent/threads/"
                                        + "thread_001/resume"
                        )
                                .header("X-Tenant-Id", "company_001")
                                .header("X-User-Id", "U1001")
                                .header("X-Request-Id", REQUEST_ID)
                                .header(
                                        "Idempotency-Key",
                                        "refund-001"
                                )
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"approved\":true}")
                )
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-Id", REQUEST_ID))
                .andExpect(jsonPath("$.thread_id").value("thread_001"))
                .andExpect(jsonPath("$.intent").value("refund"))
                .andExpect(jsonPath("$.order_id").value("A1001"));
    }

    @Test
    void shouldRejectResumeWithoutIdempotencyKeyBeforeProxying()
            throws Exception {
        mockMvc.perform(
                        post(
                                "/api/v1/agent/threads/"
                                        + "thread_001/resume"
                        )
                                .header("X-Tenant-Id", "company_001")
                                .header("X-User-Id", "U1001")
                                .header("X-Request-Id", REQUEST_ID)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"approved\":true}")
                )
                .andExpect(status().isBadRequest());

        verifyNoInteractions(agentServiceClient);
    }
}
