package com.mirs.agent.business.agent.dto;

import jakarta.validation.constraints.NotNull;

public record AgentApprovalDecisionRequest(
        @NotNull
        Boolean approved
) {
}
