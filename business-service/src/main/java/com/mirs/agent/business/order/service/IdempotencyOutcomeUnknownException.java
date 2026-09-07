package com.mirs.agent.business.order.service;

public class IdempotencyOutcomeUnknownException extends RuntimeException {

    public IdempotencyOutcomeUnknownException(String message) {
        super(message);
    }

    public IdempotencyOutcomeUnknownException(
            String message,
            Throwable cause
    ) {
        super(message, cause);
    }
}
