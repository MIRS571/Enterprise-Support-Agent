from pathlib import Path

from agent_service.rag import load_and_split_catalog

CATALOG_PATH = (
    Path(__file__).parents[1] / "data" / "knowledge" / "company_001" / "catalog.json"
)


def test_load_and_split_catalog_preserves_headings() -> None:
    chunks = load_and_split_catalog(CATALOG_PATH)
    shipped_chunk = next(
        chunk for chunk in chunks if chunk.metadata.get("section_title") == "已发货订单"
    )

    assert "## 已发货订单" in shipped_chunk.page_content
    assert "不能直接取消" in shipped_chunk.page_content


def test_chunks_have_tenant_metadata_and_stable_ids() -> None:
    first_import = load_and_split_catalog(CATALOG_PATH)
    second_import = load_and_split_catalog(CATALOG_PATH)
    first_ids = [chunk.metadata["chunk_id"] for chunk in first_import]
    second_ids = [chunk.metadata["chunk_id"] for chunk in second_import]

    assert first_ids == second_ids
    assert len(first_ids) == len(set(first_ids))
    assert all(chunk.metadata["tenant_id"] == "company_001" for chunk in first_import)
    assert all("user_id" not in chunk.metadata for chunk in first_import)
    assert all("title" in chunk.metadata for chunk in first_import)
    assert all("source" in chunk.metadata for chunk in first_import)
    assert all("version" in chunk.metadata for chunk in first_import)
