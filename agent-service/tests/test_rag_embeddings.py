from agent_service.core.config import Settings
from agent_service.rag import embeddings as embedding_module


class FakeHuggingFaceEmbeddings:
    def __init__(
        self,
        *,
        model_name: str,
        model_kwargs: dict[str, object],
        encode_kwargs: dict[str, object],
    ) -> None:
        self.model_name = model_name
        self.model_kwargs = model_kwargs
        self.encode_kwargs = encode_kwargs

    def embed_query(self, text: str) -> list[float]:
        assert text == "向量维度检测"
        return [0.1, 0.2, 0.3]


def test_create_embedding_resources_uses_settings_and_detects_size(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        embedding_module,
        "HuggingFaceEmbeddings",
        FakeHuggingFaceEmbeddings,
    )
    settings = Settings(
        _env_file=None,
        embedding_model_name="test-model",
        embedding_device="cpu",
        embedding_normalize=True,
    )

    resources = embedding_module.create_embedding_resources(settings)

    assert resources.vector_size == 3
    assert resources.model.model_name == "test-model"
    assert resources.model.model_kwargs == {"device": "cpu"}
    assert resources.model.encode_kwargs == {
        "normalize_embeddings": True,
    }
