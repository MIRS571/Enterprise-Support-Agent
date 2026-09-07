package com.mirs.agent.business.order.service;

public class IdempotencyConflictException extends RuntimeException {

    public IdempotencyConflictException() {
        super("同一个幂等键不能用于不同的退款请求");
    }
}
