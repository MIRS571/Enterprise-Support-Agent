# Enterprise Support Agent

面向电商售后场景的企业级智能客服 Agent。系统支持订单查询、企业政策问答、多轮会话和退款人工确认，并将大模型的不确定推理与 Java 的确定性业务规则分离。

项目不是单个 LangChain Demo：客户端统一访问 Java，Python 使用 LangGraph 编排模型、RAG 和业务工具，MySQL、Qdrant、PostgreSQL、Redis 分别承担业务事实、向量检索、持久记忆和高频临时状态。

## 项目亮点

- **Java/Python 职责隔离**：Spring Boot 管理订单事实、权限边界和退款写操作；FastAPI 管理模型、RAG 与 Agent 工作流。
- **可恢复 LangGraph 工作流**：PostgreSQL Checkpointer 保存会话状态，退款通过 `interrupt` 暂停，进程重启后仍可由原用户恢复。
- **检索优化**：针对纯 Dense 检索中政策文档排名不稳定的问题，将 RAG 升级为 Qdrant 命名 Dense/BM25 向量、`tenant_id` Filter、RRF 融合和 Cross-Encoder 重排，最终 Hit@3 从 96.30% 提升至 100%，MRR@3 从 0.8704 提升至 1.0000。
- **Redis 工程化能力**：实现订单缓存、Lua 原子限流和退款幂等；不同故障分别采用降级或 fail-closed 策略。
- **端到端 SSE**：Python 流式产生公开事件，Java 使用 WebClient/Flux 无缓冲转发，并保留请求前错误状态。
- **测评与性能**：建立 Dense、Hybrid、Hybrid + Cross-Encoder 三组同口径评测，统计 Hit@3、MRR@3、nDCG@3、租户泄漏和延迟；记录 CPU 重排 P95 延迟 370.387 ms，为按场景启用重排提供依据。
- **安全与可观测性**：可信身份不从自然语言提取；Java/Python 使用内部服务令牌和同一 `request_id`，日志不保存提示词、知识正文或密钥。

## 总体架构

```text
客户端
  │  JWT（生产目标；当前开发环境使用可信身份头）
  ▼
Java business-service :8080
  ├── MySQL：订单事实与原子退款状态迁移
  ├── Redis：退款幂等
  └── WebClient / Flux
          │  tenant_id + user_id + internal token + request_id
          ▼
Python agent-service :8000（仅内部访问）
  ├── LangChain：结构化模型调用与 Tool Calling
  ├── LangGraph：状态、条件路由、记忆、interrupt/resume
  ├── Qdrant：多租户知识检索
  ├── PostgreSQL：Checkpoint 与会话归属
  ├── Redis：订单缓存与聊天限流
  └── DeepSeek：意图识别和有依据的回答生成
```

详细执行流程见 [架构说明](docs/architecture.md)。

## 核心业务流程

### 订单查询

```text
用户问题 → 意图识别 → 提取订单号 → Java 查询真实订单
        → 生成有业务事实约束的回答 → SSE 返回
```

### 企业政策问答

```text
用户问题 → policy_query → Qdrant 按 tenant_id 检索
        → 格式化知识上下文 → 模型生成带来源回答
        → 没有可靠上下文时返回固定提示
```

### 退款申请

```text
退款意图 → Java 查询订单资格 → LangGraph interrupt
        → 用户明确批准 → 从 PostgreSQL Checkpoint 恢复
        → Java Redis 幂等校验 + MySQL 原子更新 → 返回结果
```

## 技术栈

| 层次 | 技术 |
| --- | --- |
| Java 业务服务 | Java 21、Spring Boot、Spring MVC、WebClient/Flux、MyBatis、Flyway |
| Python Agent 服务 | Python 3.12、FastAPI、LangChain、LangGraph、Pydantic、HTTPX |
| 模型与 RAG | DeepSeek、Hugging Face Embedding、FastEmbed BM25、Qdrant、BAAI Cross-Encoder |
| 数据与状态 | MySQL、PostgreSQL、Redis |
| 工程化 | Docker Compose、pytest、Ruff、JUnit、Maven |

## 目录结构

```text
enterprise-support-agent/
├── business-service/       # Java 业务事实、退款和 Agent 网关
├── agent-service/          # FastAPI、LangChain、LangGraph、RAG、评测
├── infra/                  # 六个服务的 Docker Compose 配置
├── docs/                   # 架构、阶段总结、安全与面试材料
└── requests.http           # 开发环境 HTTP 示例
```

## 最小启动说明

先从示例文件创建私有环境配置，所有示例密码和令牌都必须替换，真实 `.env` 不得提交。

基础设施与容器化说明见 [infra/README.md](infra/README.md)。本地调试时需要保证 Java 和 Python 的 `AGENT_INTERNAL_SERVICE_TOKEN` 完全相同。

Python：

```powershell
cd agent-service
uv sync
uv run uvicorn agent_service.main:app --app-dir src `
  --loop agent_service.core.event_loop:selector_event_loop_factory
```

Java：

```powershell
cd business-service
.\mvnw.cmd spring-boot:run
```

开发环境健康检查：

- Java：<http://127.0.0.1:8080/actuator/health>
- Java 服务信息：<http://127.0.0.1:8080/api/v1/system/info>
- Python 本地调试：<http://127.0.0.1:8000/api/v1/health>

生产拓扑中客户端只应访问 Java 8080，Python 8000 不应成为公网入口。

## 测试与评测

```powershell
cd agent-service
uv run ruff check .
uv run pytest -q

cd ../business-service
.\mvnw.cmd test
```

当前已验证证据：

| 项目 | 结果 |
| --- | ---: |
| Python 自动测试 | 188 passed |
| Java 自动测试 | 32 passed |
| RAG Dense 基线 Hit@3 | 96.30% |
| RAG Dense 基线 MRR@3 | 0.8704 |
| RAG Hybrid + Cross-Encoder Hit@3 | 100% |
| RAG Hybrid + Cross-Encoder MRR@3 | 1.0000 |
| RAG 跨租户泄漏 | 0 |
| 真实 Agent 稳定性 | 21/21，公共契约与必要事实均为 100% |

真实 Agent 评测报告：[agent-live-evaluation.json](agent-service/reports/agent-live-evaluation.json)。
检索对照报告：[retrieval-hybrid-evaluation.json](agent-service/reports/retrieval-hybrid-evaluation.json)。

## 安全边界与当前限制

- 开发环境以 `X-Tenant-Id`、`X-User-Id` 模拟 Java 已验证的身份；生产环境必须由 Spring Security/网关验证 JWT 后生成身份上下文。
- Java → Python 的共享内部令牌只证明调用者是 Java，不能代替最终用户认证。
- 生产部署前应使用独立强密码，并建立统一的密钥轮换机制。
- Python CPU 镜像和全 Compose 联合验收仍为延期状态，不能声称已经完成生产部署。
- 生产环境还需要私有基础设施网络、TLS/mTLS、Qdrant 认证和依赖/镜像漏洞扫描。

完整清单见 [安全与部署验收](docs/security-and-deployment.md)。

## 延伸文档

- [最终演示流程](docs/demo-walkthrough.md)
- [架构与请求流程](docs/architecture.md)
- [混合检索与重排评测](docs/evaluation/retrieval-hybrid-rerank.md)
- [安全与部署验收](docs/security-and-deployment.md)
