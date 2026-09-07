package com.mirs.agent.business.order.service;

public class OrderNotFoundException extends RuntimeException {

    public OrderNotFoundException(String orderId) {
        super("订单不存在或当前用户无权访问：" + orderId);
    }
}
