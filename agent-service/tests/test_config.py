import pytest
from pydantic import ValidationError

from agent_service.core.config import Settings


def test_checkpoint_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.checkpoint_enabled is False
    assert settings.checkpoint_database_url is None


def test_checkpoint_database_url_is_required_when_enabled() -> None:
    with pytest.raises(
        ValidationError,
        match="checkpoint_database_url is required",
    ):
        Settings(
            _env_file=None,
            checkpoint_enabled=True,
            checkpoint_database_url=None,
        )


def test_checkpoint_database_url_is_kept_secret() -> None:
    settings = Settings(
        _env_file=None,
        checkpoint_enabled=True,
        checkpoint_database_url=(
            "postgresql://agent_checkpoint:secret@127.0.0.1:5432/agent_checkpoint"
        ),
    )

    assert settings.checkpoint_database_url is not None
    assert "secret" not in repr(settings.checkpoint_database_url)
    assert (
        settings.checkpoint_database_url.get_secret_value()
        == "postgresql://agent_checkpoint:secret@127.0.0.1:5432/"
        "agent_checkpoint"
    )


def test_redis_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.redis_enabled is False
    assert settings.redis_url is None


def test_redis_url_is_required_when_enabled() -> None:
    with pytest.raises(
        ValidationError,
        match="redis_url is required",
    ):
        Settings(
            _env_file=None,
            redis_enabled=True,
            redis_url=None,
        )


def test_redis_url_is_kept_secret() -> None:
    settings = Settings(
        _env_file=None,
        redis_enabled=True,
        redis_url="redis://:secret@127.0.0.1:6379/0",
    )

    assert settings.redis_url is not None
    assert "secret" not in repr(settings.redis_url)


def test_evaluation_environment_template_keeps_rate_limiting_enabled() -> None:
    settings = Settings(_env_file=".env.evaluation.example")

    assert settings.environment == "evaluation"
    assert settings.chat_rate_limit_requests == 50
    assert settings.chat_rate_limit_window_seconds == 60


def test_rag_candidate_count_cannot_be_smaller_than_final_count() -> None:
    with pytest.raises(
        ValidationError,
        match="rag_candidate_k must be at least rag_top_k",
    ):
        Settings(
            _env_file=None,
            rag_top_k=5,
            rag_candidate_k=3,
        )
