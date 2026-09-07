# 最终演示流程

这份流程用于开发环境或面试演示。它复用已经验证过的运行方式：Rocky Linux 运行基础设施，Windows 本地运行 Java 和 Python。它不代表完整生产部署。

## 1. 演示目标

用 5–8 分钟展示四件事：

1. Java 是客户端唯一业务入口。
2. Agent 能区分订单查询和企业政策 RAG。
3. SSE 能逐步返回公开 token 与最终结构化结果。
4. 退款会通过 LangGraph `interrupt/resume` 暂停和恢复。

默认在恢复步骤选择拒绝退款，避免修改数据库，使演示可重复执行。真实批准、MySQL 更新和 Redis 幂等已有单独验收记录。

## 2. 启动前检查

Rocky Linux：

```bash
cd /home/mirs/enterprise-support-agent/infra
sudo docker compose ps
```

预期 MySQL、Qdrant、PostgreSQL、Redis 均为运行状态，带健康检查的服务应显示 `healthy`。

Windows 本地配置必须满足：

- Java 与 Python 的 `AGENT_INTERNAL_SERVICE_TOKEN` 完全相同。
- Java 使用 MySQL Profile，并指向虚拟机 MySQL 和 Redis。
- Python 启用 Checkpoint、Redis、RAG，并指向虚拟机 PostgreSQL、Redis 和 Qdrant。
- DeepSeek API Key 只存在私有环境文件或 IDE 环境变量中。

不要把任何真实密码或 API Key 复制到演示截图、README 或 Git。

## 3. 启动顺序

先启动 Java：

```powershell
cd business-service
.\mvnw.cmd spring-boot:run
```

再启动 Python：

```powershell
cd agent-service
uv run uvicorn agent_service.main:app --app-dir src `
  --loop agent_service.core.event_loop:selector_event_loop_factory
```

启动成功的最低判断：

- Java：`GET http://127.0.0.1:8080/actuator/health` 返回 `UP`。
- Python：`GET http://127.0.0.1:8000/api/v1/health` 返回服务状态；RAG、Redis 启用时不能被静默伪装为正常。
- 演示请求始终从 Java 8080 进入，不直接调用 Python Agent 路由。

## 4. 按顺序运行 API

使用 IntelliJ IDEA 或 PyCharm 的 HTTP Client 打开根目录 [`requests.http`](../requests.http)，依次运行：

1. **Java 健康检查**：证明公共入口运行。
2. **创建 Agent 会话**：Java 调用 Python，Python 在 PostgreSQL 创建归属记录；脚本自动保存 `thread_id`。
3. **政策咨询 SSE**：展示 `policy_query`、逐步 token 和结构化 `sources`。
4. **退款请求 SSE**：展示 `approval_required`，此时订单尚未改变。
5. **拒绝退款并恢复**：Java 转发 `approved: false`，LangGraph 从原 Checkpoint 恢复并结束，不执行 MySQL 退款。

演示时重点观察 SSE 事件顺序：

```text
metadata → token... → result → done
```

退款暂停路径应为：

```text
metadata → approval_required → done
```

## 5. 如何安全演示真实批准

仅在隔离且可以重置的测试数据库中，把恢复请求改为：

```json
{
  "approved": true
}
```

为一笔新的业务操作生成一个新的 `Idempotency-Key`；同一次操作因超时而重试时必须继续使用原 Key。不要为了重试生成新 Key。

预期结果：

- 第一次成功把符合条件的订单更新为 `REFUNDING`。
- 同一个 Key 和同一请求返回已保存结果，不重复更新 MySQL。
- 同一个 Key 用于不同订单返回 409。

## 6. 演示失败时的快速定位

| 现象 | 优先检查 |
| --- | --- |
| Java 启动提示 internal token 缺失 | Java 环境中是否配置与 Python 相同的令牌 |
| Python 启动失败 | PostgreSQL/Redis/Qdrant 地址、密码和 Windows Selector event loop |
| Java 调用 Agent 返回 401 | Java 和 Python 内部令牌是否一致 |
| 创建会话返回 503 | PostgreSQL Checkpointer 和 `agent_threads` 是否可用 |
| 政策问答固定降级 | Qdrant、集合、知识索引和 tenant_id 是否正确 |
| 第 11 次聊天返回 429 | Redis 限流正常生效；等待窗口恢复或使用新的测试身份 |
| 退款恢复返回 400 | 是否携带 `Idempotency-Key` |
| 退款恢复返回 404 | thread 是否属于当前 tenant/user，或是否已关闭 |
| 退款恢复返回 409 | 是否不存在待审批 interrupt，或订单状态已经变化 |

## 7. 演示结束时的准确结论

可以表述：

> 项目已完成本地双服务、四类基础设施、真实 SSE、持久会话、RAG、退款审批和 21 次全链路模型评测。

不能表述：

> 项目已经完成生产部署。

Python 镜像与全 Compose 联合验收仍然延期，JWT、密钥轮换、TLS 和生产私有网络也仍是上线前工作。
