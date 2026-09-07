from langchain_deepseek import ChatDeepSeek

from agent_service.core.config import Settings


def create_chat_model(settings: Settings) -> ChatDeepSeek:
    if settings.llm_model is None:
        raise ValueError("缺少 AGENT_LLM_MODEL 配置")

    if settings.llm_api_key is None:
        raise ValueError("缺少 AGENT_LLM_API_KEY 配置")

    return ChatDeepSeek(
        model=settings.llm_model,
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=(
            str(settings.llm_base_url) if settings.llm_base_url is not None else None
        ),
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        temperature=(None if settings.llm_thinking_enabled else 0),
        extra_body={
            "thinking": {
                "type": ("enabled" if settings.llm_thinking_enabled else "disabled")
            }
        },
    )
