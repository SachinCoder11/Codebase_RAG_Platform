# backend/app/services/vector_store.py
"""
VectorStore — backward-compatible shim over ProviderFactory.
All callers (repository_processor.py, repository.py endpoint) use these class methods.
Do not call chromadb directly from outside this file.
"""
import logging
from typing import List, Dict, Any, Optional
from app.services.providers.factory import ProviderFactory


class VectorStore:

    @classmethod
    def create_collection(cls, repo_id: str):
        return ProviderFactory.get_vector_store().create_collection(repo_id)

    @classmethod
    def insert_chunks(
        cls,
        repo_id: str,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]]
    ):
        ProviderFactory.get_vector_store().insert(repo_id, documents, embeddings, metadatas)

    @classmethod
    def similarity_search(
        cls,
        repo_id: str,
        query_embedding: List[float],
        top_k: int = 7,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        return ProviderFactory.get_vector_store().search(repo_id, query_embedding, top_k, filters)

    @classmethod
    def delete_repository(cls, repo_id: str) -> bool:
        return ProviderFactory.get_vector_store().delete(repo_id)

    @classmethod
    def repository_statistics(cls, repo_id: str) -> Dict[str, Any]:
        return ProviderFactory.get_vector_store().get_stats(repo_id)

    # Legacy helper — kept for any internal use
    @classmethod
    def get_collection_name(cls, repo_id: str) -> str:
        return "repo_RAGDATA"
