# Agent Service

基于 FastAPI、LangChain 与 LangGraph 的 Agent 编排服务，提供结构化意图识别、多租户 RAG、持久化会话、人工审批和 SSE 流式响应能力。

```powershell
uv sync
uv run uvicorn agent_service.main:app --app-dir src --reload
```
