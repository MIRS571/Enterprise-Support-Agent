import asyncio

import httpx

from agent_service.core.config import get_settings
from agent_service.integrations.business_service import BusinessServiceClient
from agent_service.integrations.llm import create_chat_model
from agent_service.services import AnswerGenerator, IntentAnalyzer
from agent_service.tools import create_get_order_tool

MESSAGE = "订单A1001为什么还没收到？"


async def main() -> None:
    settings = get_settings()
    model = create_chat_model(settings)
    analyzer = IntentAnalyzer(model)
    answer_generator = AnswerGenerator(model)

    analysis = await analyzer.analyze(MESSAGE)
    print("意图分析：", analysis.model_dump(mode="json"))

    async with httpx.AsyncClient(
        base_url=str(settings.business_service_base_url),
        timeout=httpx.Timeout(settings.business_service_timeout_seconds),
        trust_env=False,
    ) as http_client:
        raw_response = await http_client.get(
            "/api/v1/orders/A1001",
            headers={
                "X-Tenant-Id": "company_001",
                "X-User-Id": "U1001",
            },
        )
        print(
            "原始Java响应：",
            raw_response.url,
            raw_response.status_code,
            raw_response.text,
        )

        business_client = BusinessServiceClient(
            http_client=http_client,
            max_retries=settings.business_service_max_retries,
        )
        order_tool = create_get_order_tool(
            client=business_client,
            tenant_id="company_001",
            user_id="U1001",
        )
        order_data = await order_tool.ainvoke(
            {
                "order_id": analysis.order_id,
            }
        )
        print("订单工具：", order_data)

    answer = await answer_generator.generate(
        message=MESSAGE,
        order_data=order_data,
    )
    print("最终回答：", answer)


if __name__ == "__main__":
    asyncio.run(main())
