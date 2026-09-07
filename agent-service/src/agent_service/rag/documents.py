from datetime import date
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from pydantic import BaseModel, Field

HEADERS_TO_SPLIT_ON = [
    ("#", "markdown_title"),
    ("##", "section_title"),
]


class KnowledgeDocumentEntry(BaseModel):
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source: str = Field(min_length=1)
    version: str = Field(min_length=1)
    effective_date: date


class KnowledgeCatalog(BaseModel):
    tenant_id: str = Field(min_length=1)
    documents: list[KnowledgeDocumentEntry] = Field(min_length=1)


def build_chunk_id(
    *,
    tenant_id: str,
    document_id: str,
    chunk_index: int,
) -> str:
    stable_name = f"{tenant_id}:{document_id}:{chunk_index}"
    return str(uuid5(NAMESPACE_URL, stable_name))


def load_and_split_catalog(
    catalog_path: Path,
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
) -> list[Document]:
    catalog = KnowledgeCatalog.model_validate_json(
        catalog_path.read_text(encoding="utf-8")
    )
    catalog_directory = catalog_path.parent.resolve()
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=False,
    )
    length_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    all_chunks: list[Document] = []

    for entry in catalog.documents:
        source_path = (catalog_directory / entry.source).resolve()
        try:
            source_path.relative_to(catalog_directory)
        except ValueError as error:
            raise ValueError(f"知识文档不能位于目录清单之外：{entry.source}") from error

        markdown = source_path.read_text(encoding="utf-8")
        section_documents = markdown_splitter.split_text(markdown)
        for section in section_documents:
            section.metadata.update(
                {
                    "tenant_id": catalog.tenant_id,
                    "document_id": entry.document_id,
                    "title": entry.title,
                    "source": entry.source,
                    "version": entry.version,
                    "effective_date": entry.effective_date.isoformat(),
                }
            )

        document_chunks = length_splitter.split_documents(section_documents)
        for chunk_index, chunk in enumerate(document_chunks):
            chunk.metadata.update(
                {
                    "chunk_index": chunk_index,
                    "chunk_id": build_chunk_id(
                        tenant_id=catalog.tenant_id,
                        document_id=entry.document_id,
                        chunk_index=chunk_index,
                    ),
                }
            )
            all_chunks.append(chunk)

    return all_chunks
