import asyncio

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
                "thread_id": "thread_day4_check",
                "message": "订单A1001为什么还没收到？",
            },
        )

    print(f"HTTP {response.status_code}")
    print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
