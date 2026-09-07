from pydantic import BaseModel, Field


class KnowledgeReindexRequest(BaseModel):
    tenant_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
    )


class KnowledgeReindexResponse(BaseModel):
    tenant_id: str
    document_count: int
    chunk_count: int
