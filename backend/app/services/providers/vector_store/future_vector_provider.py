# backend/app/services/providers/vector_store/future_vector_provider.py
"""Future vector store provider stubs: Pinecone, Weaviate, pgvector."""
from app.services.providers.vector_store.base import BaseVectorStoreProvider

class PineconeProvider(BaseVectorStoreProvider):
    def create_collection(self, repo_id): raise NotImplementedError
    def insert(self, *a, **k): raise NotImplementedError
    def search(self, *a, **k): raise NotImplementedError
    def delete(self, repo_id): raise NotImplementedError
    def health_check(self): return {"status": "not_implemented", "provider": "pinecone"}
    def get_stats(self, repo_id): return {"vector_count": 0}
