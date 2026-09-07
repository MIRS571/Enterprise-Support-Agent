import json

from langchain_core.documents import Document

from agent_service.rag.context import format_retrieved_context
from agent_service.rag.retrieval import RetrievedChunk


def make_chunk(
    *,
    content: str,
    section_title: str,
) -> RetrievedChunk:
    return RetrievedChunk(
        document=Document(
            page_content=content,
            metadata={
                "tenant_id": "company_001",
                "document_id": "refund-policy",
                "title": "退款政策",
                "section_title": section_title,
                "version": "1.0",
                "source": "private/path/refund.md",
                "chunk_id": "secret-chunk-id",
            },
        ),
        score=0.91,
    )


def test_format_context_keeps_content_and_minimal_metadata() -> None:
    formatted = format_retrieved_context(
        [
            make_chunk(
                content='订单未发货时可以申请取消。"',
                section_title="未发货订单",
            )
        ]
    )
    payload = json.loads(formatted.text)
    reference = payload["reference_documents"][0]

    assert reference == {
        "reference_number": 1,
        "title": "退款政策",
        "section": "未发货订单",
        "version": "1.0",
        "content": '订单未发货时可以申请取消。"',
    }
    assert "company_001" not in formatted.text
    assert "private/path" not in formatted.text
    assert "secret-chunk-id" not in formatted.text
    assert "0.91" not in formatted.text
    assert formatted.references[0].reference_number == 1


def test_format_context_preserves_reference_number_mapping() -> None:
    formatted = format_retrieved_context(
        [
            make_chunk(
                content="第一块",
                section_title="退款条件",
            ),
            make_chunk(
                content="第二块",
                section_title="退款条件",
            ),
        ]
    )

    assert len(formatted.references) == 2
    assert [reference.reference_number for reference in formatted.references] == [1, 2]


def test_format_context_handles_no_results() -> None:
    formatted = format_retrieved_context([])

    assert formatted.text == ""
    assert formatted.references == ()
