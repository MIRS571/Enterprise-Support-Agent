package com.mirs.agent.business.order.service;

public class RefundNotAllowedException extends RuntimeException {

    public RefundNotAllowedException(String orderId) {
        super("订单当前状态不允许申请退款：" + orderId);
    }
}
