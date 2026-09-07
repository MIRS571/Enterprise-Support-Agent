package com.mirs.agent.business.order.repository;

import com.mirs.agent.business.order.domain.CustomerOrder;
import com.mirs.agent.business.order.domain.OrderPolicy;
import com.mirs.agent.business.order.domain.OrderStatus;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

@Repository
@Profile("memory")
public class InMemoryOrderRepository implements OrderRepository {

    private final Map<String, CustomerOrder> orders = new ConcurrentHashMap<>(Map.of(
            "A1001",
            new CustomerOrder(
                    "company_001",
                    "A1001",
                    "U1001",
                    "机械键盘",
                    1,
                    new BigDecimal("299.00"),
                    OrderStatus.SHIPPED,
                    Instant.parse("2026-08-20T02:30:00Z")
            ),
            "A1002",
            new CustomerOrder(
                    "company_001",
                    "A1002",
                    "U1001",
                    "无线鼠标",
                    2,
                    new BigDecimal("198.00"),
                    OrderStatus.PAID,
                    Instant.parse("2026-08-23T01:15:00Z")
            ),
            "B2001",
            new CustomerOrder(
                    "company_001",
                    "B2001",
                    "U2002",
                    "显示器支架",
                    1,
                    new BigDecimal("159.00"),
                    OrderStatus.COMPLETED,
                    Instant.parse("2026-08-12T06:20:00Z")
            )
    ));

    @Override
    public Optional<CustomerOrder> findByOrderIdAndUserId(
            String tenantId,
            String orderId,
            String userId
    ) {
        return Optional.ofNullable(orders.get(orderId))
                .filter(order -> order.tenantId().equals(tenantId))
                .filter(order -> order.userId().equals(userId));
    }

    @Override
    public boolean markRefundingIfEligible(
            String tenantId,
            String orderId,
            String userId
    ) {
        AtomicBoolean updated = new AtomicBoolean(false);
        orders.computeIfPresent(orderId, (ignored, order) -> {
            boolean eligible = order.tenantId().equals(tenantId)
                    && order.userId().equals(userId)
                    && OrderPolicy.isRefundable(order.status());
            if (!eligible) {
                return order;
            }

            updated.set(true);
            return new CustomerOrder(
                    order.tenantId(),
                    order.orderId(),
                    order.userId(),
                    order.productName(),
                    order.quantity(),
                    order.totalAmount(),
                    OrderStatus.REFUNDING,
                    order.createdAt()
            );
        });
        return updated.get();
    }
}
