# backend/app/services/providers/embedding/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseEmbeddingProvider(ABC):
    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]: ...

    @abstractmethod
    def embed_query(self, query: str) -> List[float]: ...

    @abstractmethod
    def health_check(self) -> Dict[str, Any]: ...
