package com.mirs.agent.business.agent.controller;

import com.mirs.agent.business.agent.client.AgentServiceClient;
import com.mirs.agent.business.agent.dto.AgentApprovalDecisionRequest;
import com.mirs.agent.business.agent.dto.AgentChatRequest;
import com.mirs.agent.business.agent.dto.AgentChatResponse;
import com.mirs.agent.business.agent.dto.AgentThreadResponse;
import com.mirs.agent.business.common.observability.RequestCorrelationFilter;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Validated
@RestController
@RequestMapping("/api/v1/agent")
public class AgentController {

    private final AgentServiceClient agentServiceClient;

    public AgentController(AgentServiceClient agentServiceClient) {
        this.agentServiceClient = agentServiceClient;
    }

    @PostMapping("/threads")
    public Mono<ResponseEntity<AgentThreadResponse>> createThread(
            @RequestHeader("X-Tenant-Id") @NotBlank String tenantId,
            @RequestHeader("X-User-Id") @NotBlank String userId,
            @RequestAttribute(
                    RequestCorrelationFilter.REQUEST_ID_ATTRIBUTE
            ) String requestId
    ) {
        return agentServiceClient.createThread(
                tenantId,
                userId,
                requestId
        );
    }

    @PostMapping(
            value = "/chat/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Mono<ResponseEntity<Flux<ServerSentEvent<String>>>> streamChat(
            @RequestHeader("X-Tenant-Id") @NotBlank String tenantId,
            @RequestHeader("X-User-Id") @NotBlank String userId,
            @RequestAttribute(
                    RequestCorrelationFilter.REQUEST_ID_ATTRIBUTE
            ) String requestId,
            @Valid @RequestBody AgentChatRequest request
    ) {
        return agentServiceClient.streamChat(
                tenantId,
                userId,
                requestId,
                request
        );
    }

    @PostMapping("/threads/{threadId}/resume")
    public Mono<ResponseEntity<AgentChatResponse>> resumeThread(
            @PathVariable @NotBlank String threadId,
            @RequestHeader("X-Tenant-Id") @NotBlank String tenantId,
            @RequestHeader("X-User-Id") @NotBlank String userId,
            @RequestHeader("Idempotency-Key")
            @NotBlank
            String idempotencyKey,
            @RequestAttribute(
                    RequestCorrelationFilter.REQUEST_ID_ATTRIBUTE
            ) String requestId,
            @Valid @RequestBody AgentApprovalDecisionRequest request
    ) {
        return agentServiceClient.resumeThread(
                tenantId,
                userId,
                requestId,
                threadId,
                idempotencyKey,
                request
        );
    }
}
