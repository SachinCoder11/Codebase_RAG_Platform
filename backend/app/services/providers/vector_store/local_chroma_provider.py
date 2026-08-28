# backend/app/services/providers/vector_store/local_chroma_provider.py
import logging
import chromadb
from typing import List, Dict, Any, Optional
from app.services.providers.vector_store.base import BaseVectorStoreProvider
from app.core.config import settings

class LocalChromaProvider(BaseVectorStoreProvider):
    """ChromaDB running locally on disk (PersistentClient)."""
    _client = None

    def _get_client(self) -> chromadb.PersistentClient:
        if self.__class__._client is None:
            logging.info(f"Initializing local ChromaDB at {settings.CHROMA_PERSIST_DIR}")
            self.__class__._client = chromadb.PersistentClient(
                path=str(settings.CHROMA_PERSIST_DIR)
            )
        return self.__class__._client

    def _collection_name(self, repo_id: str) -> str:
        return "repo_RAGDATA"

    def create_collection(self, repo_id: str):
        return self._get_client().get_or_create_collection(
            name=self._collection_name(repo_id)
        )

    def insert(self, repo_id, documents, embeddings, metadatas):
        if not documents:
            return
        collection = self.create_collection(repo_id)
        ids = [f"chunk_{m['hash']}_{i}" for i, m in enumerate(metadatas)]
        batch_size = 500
        for i in range(0, len(documents), batch_size):
            end = min(i + batch_size, len(documents))
            collection.add(
                ids=ids[i:end],
                embeddings=embeddings[i:end],
                metadatas=metadatas[i:end],
                documents=documents[i:end]
            )
        logging.info(f"Inserted {len(documents)} vectors into '{self._collection_name(repo_id)}'")

    def search(self, repo_id, query_embedding, top_k=7, filters=None):
        client = self._get_client()
        name = self._collection_name(repo_id)
        try:
            collection = client.get_collection(name=name)
        except Exception:
            logging.warning(f"Collection {name} not found")
            return []
        where_filter = {k: v for k, v in (filters or {}).items() if v}
        # Enforce repo_id filter for single-collection architecture
        where_filter["repo_id"] = repo_id

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter
        )
        formatted = []
        if results and results.get("documents"):
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            dists = results.get("distances", [[0.0] * len(docs)])[0]
            ids = results["ids"][0]
            for d, m, dist, cid in zip(docs, metas, dists, ids):
                formatted.append({"id": cid, "document": d, "metadata": m, "distance": float(dist)})
        return formatted

    def delete(self, repo_id: str) -> bool:
        name = self._collection_name(repo_id)
        try:
            collection = self._get_client().get_collection(name=name)
            collection.delete(where={"repo_id": repo_id})
            logging.info(f"Deleted vectors for '{repo_id}' from collection '{name}'")
            return True
        except Exception as e:
            logging.warning(f"Could not delete '{name}': {e}")
            return False

    def health_check(self):
        try:
            client = self._get_client()
            collections = client.list_collections()
            return {"status": "healthy", "provider": "local_chroma", "collections": len(collections)}
        except Exception as e:
            return {"status": "unhealthy", "provider": "local_chroma", "error": str(e)}

    def get_stats(self, repo_id: str):
        name = self._collection_name(repo_id)
        try:
            col = self._get_client().get_collection(name=name)
            result = col.get(where={"repo_id": repo_id}, include=[])
            return {"vector_count": len(result.get("ids", []))}
        except Exception:
            return {"vector_count": 0}
