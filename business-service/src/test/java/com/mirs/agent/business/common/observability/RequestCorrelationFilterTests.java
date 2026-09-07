package com.mirs.agent.business.common.observability;

import org.junit.jupiter.api.Test;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class RequestCorrelationFilterTests {

    @Test
    void shouldPreserveCanonicalUuid() {
        String requestId = "c1ac5efd-1bb4-4dbf-b0e6-3a8320c4f30b";

        assertEquals(
                requestId,
                RequestCorrelationFilter.resolveRequestId(requestId)
        );
    }

    @Test
    void shouldReplaceInvalidExternalValue() {
        String resolved = RequestCorrelationFilter.resolveRequestId(
                "not-a-safe-request-id"
        );

        assertNotEquals("not-a-safe-request-id", resolved);
        UUID.fromString(resolved);
    }
}
