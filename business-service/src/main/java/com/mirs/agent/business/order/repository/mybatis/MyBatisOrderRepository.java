package com.mirs.agent.business.order.repository.mybatis;

import com.mirs.agent.business.order.domain.CustomerOrder;
import com.mirs.agent.business.order.repository.OrderRepository;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
@Profile("!memory")
public class MyBatisOrderRepository implements OrderRepository {

    private final OrderMapper orderMapper;

    public MyBatisOrderRepository(OrderMapper orderMapper) {
        this.orderMapper = orderMapper;
    }

    @Override
    public Optional<CustomerOrder> findByOrderIdAndUserId(
            String tenantId,
            String orderId,
            String userId
    ) {
        return Optional.ofNullable(
                orderMapper.findOwnedOrder(tenantId, orderId, userId)
        ).map(this::toDomain);
    }

    @Override
    public boolean markRefundingIfEligible(
            String tenantId,
            String orderId,
            String userId
    ) {
        return orderMapper.markRefundingIfEligible(
                tenantId,
                orderId,
                userId
        ) == 1;
    }

    private CustomerOrder toDomain(OrderEntity entity) {
        return new CustomerOrder(
                entity.getTenantId(),
                entity.getOrderId(),
                entity.getUserId(),
                entity.getProductName(),
                entity.getQuantity(),
                entity.getTotalAmount(),
                entity.getStatus(),
                entity.getCreatedAt()
        );
    }
}
