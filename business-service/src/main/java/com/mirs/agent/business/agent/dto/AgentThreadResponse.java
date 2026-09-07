package com.mirs.agent.business.agent.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.UUID;

public record AgentThreadResponse(
        @JsonProperty("thread_id")
        UUID threadId
) {
}
