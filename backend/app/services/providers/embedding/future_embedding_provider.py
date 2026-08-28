# backend/app/services/providers/embedding/future_embedding_provider.py
"""Future embedding provider stubs."""
from app.services.providers.embedding.base import BaseEmbeddingProvider

class VoyageAIProvider(BaseEmbeddingProvider):
    def embed_documents(self, texts): raise NotImplementedError
    def embed_query(self, query): raise NotImplementedError
    def health_check(self): return {"status": "not_implemented", "provider": "voyage_ai"}

class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    def embed_documents(self, texts): raise NotImplementedError
    def embed_query(self, query): raise NotImplementedError
    def health_check(self): return {"status": "not_implemented", "provider": "openai_embeddings"}
