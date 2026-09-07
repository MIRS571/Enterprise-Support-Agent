import json

from pydantic import BaseModel

from agent_service.api.schemas.stream import StreamEventType


def encode_sse(
    *,
    event: StreamEventType,
    data: BaseModel,
) -> str:
    payload = json.dumps(
        data.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"event: {event.value}\ndata: {payload}\n\n"
