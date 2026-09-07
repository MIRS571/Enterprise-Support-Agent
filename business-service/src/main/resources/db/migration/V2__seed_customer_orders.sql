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
    ('company_001', 'A1001', 'U1001', '机械键盘', 1, 299.00, 'SHIPPED', '2026-08-20 02:30:00', '2026-08-20 02:30:00'),
    ('company_001', 'A1002', 'U1001', '无线鼠标', 2, 198.00, 'PAID', '2026-08-23 01:15:00', '2026-08-23 01:15:00'),
    ('company_001', 'B2001', 'U2002', '显示器支架', 1, 159.00, 'COMPLETED', '2026-08-12 06:20:00', '2026-08-12 06:20:00');
