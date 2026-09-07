package com.mirs.agent.business.order.service;

public class IdempotencyUnavailableException extends RuntimeException {

    public IdempotencyUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }

    public IdempotencyUnavailableException(String message) {
        super(message);
    }
}
