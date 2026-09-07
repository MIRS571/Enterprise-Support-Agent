package com.mirs.agent.business.order.domain;

import java.util.EnumSet;
import java.util.Set;

public final class OrderPolicy {

    private static final Set<OrderStatus> CANCELABLE_STATUSES = EnumSet.of(
            OrderStatus.PENDING_PAYMENT,
            OrderStatus.PAID
    );

    private static final Set<OrderStatus> REFUNDABLE_STATUSES = EnumSet.of(
            OrderStatus.SHIPPED,
            OrderStatus.COMPLETED
    );

    private OrderPolicy() {
    }

    public static boolean isCancelable(OrderStatus status) {
        return CANCELABLE_STATUSES.contains(status);
    }

    public static boolean isRefundable(OrderStatus status) {
        return REFUNDABLE_STATUSES.contains(status);
    }
}
