import os

os.environ.setdefault("AGENT_LLM_MODEL", "deepseek-v4-flash")
os.environ.setdefault("AGENT_LLM_API_KEY", "test-key")
os.environ.setdefault("AGENT_LLM_BASE_URL", "https://api.deepseek.com")
os.environ.setdefault("AGENT_LLM_THINKING_ENABLED", "false")
os.environ.setdefault("AGENT_RAG_ENABLED", "false")
os.environ.setdefault("AGENT_CHECKPOINT_ENABLED", "false")
os.environ.setdefault("AGENT_REDIS_ENABLED", "false")
os.environ.setdefault(
    "AGENT_INTERNAL_SERVICE_TOKEN",
    "test-internal-service-token-1234567890",
)
