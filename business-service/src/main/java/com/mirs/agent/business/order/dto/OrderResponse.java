package com.mirs.agent.business.order.dto;

import com.mirs.agent.business.order.domain.CustomerOrder;
import com.mirs.agent.business.order.domain.OrderPolicy;
import com.mirs.agent.business.order.domain.OrderStatus;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderResponse(
        String orderId,
        String productName,
        int quantity,
        BigDecimal totalAmount,
        OrderStatus status,
        Instant createdAt,
        boolean cancelable,
        boolean refundable
) {

    public static OrderResponse from(CustomerOrder order) {
        return new OrderResponse(
                order.orderId(),
                order.productName(),
                order.quantity(),
                order.totalAmount(),
                order.status(),
                order.createdAt(),
                OrderPolicy.isCancelable(order.status()),
                OrderPolicy.isRefundable(order.status())
        );
    }
}
