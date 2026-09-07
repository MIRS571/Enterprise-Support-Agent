import pytest

from agent_service.core.redis_keys import RedisKeyBuilder


@pytest.fixture
def key_builder() -> RedisKeyBuilder:
    return RedisKeyBuilder(
        prefix="esa",
        environment="local",
    )


def test_builds_tenant_scoped_order_cache_key(
    key_builder: RedisKeyBuilder,
) -> None:
    key = key_builder.order_cache(
        tenant_id="company_001",
        user_id="U1001",
        order_id="A1001",
    )

    assert key == ("esa:local:cache:order:company_001:U1001:A1001")


def test_builds_identity_scoped_chat_rate_key(
    key_builder: RedisKeyBuilder,
) -> None:
    key = key_builder.chat_rate_limit(
        tenant_id="company_001",
        user_id="U1001",
    )

    assert key == "esa:local:rate:chat:company_001:U1001"


def test_builds_refund_idempotency_key(
    key_builder: RedisKeyBuilder,
) -> None:
    key = key_builder.refund_idempotency(
        tenant_id="company_001",
        user_id="U1001",
        idempotency_key="7e0ed59c-ef00-4d96-9028-46052ef55a82",
    )

    assert key == (
        "esa:local:idempotency:refund:company_001:U1001:"
        "7e0ed59c-ef00-4d96-9028-46052ef55a82"
    )


def test_same_idempotency_key_targets_same_record_for_different_orders(
    key_builder: RedisKeyBuilder,
) -> None:
    first_key = key_builder.refund_idempotency(
        tenant_id="company_001",
        user_id="U1001",
        idempotency_key="request-001",
    )
    second_key = key_builder.refund_idempotency(
        tenant_id="company_001",
        user_id="U1001",
        idempotency_key="request-001",
    )

    assert first_key == second_key


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("tenant_id", "company:001"),
        ("user_id", " "),
        ("order_id", "A1001/other"),
    ],
)
def test_rejects_ambiguous_key_segments(
    key_builder: RedisKeyBuilder,
    field_name: str,
    field_value: str,
) -> None:
    values = {
        "tenant_id": "company_001",
        "user_id": "U1001",
        "order_id": "A1001",
    }
    values[field_name] = field_value

    with pytest.raises(
        ValueError,
        match=field_name,
    ):
        key_builder.order_cache(**values)
