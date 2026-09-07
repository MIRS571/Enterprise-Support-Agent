# 架构与请求流程

## 1. 架构原则

系统最重要的设计不是“调用了大模型”，而是把不确定能力和确定性业务分开：

- Java 持有用户身份、订单事实、业务规则和高风险写操作。
- Python 负责理解自然语言、检索知识和编排工作流。
- 模型可以提出调用意图，但不能直接修改数据库或决定退款是否成功。

这样即使模型产生幻觉，最终业务结果仍受 Java、MySQL 和幂等机制约束。

## 2. 组件职责

| 组件 | 主要职责 | 不承担的职责 |
| --- | --- | --- |
| Spring Boot | 对外入口、订单查询、退款规则、幂等和 SSE 转发 | 不负责大模型推理 |
| FastAPI | Agent API、生命周期和依赖组织 | 不持有订单真相 |
| LangChain | 模型连接、结构化输出和 Tool Calling | 不定义完整业务流程 |
| LangGraph | State、节点、路由、Checkpoint、暂停与恢复 | 不代替 Java 业务校验 |
| MySQL | 订单事实和原子状态更新 | 不保存对话记忆 |
| Qdrant | 向量与租户过滤检索 | 不保存业务订单 |
| PostgreSQL | Checkpoint 和会话归属 | 不作为订单数据库 |
| Redis | 缓存、限流和幂等临时状态 | 不作为最终业务真相 |

## 3. 公共请求入口

```text
客户端
  │
  │ Authorization: Bearer <JWT>（生产目标）
  ▼
Java
  1. 验证最终用户身份
  2. 生成或校验 request_id
  3. 提取可信 tenant_id / user_id
  4. 添加 Java→Python 内部服务令牌
  ▼
Python
  5. 校验内部服务令牌
  6. 校验会话归属和用户限流
  7. 调用 LangGraph
```

当前开发环境使用身份请求头模拟第 1–3 步，因此只适合可信网络测试，不能直接描述为完整生产认证。

## 4. LangGraph 执行流程

每次请求先创建只包含原始消息和必要默认值的 State；`tenant_id`、`user_id`、服务客户端等可信对象通过 Runtime Context 进入节点，不从用户消息中提取。

```text
START
  ↓
analyze_intent
  ├── 信息不足 → request_clarification → save_turn → END
  ├── 不支持   → unsupported → save_turn → END
  ├── 订单查询 → query_order
  │               ├── 找到 → generate_answer → save_turn → END
  │               └── 404  → order_not_found → save_turn → END
  ├── 政策咨询 → retrieve_knowledge
  │               └── generate_knowledge_answer → save_turn → END
  └── 退款申请 → prepare_refund → interrupt
                                  ↓ resume
                                execute_refund → save_turn → END
```

Checkpoint 保存可序列化 State。公开 `thread_id` 先经过 PostgreSQL 中 tenant/user 归属查询，再转换为内部 checkpoint key，客户端不能自己选择 Checkpoint 命名空间。

## 5. RAG 数据流

### 写入

```text
企业文档目录
  → catalog 校验路径与元数据
  → Markdown 感知切分
  → 生成稳定 chunk_id
  → 本地 Embedding
  → Qdrant 写入向量 + tenant_id/document_id/version 等元数据
```

重新索引采用按文档替换：先验证新数据，再删除该租户该文档的旧 chunks，避免不同版本混在一起。

### 查询

```text
用户问题 → Dense + BM25 双路召回（Qdrant tenant Filter）
        → RRF 融合 → Cross-Encoder 重排 → Top K Document
        → 格式化知识上下文和引用编号
        → 模型生成回答 → 返回结构化 sources
```

无结果或 Qdrant 不可用时使用固定提示，不能让模型脱离知识上下文自由回答企业政策。

## 6. 退款安全流程

```text
1. 模型识别退款意图并提取 order_id
2. Python 使用可信 tenant/user 调用 Java 查询订单
3. LangGraph interrupt 返回最小审批信息
4. 用户提交 approved 和 Idempotency-Key
5. Python 从原 Checkpoint 恢复，不接受客户端重新提交 order_data
6. Java Redis Lua 原子声明幂等请求
7. MySQL 条件 UPDATE 执行一次状态迁移
8. Java 保存完成结果；Python 清理订单缓存并返回
```

Redis 失败发生在写操作前时返回 503；MySQL 已可能成功但幂等结果保存失败时返回 504“结果未知”，不能擅自重试并假定失败。

## 7. SSE 数据流

Python 只允许以下公开事件：

```text
metadata
token
result | approval_required | error
done
```

LangGraph 内部分析消息、工具参数和 RAG 原文不会作为 token 输出。Java 返回 `Flux<ServerSentEvent<String>>`，不在生产代码中调用 `block()`、`collectList()` 或手动 `subscribe()`，由 Spring 在客户端订阅时逐条转发。

## 8. 故障策略

| 故障 | 行为 |
| --- | --- |
| Java 订单 404 | 返回不枚举资源的 404 |
| Java 连接超时 | 查询可按策略处理；退款写操作不自动重试 |
| Qdrant 不可用 | 政策问答固定降级，订单查询继续可用，健康状态 DEGRADED |
| Redis 缓存不可用 | 绕过缓存，继续查询 Java |
| Redis 限流不可用 | fail-closed，聊天返回 503 |
| PostgreSQL 不可用 | 持久会话模式启动失败，不伪装成可恢复服务 |
| SSE 已开始后出错 | 发送公开 `error` 事件，不泄露内部异常 |

## 9. 可观测性和信任边界

- Java 生成或校验 UUID `request_id`，并沿 Java → Python → Java 工具调用传递。
- 日志只记录 `request_id`、操作名、HTTP 状态、耗时和稳定错误码。
- Python Agent 路由要求内部服务令牌；Compose 不向宿主机发布 Python 8000。
- 日志和评测报告不保存密钥、完整提示词、知识正文或完整用户回答。
