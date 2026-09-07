package com.mirs.agent.business.agent.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

public record AgentChatResponse(
        @JsonProperty("thread_id")
        String threadId,

        String answer,

        String intent,

        @JsonProperty("order_id")
        String orderId,

        List<AgentSourceResponse> sources
) {
    public record AgentSourceResponse(
            @JsonProperty("reference_number")
            int referenceNumber,

            @JsonProperty("document_id")
            String documentId,

            String title,

            @JsonProperty("section_title")
            String sectionTitle,

            String version
    ) {
    }
}
