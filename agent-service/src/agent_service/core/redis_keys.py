import re
from dataclasses import dataclass

_KEY_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _validated_segment(
    value: str,
    *,
    name: str,
) -> str:
    cleaned_value = value.strip()
    if not _KEY_SEGMENT_PATTERN.fullmatch(cleaned_value):
        raise ValueError(
            f"{name} must contain only letters, numbers, underscores, or hyphens"
        )
    return cleaned_value


@dataclass(frozen=True, slots=True)
class RedisKeyBuilder:
    prefix: str
    environment: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "prefix",
            _validated_segment(
                self.prefix,
                name="prefix",
            ),
        )
        object.__setattr__(
            self,
            "environment",
            _validated_segment(
                self.environment,
                name="environment",
            ),
        )

    def order_cache(
        self,
        *,
        tenant_id: str,
        user_id: str,
        order_id: str,
    ) -> str:
        return self._join(
            "cache",
            "order",
            _validated_segment(tenant_id, name="tenant_id"),
            _validated_segment(user_id, name="user_id"),
            _validated_segment(order_id, name="order_id"),
        )

    def chat_rate_limit(
        self,
        *,
        tenant_id: str,
        user_id: str,
    ) -> str:
        return self._join(
            "rate",
            "chat",
            _validated_segment(tenant_id, name="tenant_id"),
            _validated_segment(user_id, name="user_id"),
        )

    def refund_idempotency(
        self,
        *,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
    ) -> str:
        return self._join(
            "idempotency",
            "refund",
            _validated_segment(tenant_id, name="tenant_id"),
            _validated_segment(user_id, name="user_id"),
            _validated_segment(
                idempotency_key,
                name="idempotency_key",
            ),
        )

    def _join(self, *segments: str) -> str:
        return ":".join(
            (
                self.prefix,
                self.environment,
                *segments,
            )
        )
