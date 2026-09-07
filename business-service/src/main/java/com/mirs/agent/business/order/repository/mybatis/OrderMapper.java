package com.mirs.agent.business.order.repository.mybatis;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface OrderMapper {

    @Select("""
            SELECT tenant_id,
                   order_id,
                   user_id,
                   product_name,
                   quantity,
                   total_amount,
                   status,
                   created_at
            FROM customer_orders
            WHERE tenant_id = #{tenantId}
              AND order_id = #{orderId}
              AND user_id = #{userId}
            """)
    OrderEntity findOwnedOrder(
            @Param("tenantId") String tenantId,
            @Param("orderId") String orderId,
            @Param("userId") String userId
    );

    @Update("""
            UPDATE customer_orders
            SET status = 'REFUNDING',
                updated_at = CURRENT_TIMESTAMP(6)
            WHERE tenant_id = #{tenantId}
              AND order_id = #{orderId}
              AND user_id = #{userId}
              AND status IN ('SHIPPED', 'COMPLETED')
            """)
    int markRefundingIfEligible(
            @Param("tenantId") String tenantId,
            @Param("orderId") String orderId,
            @Param("userId") String userId
    );
}
