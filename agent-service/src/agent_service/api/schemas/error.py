from datetime import datetime

from pydantic import BaseModel


class ApiErrorResponse(BaseModel):
    code: str
    message: str
    timestamp: datetime
