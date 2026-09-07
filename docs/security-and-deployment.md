# 安全清单与部署验收证据

最后更新：2026-09-01

## 1. 验收结论

当前状态：**开发环境核心功能通过，完整容器化部署部分通过，生产安全验收未通过。**

原因很明确：Java、Python 和四个基础设施组件都已有真实运行证据，21 次真实全链路评测也已通过；但 Python 镜像构建和全 Compose 联合启动被主动延期，Java 入口目前仍使用可信身份请求头模拟认证，而不是真实 JWT。

## 2. 最终安全清单

| 检查项 | 状态 | 当前证据或限制 |
| --- | --- | --- |
| Java 负责业务事实和高风险写操作 | 通过 | Python 只能调用 Java API，不能直接修改 MySQL |
| 租户与用户隔离 | 通过 | MySQL 查询和 Qdrant Filter 均在查询阶段限制租户；越权会话统一返回 404 |
| Java → Python 服务鉴权 | 通过 | Agent 路由要求 `X-Internal-Service-Token`，Java WebClient 统一添加该请求头 |
| Python 不直接暴露给外网 | Compose 通过 | `agent-service` 只使用 `expose: 8000`，外部入口为 Java 的 8080 |
| 用户真实认证 | 待生产实现 | Java 当前信任 `X-Tenant-Id`、`X-User-Id`；生产环境必须改为网关或 Spring Security 校验 JWT 后生成可信身份 |
| 高风险退款人工确认 | 通过 | LangGraph `interrupt` 暂停，恢复时只接受明确的 `approved: bool` |
| 退款并发与重复提交 | 通过 | MySQL 条件更新保证原子性，Redis Lua 和幂等 Key 控制重复请求 |
| RAG 无依据时禁止自由回答 | 通过 | 无上下文或 Qdrant 不可用时返回固定提示，不调用模型编造答案 |
| 密钥不进入仓库 | 通过 | `.env` 被 Git 忽略，示例文件只保留占位符，Pydantic 使用 `SecretStr` |
| 密钥轮换 | 待处理 | 曾出现在诊断输出中的 PostgreSQL 密码必须轮换；共享服务令牌也应支持定期轮换 |
| 日志脱敏和请求追踪 | 通过 | Java/Python 共享 UUID `request_id`；日志只记录操作、状态、耗时和错误码，不记录提示词、知识正文或令牌 |
| 错误信息防枚举 | 通过 | 未知、越权、关闭的会话统一为 404，不泄露资源是否真实存在 |
| 限流失败策略 | 通过 | Redis Lua 原子限流；Redis 故障时高成本聊天请求 fail-closed 返回 503 |
| 内部传输加密 | 待生产实现 | 当前实验网络使用 HTTP；生产环境建议内网 TLS 或 mTLS |
| 基础设施网络暴露 | 仅实验环境可接受 | Compose 为调试发布了数据库端口；生产环境应取消 `ports`，只留私有网络，并为 Qdrant 配置认证 |
| 依赖和镜像漏洞扫描 | 未执行 | 上线前应加入 Dependabot/Renovate、Trivy 或同类扫描 |

### 当前信任链

```text
客户端
  → Java：未来由 JWT 验证用户身份
  → Python：共享内部令牌验证调用者是 Java
  → LangGraph：只使用 Java 提供的可信 tenant_id / user_id
  → Java/MySQL：再次执行租户、用户和业务状态校验
```

共享内部令牌只证明调用者是 Java 服务，不能证明最终用户身份，因此不能代替 Java 入口的 JWT。

## 3. 已有部署验收证据

| 层次 | 结果 | 证据 |
| --- | --- | --- |
| MySQL | 通过 | Rocky Linux Docker 容器运行且健康，Java/Flyway 已完成 V1–V3 迁移 |
| Qdrant | 通过 | 容器运行，集合 `enterprise_support_knowledge_hybrid_v1` 可查询，真实 RAG 请求成功 |
| PostgreSQL | 通过 | 容器健康，LangGraph checkpoint 表和 `agent_threads` 已创建，重启后可恢复退款审批 |
| Redis | 通过 | 容器健康且启用密码；缓存、限流、幂等三个真实验收脚本已通过 |
| Java 服务 | 通过 | Java 21 镜像构建成功，容器连接 MySQL/Redis 并通过健康检查 |
| Python 本地服务 | 通过 | FastAPI 生命周期成功连接 Java、PostgreSQL、Redis、Qdrant，并完成真实 SSE 请求 |
| Java → Python SSE | 通过 | 真实链路返回 `metadata → token → result → done` |
| 自动测试 | 通过 | Python Ruff 通过、188 项 pytest 通过；Java 完整 Maven 测试通过 |
| 真实 Agent 稳定性 | 通过 | 7 个案例各运行 3 次，共 21/21；公共契约和必要事实均为 100% |
| Python Docker 镜像 | 延期 | CPU-only 依赖已调整，但镜像构建因下载时间过长被主动跳过 |
| 全 Compose 联合启动 | 未完成 | 必须等 Python 镜像成功后再执行最终健康和 SSE 冒烟测试 |

真实评测报告位于：`agent-service/reports/agent-live-evaluation.json`。

## 4. 最小复验命令

### 代码回归

```powershell
cd agent-service
uv run ruff check .
uv run pytest -q

cd ../business-service
.\mvnw.cmd test
```

### Rocky Linux 基础设施

```bash
cd /home/mirs/enterprise-support-agent/infra
sudo docker compose ps
curl http://127.0.0.1:8080/api/v1/system/info
```

所有服务镜像完成后，再执行最终 Compose 验收：

```bash
sudo docker compose up -d --build
sudo docker compose ps
sudo docker compose exec agent-service \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').read().decode())"
curl http://127.0.0.1:8080/api/v1/system/info
```

最终还应从客户端通过 **Java 8080** 创建会话并发起一次 SSE 请求；不要把 Python 8000 暴露为公网入口。

## 5. 上线前必须完成

1. Java 接入真实 JWT/Spring Security，不再信任外部直接传入的身份头。
2. 轮换已经暴露过的 PostgreSQL 密码，并轮换内部服务令牌。
3. 完成 Python CPU 镜像和全 Compose 冒烟验收。
4. 取消数据库与 Qdrant 的公网端口映射，或使用严格防火墙和认证。
5. 增加依赖、镜像漏洞扫描和 HTTPS/mTLS。
