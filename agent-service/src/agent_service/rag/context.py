import json
from dataclasses import dataclass

from agent_service.rag.retrieval import RetrievedChunk


@dataclass(frozen=True)
class KnowledgeReference:
    reference_number: int
    document_id: str
    title: str
    section_title: str | None
    version: str


@dataclass(frozen=True)
class FormattedKnowledgeContext:
    text: str
    references: tuple[KnowledgeReference, ...]


def required_metadata(
    chunk: RetrievedChunk,
    key: str,
) -> str:
    value = chunk.document.metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Retrieved document has invalid metadata: {key}")
    return value.strip()


def format_retrieved_context(
    chunks: list[RetrievedChunk],
) -> FormattedKnowledgeContext:
    if not chunks:
        return FormattedKnowledgeContext(
            text="",
            references=(),
        )

    reference_documents: list[dict[str, object]] = []
    references: list[KnowledgeReference] = []

    for reference_number, chunk in enumerate(chunks, start=1):
        content = chunk.document.page_content.strip()
        if not content:
            raise ValueError("Retrieved document content cannot be blank")

        document_id = required_metadata(chunk, "document_id")
        title = required_metadata(chunk, "title")
        version = required_metadata(chunk, "version")
        section_value = chunk.document.metadata.get("section_title")
        section_title = (
            section_value.strip()
            if isinstance(section_value, str) and section_value.strip()
            else None
        )

        reference_documents.append(
            {
                "reference_number": reference_number,
                "title": title,
                "section": section_title,
                "version": version,
                "content": content,
            }
        )

        references.append(
            KnowledgeReference(
                reference_number=reference_number,
                document_id=document_id,
                title=title,
                section_title=section_title,
                version=version,
            )
        )

    context_text = json.dumps(
        {
            "reference_documents": reference_documents,
        },
        ensure_ascii=False,
        indent=2,
    )
    return FormattedKnowledgeContext(
        text=context_text,
        references=tuple(references),
    )
