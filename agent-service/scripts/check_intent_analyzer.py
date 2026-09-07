import asyncio

from agent_service.core.config import get_settings
from agent_service.integrations.llm import create_chat_model
from agent_service.services import IntentAnalyzer

EXAMPLE_MESSAGES = [
    "帮我查一下订单A1001为什么还没收到",
    "我想申请退款",
    "你们物流太慢了，我要投诉订单B2001",
]


async def main() -> None:
    settings = get_settings()
    model = create_chat_model(settings)
    analyzer = IntentAnalyzer(model)

    for message in EXAMPLE_MESSAGES:
        result = await analyzer.analyze(message)
        print(f"用户消息：{message}")
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
