# backend/app/services/providers/vector_store/cloud_chroma_provider.py
"""
CloudChromaProvider — uses Chroma Cloud (api.trychroma.com).
Credentials come from .env:
  CHROMA_HOST=api.trychroma.com
  CHROMA_API_KEY=ck-...
  CHROMA_TENANT=<your-tenant-uuid>
  CHROMA_DATABASE=<your-database-name>

API Notes (chromadb >= 0.4.24):
  - HttpClient(host, port, ssl, headers, tenant, database)
  - Chroma Cloud uses SSL on port 443 — must set port=443, ssl=True
  - Token is passed via the "x-chroma-token" header
  - TokenTransportHeader import is kept for future compatibility but not
    required for header-based auth with HttpClient
"""
import logging
import chromadb
from typing import List, Dict, Any, Optional
from app.services.providers.vector_store.base import BaseVectorStoreProvider
from app.core.config import settings


class CloudChromaProvider(BaseVectorStoreProvider):
    """ChromaDB Cloud provider using HTTP client with SSL on port 443."""
    _client = None

    def _get_client(self):
        if self.__class__._client is None:
            if not settings.CHROMA_API_KEY:
                raise ValueError(
                    "CHROMA_API_KEY not set in .env. "
                    "Get your key from https://cloud.trychroma.com"
                )
            if not settings.CHROMA_TENANT:
                raise ValueError("CHROMA_TENANT not set in .env")
            if not settings.CHROMA_DATABASE:
                raise ValueError("CHROMA_DATABASE not set in .env")

            logging.info(
                f"Connecting to Chroma Cloud: host={settings.CHROMA_HOST}, "
                f"tenant={settings.CHROMA_TENANT}, database={settings.CHROMA_DATABASE}"
            )
            try:
                self.__class__._client = chromadb.HttpClient(
                    host=settings.CHROMA_HOST,
                    port=443,          # Chroma Cloud always uses HTTPS on 443
                    ssl=True,
                    headers={"x-chroma-token": settings.CHROMA_API_KEY},
                    tenant=settings.CHROMA_TENANT,
                    database=settings.CHROMA_DATABASE,
                )
                logging.info("Chroma Cloud client created successfully.")
            except Exception as e:
                logging.error(f"Failed to create Chroma Cloud client: {e}")
                raise
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
        batch_size = 100  # Cloud batches should be smaller to avoid timeouts
        for i in range(0, len(documents), batch_size):
            end = min(i + batch_size, len(documents))
            collection.add(
                ids=ids[i:end],
                embeddings=embeddings[i:end],
                metadatas=metadatas[i:end],
                documents=documents[i:end]
            )
        logging.info(
            f"Inserted {len(documents)} vectors into cloud collection "
            f"'{self._collection_name(repo_id)}'"
        )

    def search(self, repo_id, query_embedding, top_k=7, filters=None):
        name = self._collection_name(repo_id)
        try:
            collection = self._get_client().get_collection(name=name)
        except Exception as e:
            logging.warning(f"Cloud collection '{name}' not found: {e}")
            return []

        where_filter = {k: v for k, v in (filters or {}).items() if v}
        # Enforce repo_id filter for single-collection architecture
        where_filter["repo_id"] = repo_id

        # Clamp n_results to the number of documents in the collection
        # to avoid ChromaDB errors when top_k > stored vector count
        try:
            count_result = collection.get(where=where_filter, include=[])
            available = len(count_result.get("ids", []))
            safe_top_k = min(top_k, available) if available > 0 else top_k
        except Exception as count_err:
            logging.warning(f"Could not count vectors for repo '{repo_id}': {count_err}")
            safe_top_k = top_k

        if safe_top_k == 0:
            logging.warning(
                f"No vectors found in cloud for repo_id='{repo_id}'. "
                "The repository may not have been indexed yet, or indexing failed."
            )
            return []

        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=safe_top_k,
                where=where_filter
            )
        except Exception as query_err:
            logging.error(
                f"Chroma Cloud query failed for repo '{repo_id}' "
                f"(n_results={safe_top_k}): {query_err}"
            )
            return []

        formatted = []
        if results and results.get("documents"):
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            dists = results.get("distances", [[0.0] * len(docs)])[0]
            ids = results["ids"][0]
            for d, m, dist, cid in zip(docs, metas, dists, ids):
                formatted.append({
                    "id": cid,
                    "document": d,
                    "metadata": m,
                    "distance": float(dist)
                })
        return formatted

    def delete(self, repo_id: str) -> bool:
        name = self._collection_name(repo_id)
        try:
            collection = self._get_client().get_collection(name=name)
            collection.delete(where={"repo_id": repo_id})
            logging.info(f"Deleted vectors for '{repo_id}' from cloud collection '{name}'")
            return True
        except Exception as e:
            logging.warning(f"Could not delete vectors for '{repo_id}' from cloud collection '{name}': {e}")
            return False

    def health_check(self):
        try:
            self._get_client().heartbeat()
            return {
                "status": "healthy",
                "provider": "cloud_chroma",
                "host": settings.CHROMA_HOST,
                "tenant": settings.CHROMA_TENANT,
                "database": settings.CHROMA_DATABASE,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": "cloud_chroma",
                "host": settings.CHROMA_HOST,
                "error": str(e)
            }

    def get_stats(self, repo_id: str):
        name = self._collection_name(repo_id)
        try:
            col = self._get_client().get_collection(name=name)
            result = col.get(where={"repo_id": repo_id}, include=[])
            return {"vector_count": len(result.get("ids", []))}
        except Exception:
            return {"vector_count": 0}
