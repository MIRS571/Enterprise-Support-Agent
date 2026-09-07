package com.mirs.agent.business.order.domain;

import java.math.BigDecimal;
import java.time.Instant;

public record CustomerOrder(
        String tenantId,
        String orderId,
        String userId,
        String productName,
        int quantity,
        BigDecimal totalAmount,
        OrderStatus status,
        Instant createdAt
) {
}
