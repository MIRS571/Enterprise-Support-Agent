package com.mirs.agent.business.order.service;

import com.mirs.agent.business.order.domain.CustomerOrder;
import com.mirs.agent.business.order.repository.OrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public CustomerOrder getOwnedOrder(
            String tenantId,
            String orderId,
            String userId
    ) {
        return orderRepository.findByOrderIdAndUserId(
                        tenantId,
                        orderId,
                        userId
                )
                .orElseThrow(() -> new OrderNotFoundException(orderId));
    }

    @Transactional
    public CustomerOrder requestRefund(
            String tenantId,
            String orderId,
            String userId
    ) {
        boolean updated = orderRepository.markRefundingIfEligible(
                tenantId,
                orderId,
                userId
        );
        if (!updated) {
            getOwnedOrder(tenantId, orderId, userId);
            throw new RefundNotAllowedException(orderId);
        }

        return getOwnedOrder(tenantId, orderId, userId);
    }
}
