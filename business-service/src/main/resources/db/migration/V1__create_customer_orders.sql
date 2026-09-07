CREATE TABLE customer_orders (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    quantity INT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    updated_at TIMESTAMP(6) NOT NULL,
    CONSTRAINT chk_customer_orders_quantity CHECK (quantity > 0),
    CONSTRAINT chk_customer_orders_amount CHECK (total_amount >= 0)
);

CREATE UNIQUE INDEX uk_customer_orders_tenant_order
    ON customer_orders (tenant_id, order_id);

CREATE INDEX idx_customer_orders_tenant_user_order
    ON customer_orders (tenant_id, user_id, order_id);
