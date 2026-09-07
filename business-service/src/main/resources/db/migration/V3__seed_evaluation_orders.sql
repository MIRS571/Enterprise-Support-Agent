INSERT INTO customer_orders (
    tenant_id,
    order_id,
    user_id,
    product_name,
    quantity,
    total_amount,
    status,
    created_at,
    updated_at
) VALUES
    (
        'evaluation_001',
        'EVAL-A1001',
        'EVAL_U1001',
        '评测专用机械键盘',
        1,
        299.00,
        'SHIPPED',
        '2026-09-01 00:00:00',
        '2026-09-01 00:00:00'
    );
