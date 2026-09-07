package com.mirs.agent.business.order.service;

public class IdempotencyInProgressException extends RuntimeException {

    public IdempotencyInProgressException() {
        super("相同的退款请求正在处理中");
    }
}
