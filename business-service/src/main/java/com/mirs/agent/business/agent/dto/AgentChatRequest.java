package com.mirs.agent.business.agent.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AgentChatRequest(
        @JsonProperty("thread_id")
        @NotBlank
        @Size(max = 128)
        String threadId,

        @NotBlank
        @Size(max = 4000)
        String message
) {
}
