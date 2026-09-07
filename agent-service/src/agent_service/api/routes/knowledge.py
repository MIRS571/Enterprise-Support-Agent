from fastapi import APIRouter, Depends, HTTPException, status

from agent_service.api.dependencies import (
    KnowledgeIngestionServiceDep,
    verify_internal_service_token,
)
from agent_service.api.schemas import (
    KnowledgeReindexRequest,
    KnowledgeReindexResponse,
)
from agent_service.services import (
    InvalidTenantIdError,
    KnowledgeCatalogNotFoundError,
)

router = APIRouter(
    prefix="/knowledge",
    tags=["Internal Knowledge"],
    dependencies=[Depends(verify_internal_service_token)],
)


@router.post(
    "/reindex",
    response_model=KnowledgeReindexResponse,
)
def reindex_knowledge(
    request: KnowledgeReindexRequest,
    service: KnowledgeIngestionServiceDep,
) -> KnowledgeReindexResponse:
    try:
        result = service.reindex_tenant(
            tenant_id=request.tenant_id,
        )
    except InvalidTenantIdError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid tenant_id",
        ) from error
    except KnowledgeCatalogNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge catalog was not found",
        ) from error

    return KnowledgeReindexResponse(
        tenant_id=request.tenant_id,
        document_count=result.document_count,
        chunk_count=result.chunk_count,
    )
