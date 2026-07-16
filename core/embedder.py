from sentence_transformers import SentenceTransformer

_MODEL_NAME = "all-MiniLM-L6-v2"
_model = SentenceTransformer(_MODEL_NAME)


def embed(text: str) -> list[float]:
    return _model.encode(text).tolist()
