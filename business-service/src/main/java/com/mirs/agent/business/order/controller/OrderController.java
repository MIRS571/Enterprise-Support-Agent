package com.mirs.agent.business.order.controller;

import com.mirs.agent.business.order.domain.CustomerOrder;
import com.mirs.agent.business.auth.Actor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import com.mirs.agent.business.order.dto.OrderResponse;
import com.mirs.agent.business.order.service.OrderService;
import com.mirs.agent.business.order.service.RefundApplicationService;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {

    private final OrderService orderService;
    private final RefundApplicationService refundApplicationService;

    public OrderController(
            OrderService orderService,
            RefundApplicationService refundApplicationService
    ) {
        this.orderService = orderService;
        this.refundApplicationService = refundApplicationService;
    }

    @GetMapping("/{orderId}")
    public OrderResponse getOrder(
            @PathVariable @NotBlank String orderId,
            @AuthenticationPrincipal Actor actor
    ) {
        CustomerOrder order = orderService.getOwnedOrder(
                actor.tenantId(),
                orderId,
                actor.userId()
        );
        return OrderResponse.from(order);
    }

    @PostMapping("/{orderId}/refund-requests")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public OrderResponse requestRefund(
            @PathVariable @NotBlank String orderId,
            @AuthenticationPrincipal Actor actor,
            @RequestHeader("Idempotency-Key") @NotBlank String idempotencyKey
    ) {
        return refundApplicationService.requestRefund(
                actor.tenantId(),
                orderId,
                actor.userId(),
                idempotencyKey
        );
    }
}
