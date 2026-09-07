package com.mirs.agent.business.agent.client;

import com.mirs.agent.business.agent.dto.AgentApprovalDecisionRequest;
import com.mirs.agent.business.agent.dto.AgentChatRequest;
import com.mirs.agent.business.agent.dto.AgentChatResponse;
import com.mirs.agent.business.agent.dto.AgentThreadResponse;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

import java.time.Duration;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AgentServiceClientTests {

    private static final String REQUEST_ID =
            "c1ac5efd-1bb4-4dbf-b0e6-3a8320c4f30b";
    private static final String INTERNAL_TOKEN =
            "test-internal-service-token-1234567890";

    @Test
    void shouldRejectBlankInternalServiceToken() {
        assertThrows(
                IllegalStateException.class,
                () -> new AgentServiceClient(
                        WebClient.builder(),
                        "http://agent-service",
                        " "
                )
        );
    }

    @Test
    void shouldCreateThreadWithTrustedIdentityHeaders() {
        UUID threadId = UUID.fromString(
                "95a3ff0f-0fe1-4ed4-b6c4-f0a221403a9a"
        );
        AtomicReference<String> requestedPath = new AtomicReference<>();
        AtomicReference<String> tenantHeader = new AtomicReference<>();
        AtomicReference<String> userHeader = new AtomicReference<>();
        AtomicReference<String> requestHeader = new AtomicReference<>();
        AtomicReference<String> internalTokenHeader = new AtomicReference<>();
        ExchangeFunction exchangeFunction = request -> {
            requestedPath.set(request.url().getPath());
            tenantHeader.set(request.headers().getFirst("X-Tenant-Id"));
            userHeader.set(request.headers().getFirst("X-User-Id"));
            requestHeader.set(request.headers().getFirst("X-Request-Id"));
            internalTokenHeader.set(
                    request.headers().getFirst("X-Internal-Service-Token")
            );
            return reactor.core.publisher.Mono.just(
                    ClientResponse.create(HttpStatus.CREATED)
                            .header(
                                    "Content-Type",
                                    MediaType.APPLICATION_JSON_VALUE
                            )
                            .body("{\"thread_id\":\"" + threadId + "\"}")
                            .build()
            );
        };
        AgentServiceClient client = new AgentServiceClient(
                WebClient.builder().exchangeFunction(exchangeFunction),
                "http://agent-service",
                INTERNAL_TOKEN
        );

        ResponseEntity<AgentThreadResponse> response = client.createThread(
                "evaluation_001",
                "EVAL_U1001",
                REQUEST_ID
        ).block(Duration.ofSeconds(2));

        assertNotNull(response);
        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(threadId, response.getBody().threadId());
        assertEquals("/api/v1/agent/threads", requestedPath.get());
        assertEquals("evaluation_001", tenantHeader.get());
        assertEquals("EVAL_U1001", userHeader.get());
        assertEquals(REQUEST_ID, requestHeader.get());
        assertEquals(INTERNAL_TOKEN, internalTokenHeader.get());
    }

    @Test
    void shouldPreserveSseEventNamesAndJsonData() {
        AtomicReference<String> requestedPath = new AtomicReference<>();
        AtomicReference<String> tenantHeader = new AtomicReference<>();
        AtomicReference<String> requestHeader = new AtomicReference<>();
        AtomicReference<String> internalTokenHeader = new AtomicReference<>();
        ExchangeFunction exchangeFunction = request -> {
            requestedPath.set(request.url().getPath());
            tenantHeader.set(request.headers().getFirst("X-Tenant-Id"));
            requestHeader.set(request.headers().getFirst("X-Request-Id"));
            internalTokenHeader.set(
                    request.headers().getFirst("X-Internal-Service-Token")
            );
            return reactor.core.publisher.Mono.just(
                    ClientResponse.create(HttpStatus.OK)
                            .header(
                                    "Content-Type",
                                    MediaType.TEXT_EVENT_STREAM_VALUE
                            )
                            .body("""
                                    event: token
                                    data: {"content":"订单"}

                                    event: done
                                    data: {"status":"completed"}

                                    """)
                            .build()
            );
        };
        AgentServiceClient client = new AgentServiceClient(
                WebClient.builder().exchangeFunction(exchangeFunction),
                "http://agent-service",
                INTERNAL_TOKEN
        );

        ResponseEntity<Flux<ServerSentEvent<String>>> response =
                client.streamChat(
                        "company_001",
                        "U1001",
                        REQUEST_ID,
                        new AgentChatRequest(
                                "thread_001",
                                "查询订单A1001"
                        )
                ).block(Duration.ofSeconds(2));

        assertNotNull(response);
        assertNotNull(response.getBody());
        List<ServerSentEvent<String>> events = response.getBody()
                .collectList()
                .block(Duration.ofSeconds(2));

        assertNotNull(events);
        assertEquals(2, events.size());
        assertEquals("token", events.get(0).event());
        assertEquals("{\"content\":\"订单\"}", events.get(0).data());
        assertEquals("done", events.get(1).event());
        assertEquals(
                "/api/v1/agent/chat/stream",
                requestedPath.get()
        );
        assertEquals("company_001", tenantHeader.get());
        assertEquals(REQUEST_ID, requestHeader.get());
        assertEquals(INTERNAL_TOKEN, internalTokenHeader.get());
    }

    @Test
    void shouldResumeThreadWithTrustedContextAndIdempotencyKey() {
        AtomicReference<String> requestedPath = new AtomicReference<>();
        AtomicReference<String> tenantHeader = new AtomicReference<>();
        AtomicReference<String> userHeader = new AtomicReference<>();
        AtomicReference<String> requestHeader = new AtomicReference<>();
        AtomicReference<String> idempotencyHeader = new AtomicReference<>();
        ExchangeFunction exchangeFunction = request -> {
            requestedPath.set(request.url().getPath());
            tenantHeader.set(request.headers().getFirst("X-Tenant-Id"));
            userHeader.set(request.headers().getFirst("X-User-Id"));
            requestHeader.set(request.headers().getFirst("X-Request-Id"));
            idempotencyHeader.set(
                    request.headers().getFirst("Idempotency-Key")
            );
            return reactor.core.publisher.Mono.just(
                    ClientResponse.create(HttpStatus.OK)
                            .header(
                                    "Content-Type",
                                    MediaType.APPLICATION_JSON_VALUE
                            )
                            .body("""
                                    {
                                      "thread_id": "thread_001",
                                      "answer": "退款申请已提交",
                                      "intent": "refund",
                                      "order_id": "A1001",
                                      "sources": []
                                    }
                                    """)
                            .build()
            );
        };
        AgentServiceClient client = new AgentServiceClient(
                WebClient.builder().exchangeFunction(exchangeFunction),
                "http://agent-service",
                INTERNAL_TOKEN
        );

        ResponseEntity<AgentChatResponse> response = client.resumeThread(
                "company_001",
                "U1001",
                REQUEST_ID,
                "thread_001",
                "refund-001",
                new AgentApprovalDecisionRequest(true)
        ).block(Duration.ofSeconds(2));

        assertNotNull(response);
        assertNotNull(response.getBody());
        assertEquals("退款申请已提交", response.getBody().answer());
        assertEquals(
                "/api/v1/agent/threads/thread_001/resume",
                requestedPath.get()
        );
        assertEquals("company_001", tenantHeader.get());
        assertEquals("U1001", userHeader.get());
        assertEquals(REQUEST_ID, requestHeader.get());
        assertEquals("refund-001", idempotencyHeader.get());
    }
}
