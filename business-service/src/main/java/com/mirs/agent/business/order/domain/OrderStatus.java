package com.mirs.agent.business.order.domain;

public enum OrderStatus {
    PENDING_PAYMENT,
    PAID,
    SHIPPED,
    COMPLETED,
    CANCELLED,
    REFUNDING,
    REFUNDED
}
