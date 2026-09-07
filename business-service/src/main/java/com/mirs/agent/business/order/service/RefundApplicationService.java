package com.mirs.agent.business.order.service;

import com.mirs.agent.business.order.dto.OrderResponse;
import org.springframework.stereotype.Service;

@Service
public class RefundApplicationService {

    private final OrderService orderService;
    private final RefundIdempotencyService idempotencyService;

    public RefundApplicationService(
            OrderService orderService,
            RefundIdempotencyService idempotencyService
    ) {
        this.orderService = orderService;
        this.idempotencyService = idempotencyService;
    }

    public OrderResponse requestRefund(
            String tenantId,
            String orderId,
            String userId,
            String idempotencyKey
    ) {
        return idempotencyService.execute(
                tenantId,
                userId,
                orderId,
                idempotencyKey,
                () -> OrderResponse.from(
                        orderService.requestRefund(
                                tenantId,
                                orderId,
                                userId
                        )
                )
        );
    }
}
