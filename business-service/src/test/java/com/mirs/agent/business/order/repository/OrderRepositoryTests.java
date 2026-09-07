package com.mirs.agent.business.order.repository;

import com.mirs.agent.business.order.domain.OrderStatus;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Transactional
class OrderRepositoryTests {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void shouldLoadDedicatedEvaluationOrderOnlyFromTrustedScope() {
        assertThat(orderRepository.findByOrderIdAndUserId(
                "evaluation_001",
                "EVAL-A1001",
                "EVAL_U1001"
        )).get().satisfies(order -> {
            assertThat(order.productName()).isEqualTo("评测专用机械键盘");
            assertThat(order.status()).isEqualTo(OrderStatus.SHIPPED);
        });

        assertThat(orderRepository.findByOrderIdAndUserId(
                "evaluation_001",
                "EVAL-A1001",
                "U9999"
        )).isEmpty();
    }

    @Test
    void shouldAtomicallyMarkOwnedEligibleOrderAsRefunding() {
        boolean updated = orderRepository.markRefundingIfEligible(
                "company_001",
                "A1001",
                "U1001"
        );

        assertThat(updated).isTrue();
        assertThat(orderRepository.findByOrderIdAndUserId(
                "company_001",
                "A1001",
                "U1001"
        )).get().extracting("status").isEqualTo(OrderStatus.REFUNDING);
    }

    @Test
    void shouldRejectSecondTransitionAfterStatusChanged() {
        assertThat(orderRepository.markRefundingIfEligible(
                "company_001",
                "A1001",
                "U1001"
        )).isTrue();

        assertThat(orderRepository.markRefundingIfEligible(
                "company_001",
                "A1001",
                "U1001"
        )).isFalse();
    }

    @Test
    void shouldNotModifyOrderForDifferentOwner() {
        boolean updated = orderRepository.markRefundingIfEligible(
                "company_001",
                "A1001",
                "U9999"
        );

        assertThat(updated).isFalse();
        assertThat(orderRepository.findByOrderIdAndUserId(
                "company_001",
                "A1001",
                "U1001"
        )).get().extracting("status").isEqualTo(OrderStatus.SHIPPED);
    }
}
