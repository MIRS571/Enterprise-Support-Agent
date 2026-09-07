import asyncio

import httpx

from agent_service.main import app


def test_health() -> None:
    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)

        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport,
                base_url="http://test-server",
            ) as client,
        ):
            return await client.get("/api/v1/health")

    response = asyncio.run(scenario())

    assert response.status_code == 200
    assert response.json() == {
        "service": "agent-service",
        "status": "DEGRADED",
        "environment": "local",
        "components": {
            "rag": {
                "status": "DISABLED",
            },
            "redis": {
                "status": "DISABLED",
            },
        },
    }
