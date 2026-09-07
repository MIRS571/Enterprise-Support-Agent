# 第二天：Java 业务能力与 Python 调用

## 业务背景

Agent 负责理解自然语言和组织回答，Java 业务服务负责身份校验、订单数据和确定性业务规则。Agent 不直接访问订单数据库，也不自行判断订单是否允许取消或退款。

## 今日验收

- [x] 固定订单查询接口契约
- [x] Java 订单查询与所有权过滤
- [x] Java 取消、退款资格规则
- [x] 结构化 404 错误
- [x] 成功、不存在、越权自动化测试
- [x] MyBatis 数据库仓库和 Flyway 迁移
- [x] H2 自动化数据库测试
- [x] Docker MySQL 真实连接验收
- [x] Python 异步调用 Java
- [x] Python 客户端错误分类和有限重试
- [x] FastAPI lifespan 复用 HTTP 连接池
- [x] 双服务真实 HTTP 集成测试

## 当前接口契约

```http
GET /api/v1/orders/{orderId}
X-Tenant-Id: company_001
X-User-Id: U1001
```

`X-Tenant-Id` 和 `X-User-Id` 仅用于本地学习阶段模拟已认证身份，可以被伪造，不能视为生产级认证。正式版本应由可信网关或 Java 安全组件验证 Token 后获得租户和用户身份。

## 数据库策略

- 默认配置使用 H2 的 MySQL 兼容模式，让自动化测试不依赖人工启动数据库。
- `mysql` Profile 使用真实 MySQL，连接信息全部由环境变量注入。
- Flyway 负责建表和初始化学习数据，禁止依靠人工手动改表维持环境。
- MyBatis Repository 实现数据查询，Service 继续依赖 `OrderRepository` 接口。

## 真实 MySQL 验收结果

```text
Rocky Docker MySQL 8.4.11 -> healthy
Windows -> 192.168.82.128:3306 -> connected
Spring profile -> mysql
Flyway -> V1、V2 applied
GET /api/v1/orders/A1001 -> 200
```

接口成功返回 `SHIPPED`、`cancelable=false`、`refundable=true`，证明请求已经经过 Spring Boot、MyBatis 和真实 MySQL。

## Python 调用验收

```text
Python tests -> 6 passed
Ruff -> All checks passed
Python BusinessServiceClient -> Java HTTP -> 200
Pydantic contract validation -> passed
H2/MySQL database session timezone -> UTC
```

诊断命令：

```powershell
cd agent-service
$env:PYTHONPATH="src"
uv run python scripts\check_business_service.py
```

查询成功：

```json
{
  "orderId": "A1001",
  "productName": "机械键盘",
  "quantity": 1,
  "totalAmount": 299.00,
  "status": "SHIPPED",
  "createdAt": "2026-08-20T10:30:00+08:00",
  "cancelable": false,
  "refundable": true
}
```

订单不存在或不属于当前用户：

```http
HTTP/1.1 404 Not Found
```

```json
{
  "code": "ORDER_NOT_FOUND",
  "message": "订单不存在或当前用户无权访问：A1001",
  "timestamp": "..."
}
```
