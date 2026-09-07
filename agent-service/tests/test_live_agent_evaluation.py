import asyncio
import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from agent_service.api.schemas.stream import StreamEventType
from agent_service.evaluation import (
    JavaAgentLiveClient,
    LiveEvaluationProtocolError,
    evaluate_live_agent_case,
    load_agent_evaluation_cases,
)


def _sse(event: str, data: dict) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def test_live_client_creates_a_fresh_thread_for_every_run() -> None:
    case = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))[0]
    thread_ids = [
        UUID("95a3ff0f-0fe1-4ed4-b6c4-f0a221403a9a"),
        UUID("4ef141b2-c729-4baa-9246-48f9b67ff46a"),
    ]
    created = 0
    chat_thread_ids: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal created
        assert request.headers["X-Tenant-Id"] == "evaluation_001"
        assert request.headers["X-User-Id"] == "EVAL_U1001"
        if request.url.path == "/api/v1/agent/threads":
            thread_id = thread_ids[created]
            created += 1
            return httpx.Response(
                201,
                json={"thread_id": str(thread_id)},
            )

        payload = json.loads(request.content)
        chat_thread_ids.append(payload["thread_id"])
        body = "".join(
            [
                _sse("metadata", {"thread_id": payload["thread_id"]}),
                _sse("token", {"content": "已发货"}),
                _sse(
                    "result",
                    {
                        "thread_id": payload["thread_id"],
                        "answer": "EVAL-A1001 的订单状态是已发货。",
                        "intent": "order_query",
                        "order_id": "EVAL-A1001",
                        "sources": [],
                    },
                ),
                _sse("done", {"status": "completed"}),
            ]
        )
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text=body,
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://java-service",
        ) as http_client:
            client = JavaAgentLiveClient(http_client)
            first = await client.run_case(case)
            second = await client.run_case(case)

        assert first.event_types == [
            StreamEventType.METADATA,
            StreamEventType.TOKEN,
            StreamEventType.RESULT,
            StreamEventType.DONE,
        ]
        assert first.answer == "EVAL-A1001 的订单状态是已发货。"
        assert evaluate_live_agent_case(case, first).public_contract_passed
        assert evaluate_live_agent_case(case, second).required_facts_passed

    asyncio.run(scenario())

    assert created == 2
    assert chat_thread_ids == [str(thread_id) for thread_id in thread_ids]


def test_live_client_observes_approval_without_resuming_mutation() -> None:
    case = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))[4]
    thread_id = "95a3ff0f-0fe1-4ed4-b6c4-f0a221403a9a"
    requested_paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path.endswith("/threads"):
            return httpx.Response(201, json={"thread_id": thread_id})
        body = "".join(
            [
                _sse("metadata", {"thread_id": thread_id}),
                _sse(
                    "approval_required",
                    {
                        "thread_id": thread_id,
                        "status": "approval_required",
                        "intent": "refund",
                        "order_id": "EVAL-A1001",
                        "approval": {
                            "operation": "request_refund",
                            "order_id": "EVAL-A1001",
                            "product_name": "评测专用机械键盘",
                            "total_amount": "299.00",
                            "status": "SHIPPED",
                        },
                    },
                ),
                _sse("done", {"status": "completed"}),
            ]
        )
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text=body,
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://java-service",
        ) as http_client:
            observation = await JavaAgentLiveClient(http_client).run_case(case)

        result = evaluate_live_agent_case(case, observation)
        assert observation.outcome == "approval_required"
        assert result.public_contract_passed is True

    asyncio.run(scenario())

    assert requested_paths == [
        "/api/v1/agent/threads",
        "/api/v1/agent/chat/stream",
    ]


def test_live_client_compares_sources_at_document_level() -> None:
    case = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))[2]
    thread_id = "95a3ff0f-0fe1-4ed4-b6c4-f0a221403a9a"

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/threads"):
            return httpx.Response(201, json={"thread_id": thread_id})
        sources = [
            {
                "reference_number": reference_number,
                "document_id": "refund-policy",
                "title": "退款政策",
                "section_title": section_title,
                "version": "1.0",
            }
            for reference_number, section_title in enumerate(
                ["七天无理由退货", "已发货订单", "质量问题"],
                start=1,
            )
        ]
        body = "".join(
            [
                _sse("metadata", {"thread_id": thread_id}),
                _sse(
                    "result",
                    {
                        "thread_id": thread_id,
                        "answer": "软件拆封后不支持七天无理由退货。",
                        "intent": "policy_query",
                        "order_id": None,
                        "sources": sources,
                    },
                ),
                _sse("done", {"status": "completed"}),
            ]
        )
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text=body,
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://java-service",
        ) as http_client:
            observation = await JavaAgentLiveClient(http_client).run_case(case)

        assert observation.source_document_ids == ["refund-policy"]
        assert evaluate_live_agent_case(case, observation).public_contract_passed

    asyncio.run(scenario())


def test_live_client_rejects_incomplete_stream() -> None:
    case = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))[3]
    thread_id = "95a3ff0f-0fe1-4ed4-b6c4-f0a221403a9a"

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/threads"):
            return httpx.Response(201, json={"thread_id": thread_id})
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text=_sse("metadata", {"thread_id": thread_id}),
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://java-service",
        ) as http_client:
            with pytest.raises(
                LiveEvaluationProtocolError,
                match="either result or approval_required",
            ):
                await JavaAgentLiveClient(http_client).run_case(case)

    asyncio.run(scenario())
