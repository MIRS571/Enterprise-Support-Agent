# Agent Service

Python AI 服务。第一天仅提供健康检查，后续逐步加入 LangChain、LangGraph、RAG、checkpoint 和 SSE。

```powershell
uv sync
uv run uvicorn agent_service.main:app --app-dir src --reload
```
