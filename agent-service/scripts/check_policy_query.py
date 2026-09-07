import asyncio
import json

import httpx

from agent_service.main import app


async def main() -> None:
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=transport,
            base_url="http://test-server",
        ) as client,
    ):
        response = await client.post(
            "/api/v1/agent/chat",
            headers={
                "X-Tenant-Id": "company_001",
                "X-User-Id": "U1001",
            },
            json={
                "thread_id": "rag_acceptance_001",
                "message": "已经拆封的软件支持无理由退款吗？",
            },
        )

    response.raise_for_status()
    result = response.json()

    if result["intent"] != "policy_query":
        raise RuntimeError(
            f"Unexpected intent: {result['intent']}"
        )
    if "[资料" not in result["answer"]:
        raise RuntimeError("知识库回答缺少资料引用")
    if "不支持" not in result["answer"]:
        raise RuntimeError("知识库回答与验收政策不符")
    if not result["sources"]:
        raise RuntimeError("知识库回答缺少结构化来源")
    if result["sources"][0]["reference_number"] < 1:
        raise RuntimeError("知识来源编号无效")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
