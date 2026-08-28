# backend/app/services/embedding.py
"""
EmbeddingService — backward-compatible shim over ProviderFactory.
Callers: repository_processor.py, query_engine.py.
Public method signatures are preserved.
"""
from typing import List
from app.services.providers.factory import ProviderFactory


class EmbeddingService:

    @classmethod
    def generate_embeddings(cls, texts: List[str]) -> List[List[float]]:
        return ProviderFactory.get_embedding().embed_documents(texts)

    @classmethod
    def generate_query_embedding(cls, query: str) -> List[float]:
        return ProviderFactory.get_embedding().embed_query(query)

    @classmethod
    def batch_embedding(cls, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        embeddings = []
        for i in range(0, len(texts), batch_size):
            embeddings.extend(cls.generate_embeddings(texts[i:i + batch_size]))
        return embeddings
