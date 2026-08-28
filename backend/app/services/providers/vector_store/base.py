# backend/app/services/providers/vector_store/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseVectorStoreProvider(ABC):
    @abstractmethod
    def create_collection(self, repo_id: str) -> Any: ...

    @abstractmethod
    def insert(
        self,
        repo_id: str,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]]
    ) -> None: ...

    @abstractmethod
    def search(
        self,
        repo_id: str,
        query_embedding: List[float],
        top_k: int,
        filters: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def delete(self, repo_id: str) -> bool: ...

    @abstractmethod
    def health_check(self) -> Dict[str, Any]: ...

    @abstractmethod
    def get_stats(self, repo_id: str) -> Dict[str, Any]: ...
