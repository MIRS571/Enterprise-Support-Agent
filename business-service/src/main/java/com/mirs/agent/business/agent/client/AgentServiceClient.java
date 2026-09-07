package com.mirs.agent.business.agent.client;

import com.mirs.agent.business.agent.dto.AgentApprovalDecisionRequest;
import com.mirs.agent.business.agent.dto.AgentChatRequest;
import com.mirs.agent.business.agent.dto.AgentChatResponse;
import com.mirs.agent.business.agent.dto.AgentThreadResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class AgentServiceClient {

    private static final ParameterizedTypeReference<ServerSentEvent<String>>
            SSE_TYPE = new ParameterizedTypeReference<>() {
            };

    private final WebClient webClient;

    public AgentServiceClient(
            WebClient.Builder webClientBuilder,
            @Value("${agent-service.base-url}") String baseUrl,
            @Value("${agent-service.internal-token}") String internalToken
    ) {
        if (internalToken == null || internalToken.isBlank()) {
            throw new IllegalStateException(
                    "agent-service internal token is required"
            );
        }
        this.webClient = webClientBuilder
                .baseUrl(baseUrl)
                .defaultHeader(
                        "X-Internal-Service-Token",
                        internalToken
                )
                .build();
    }

    public Mono<ResponseEntity<AgentThreadResponse>> createThread(
            String tenantId,
            String userId,
            String requestId
    ) {
        return webClient.post()
                .uri("/api/v1/agent/threads")
                .header("X-Tenant-Id", tenantId)
                .header("X-User-Id", userId)
                .header("X-Request-Id", requestId)
                .retrieve()
                .toEntity(AgentThreadResponse.class);
    }

    public Mono<ResponseEntity<Flux<ServerSentEvent<String>>>> streamChat(
            String tenantId,
            String userId,
            String requestId,
            AgentChatRequest request
    ) {
        return webClient.post()
                .uri("/api/v1/agent/chat/stream")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .header("X-Tenant-Id", tenantId)
                .header("X-User-Id", userId)
                .header("X-Request-Id", requestId)
                .bodyValue(request)
                .retrieve()
                .toEntityFlux(SSE_TYPE)
                .map(response -> ResponseEntity
                        .status(response.getStatusCode())
                        .header(
                                "Cache-Control",
                                "no-cache, no-transform"
                        )
                        .header("X-Accel-Buffering", "no")
                        .contentType(MediaType.TEXT_EVENT_STREAM)
                        .body(response.getBody()));
    }

    public Mono<ResponseEntity<AgentChatResponse>> resumeThread(
            String tenantId,
            String userId,
            String requestId,
            String threadId,
            String idempotencyKey,
            AgentApprovalDecisionRequest request
    ) {
        return webClient.post()
                .uri(
                        "/api/v1/agent/threads/{threadId}/resume",
                        threadId
                )
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Tenant-Id", tenantId)
                .header("X-User-Id", userId)
                .header("X-Request-Id", requestId)
                .header("Idempotency-Key", idempotencyKey)
                .bodyValue(request)
                .retrieve()
                .toEntity(AgentChatResponse.class);
    }
}
