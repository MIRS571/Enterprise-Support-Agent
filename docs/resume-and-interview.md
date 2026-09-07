# 简历描述与面试讲解

## 1. 简历项目名称

**企业级电商售后智能 Agent｜Spring Boot + LangGraph + RAG**

不要写成“调用大模型接口实现智能客服”，这无法体现架构和工程能力。

## 2. 项目简介

设计并实现面向电商售后的双服务智能 Agent：以 Spring Boot 管理订单事实、退款规则和高风险写操作，以 FastAPI/LangGraph 编排意图识别、业务工具、企业知识 RAG、多轮记忆与人工审批，并通过 Redis、PostgreSQL、Qdrant 和 SSE 完成可靠性与流式交互建设。

## 3. 可直接使用的简历要点

- 设计 Java/Python 双服务边界，将模型推理与订单业务解耦；由 Java 统一执行租户/用户范围查询、退款资格校验和 MySQL 原子状态更新，避免 Agent 绕过业务规则。
- 基于 LangGraph 实现条件路由、PostgreSQL Checkpointer、多轮订单上下文和 `interrupt/resume` 退款审批；验证进程重启后仍能恢复原流程，并阻止跨用户会话接管。
- **检索优化：**针对纯 Dense 检索中政策文档排名不稳定的问题，负责升级 RAG 召回链路，在 Qdrant 中维护命名 Dense/BM25 向量，先按 `tenant_id` Filter 双路召回，再用 RRF 融合与 BAAI Cross-Encoder 重排；30 条真实案例中 Hit@3 从 96.30% 提升到 100%，MRR@3 从 0.8704 提升到 1.0000，跨租户泄漏为 0。
- **测评性能：**针对 Agent/RAG 效果难以凭感觉判断的问题，设计 Dense、Hybrid、Hybrid + Cross-Encoder 三组同口径评测，统计 Hit@3、MRR@3、nDCG@3、租户泄漏和延迟；发现重排能补齐弱召回但带来 CPU P95 370.387 ms 延迟，为后续按场景启用重排提供依据。
- 使用 Redis 实现 15 秒订单缓存、Lua 原子限流和退款幂等状态机，区分缓存降级、限流 fail-closed、幂等冲突及写入结果未知等故障语义。
- 通过 FastAPI SSE 与 Spring WebClient/Flux 实现端到端流式转发，只输出公开事件并传播取消；为 Java/Python 请求链加入统一 `request_id` 和内部服务鉴权。
- 建立受控依赖评测与真实模型稳定性评测，覆盖意图、路由、工具调用、RAG、身份越权、无依据回答和退款审批；最终 7 个场景各运行 3 次，共 21/21 通过。

根据简历篇幅选择其中 3–4 条，不要全部堆入一页简历。

## 4. 一分钟介绍

> 这是一个电商售后智能 Agent。我的核心设计是把 AI 的不确定推理和业务系统的确定性规则分开：Java 服务负责用户身份、订单事实、退款资格和最终写操作，Python 使用 LangChain、LangGraph 做意图识别、工具调用、RAG 和多轮流程。政策问答通过 Qdrant 按租户检索，退款通过 LangGraph interrupt 暂停并在用户确认后恢复，Java 再使用 Redis 幂等和 MySQL 条件更新保证只执行一次。系统支持 Java 到 Python 的 SSE 流式转发，并建立了受控测试和 21 次真实全链路评测。当前开发环境核心功能通过，但 JWT、完整容器验收和生产网络加固仍被明确列为上线前工作。

## 5. 三分钟介绍顺序

1. **业务问题**：普通聊天机器人可能编造订单或越权执行退款。
2. **架构决策**：Java 管业务真相，Python 管 AI 编排；Agent 只能通过 Java 工具访问订单。
3. **LangGraph**：State 保存流程数据，条件边选择订单/RAG/退款路径，PostgreSQL 支持恢复。
4. **RAG**：Qdrant 查询时直接按租户过滤；无上下文固定降级；返回结构化来源。
5. **高风险操作**：退款先查资格，再 interrupt，恢复后使用 Redis 幂等和 MySQL 原子更新。
6. **用户体验**：Python SSE 生成 token，Java Flux 逐条转发，不把内部推理暴露给用户。
7. **证据**：188 项 Python 测试、Java 完整测试、RAG 对照指标和 21/21 真实评测。
8. **局限**：JWT、Python 镜像全 Compose、TLS/私有网络和漏洞扫描仍需生产加固。

## 6. 高频面试问题

### 为什么不全部使用 Python？

订单、金额和退款属于确定性业务，已有 Java 生态更适合承载事务、权限和业务规则；Python 负责快速接入模型与 Agent 框架。拆分后可以独立发布和降级。

### LangChain 和 LangGraph 分别做什么？

LangChain 主要提供模型、Prompt、结构化输出、Tool 和 RAG 组件；LangGraph 负责把这些能力组织成有状态、可路由、可暂停恢复的工作流。

### 为什么有了 Checkpointer 还要 `agent_threads` 表？

Checkpoint 保存内部图状态，但公开 thread ID 的租户/用户归属、状态和内部 checkpoint key 需要独立管理，才能在读取状态前完成权限过滤并避免会话枚举。

### 为什么 Redis 不能保存最终订单状态？

Redis 保存的是可过期或可重建的高频状态；MySQL 才是订单事实来源。否则缓存丢失或过期会影响金融和退款正确性。

### 为什么退款超时不能直接重试？

请求超时时 Java 可能已经提交 MySQL 更新。没有幂等保护直接重试可能重复执行，因此系统区分“明确失败”和“结果未知”。

### 如何防止 RAG 跨企业泄漏？

把 `tenant_id` 作为 Qdrant Filter 放进向量查询本身，而不是先检索全部数据再在 Python 中过滤。

### 项目能直接上生产吗？

不能。开发环境核心能力和评测已经通过，但真实 JWT、密钥轮换、Python 全容器验收、私有网络、TLS/mTLS 和漏洞扫描仍需要完成。

## 7. 不应写入简历的表述

- “实现了完全可靠、零幻觉的 Agent”。
- “已经达到生产级部署”，因为完整容器和生产安全尚未验收。
- “使用了微调”，当前没有测量结果证明需要微调。
- “实现多 Agent 协作”，当前核心架构是一个可控 LangGraph 工作流。
- “RAG 准确率 100%”，应明确评测口径：30 条检索案例（27 条正向、3 条未知租户隔离）中，Hybrid + Cross-Encoder 的 Hit@3/MRR@3 均为 100%；这不是通用准确率。
