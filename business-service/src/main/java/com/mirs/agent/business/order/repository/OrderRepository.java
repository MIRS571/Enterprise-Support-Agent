package com.mirs.agent.business.order.repository;

import com.mirs.agent.business.order.domain.CustomerOrder;

import java.util.Optional;

public interface OrderRepository {

    Optional<CustomerOrder> findByOrderIdAndUserId(
            String tenantId,
            String orderId,
            String userId
    );

    boolean markRefundingIfEligible(
            String tenantId,
            String orderId,
            String userId
    );
}
