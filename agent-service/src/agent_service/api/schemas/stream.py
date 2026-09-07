from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class StreamEventType(StrEnum):
    METADATA = "metadata"
    TOKEN = "token"
    RESULT = "result"
    APPROVAL_REQUIRED = "approval_required"
    ERROR = "error"
    DONE = "done"


class StreamMetadata(BaseModel):
    thread_id: str


class StreamToken(BaseModel):
    content: str = Field(min_length=1)


class StreamError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class StreamDone(BaseModel):
    status: Literal["completed"] = "completed"
