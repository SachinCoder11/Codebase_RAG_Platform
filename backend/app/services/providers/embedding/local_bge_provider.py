# backend/app/services/providers/embedding/local_bge_provider.py
import logging
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from app.services.providers.embedding.base import BaseEmbeddingProvider
from app.core.config import settings

class LocalBGEProvider(BaseEmbeddingProvider):
    """BAAI/bge-small-en-v1.5 running locally via sentence-transformers.

    Load strategy:
      1. Try local_files_only=True (offline, uses HuggingFace cache — no network call)
      2. If the cache is missing, fall back to online download (first-time setup only)
    """
    _model = None

    def _get_model(self) -> SentenceTransformer:
        if self.__class__._model is None:
            model_name = settings.EMBEDDING_MODEL_NAME

            # ── Try loading from local cache first (fully offline) ─────────
            try:
                logging.info(
                    f"Loading embedding model from local cache: {model_name}"
                )
                self.__class__._model = SentenceTransformer(
                    model_name,
                    local_files_only=True
                )
                logging.info("Embedding model loaded from local cache (offline mode).")
                return self.__class__._model
            except Exception as cache_err:
                logging.warning(
                    f"Local cache miss for '{model_name}': {cache_err}. "
                    "Falling back to online download (first-time setup). "
                    "This requires an internet connection."
                )

            # ── Fallback: download from HuggingFace Hub ────────────────────
            try:
                logging.info(f"Downloading embedding model: {model_name}")
                self.__class__._model = SentenceTransformer(model_name)
                logging.info("Embedding model downloaded and loaded successfully.")
            except Exception as download_err:
                logging.error(
                    f"Failed to load embedding model '{model_name}': {download_err}"
                )
                raise RuntimeError(
                    f"Cannot load embedding model '{model_name}'. "
                    f"Ensure it was previously downloaded and is in the HuggingFace cache. "
                    f"Original error: {download_err}"
                ) from download_err

        return self.__class__._model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        model = self._get_model()
        return model.encode(texts, show_progress_bar=False).tolist()

    def embed_query(self, query: str) -> List[float]:
        model = self._get_model()
        instruction = f"Represent this sentence for searching relevant passages: {query}"
        return model.encode(instruction, show_progress_bar=False).tolist()

    def health_check(self) -> Dict[str, Any]:
        try:
            self._get_model()
            return {
                "status": "healthy",
                "provider": "local_bge",
                "model": settings.EMBEDDING_MODEL_NAME,
                "mode": "offline_cache"
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": "local_bge",
                "error": str(e)
            }
