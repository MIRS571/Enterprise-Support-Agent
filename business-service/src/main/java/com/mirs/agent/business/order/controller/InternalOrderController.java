package com.mirs.agent.business.order.controller;

import com.mirs.agent.business.auth.AccountRepository;
import com.mirs.agent.business.auth.Actor;
import com.mirs.agent.business.order.dto.OrderResponse;
import com.mirs.agent.business.order.service.OrderService;
import com.mirs.agent.business.order.service.OrderNotFoundException;
import com.mirs.agent.business.order.service.RefundApplicationService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

/** Identity headers are accepted only behind ROLE_AGENT_SERVICE on this internal route. */
@RestController
@RequestMapping("/internal/v1/orders")
public class InternalOrderController {
    private final OrderService orders;
    private final RefundApplicationService refunds;
    private final AccountRepository accounts;
    public InternalOrderController(OrderService orders, RefundApplicationService refunds, AccountRepository accounts) {
        this.orders = orders; this.refunds = refunds; this.accounts = accounts;
    }
    private Actor identity(String tenant, String user, String order) {
        return accounts.findIdentity(tenant, user).filter(a -> a.enabled() && a.actor().role().equals("CUSTOMER"))
                .map(AccountRepository.Account::actor).orElseThrow(() -> new OrderNotFoundException(order));
    }
    @GetMapping("/{id}")
    public OrderResponse get(@PathVariable String id, @RequestHeader("X-Tenant-Id") String tenant, @RequestHeader("X-User-Id") String user) {
        Actor actor = identity(tenant, user, id);
        return OrderResponse.from(orders.getOwnedOrder(actor.tenantId(), id, actor.userId()));
    }
    @PostMapping("/{id}/refund-requests")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public OrderResponse refund(@PathVariable String id, @RequestHeader("X-Tenant-Id") String tenant,
            @RequestHeader("X-User-Id") String user, @RequestHeader("Idempotency-Key") String key) {
        Actor actor = identity(tenant, user, id);
        return refunds.requestRefund(actor.tenantId(), id, actor.userId(), key);
    }
}
