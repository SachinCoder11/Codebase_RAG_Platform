# backend/app/services/providers/embedding/huggingface_api_provider.py
"""
HuggingFace Inference API — Cloud Embedding Provider
======================================================
Uses the huggingface_hub InferenceClient for feature-extraction so that
it routes through router.huggingface.co (the new Inference API endpoint)
rather than the legacy api-inference.huggingface.co subdomain.

Activate in .env:
  EMBEDDING_PROVIDER=huggingface_api
  HUGGINGFACE_API_KEY=hf_xxxxxxxxxxxxxxx
  HUGGINGFACE_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5

Features:
  - Uses huggingface_hub SDK (same route as LLM provider — known to work)
  - Automatic retry with wait when model is loading (503 / loading states)
  - Batching to stay under the 100-input limit per request
  - Handles both List[List[float]] and nested token-level responses (mean-pool)
  - Zero local model download — all compute happens server-side
"""
import time
import logging
from typing import List, Dict, Any

from app.services.providers.embedding.base import BaseEmbeddingProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

_BATCH_SIZE   = 32          # safe batch size for HF Inference API
_MAX_RETRIES  = 5
_LOADING_WAIT = 25          # seconds to wait when model is cold-starting


class HuggingFaceAPIProvider(BaseEmbeddingProvider):
    """
    Cloud embedding provider using the HuggingFace Inference API.
    Zero local model download — all compute happens server-side.
    """
    _client = None

    def _get_client(self):
        if self.__class__._client is None:
            if not settings.HUGGINGFACE_API_KEY:
                raise ValueError(
                    "HUGGINGFACE_API_KEY not set in .env. "
                    "Set EMBEDDING_PROVIDER=huggingface_api and add your HF key."
                )
            from huggingface_hub import InferenceClient
            self.__class__._client = InferenceClient(
                token=settings.HUGGINGFACE_API_KEY,
                timeout=90,
            )
            logger.info(
                f"HuggingFaceAPIProvider initialised — model: "
                f"{settings.HUGGINGFACE_EMBEDDING_MODEL}"
            )
        return self.__class__._client

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Call the feature-extraction endpoint for a single batch.
        Retries on model-loading delays.
        """
        client = self._get_client()
        model  = settings.HUGGINGFACE_EMBEDDING_MODEL

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                # huggingface_hub >= 0.20 supports feature_extraction directly
                result = client.feature_extraction(
                    text=texts,
                    model=model,
                )
                # result is a numpy array or list; normalise to List[List[float]]
                return self._parse_embeddings(result, len(texts))

            except Exception as exc:
                error_msg = str(exc)

                # Model is still loading
                if "loading" in error_msg.lower() or "503" in error_msg:
                    wait = _LOADING_WAIT
                    logger.warning(
                        f"HF embedding model loading "
                        f"(attempt {attempt}/{_MAX_RETRIES}). "
                        f"Waiting {wait}s..."
                    )
                    time.sleep(wait)
                    continue

                # Rate limited
                if "429" in error_msg or "rate" in error_msg.lower():
                    backoff = 10 * attempt
                    logger.warning(
                        f"HF embedding rate limited "
                        f"(attempt {attempt}/{_MAX_RETRIES}). "
                        f"Retrying in {backoff}s..."
                    )
                    time.sleep(backoff)
                    continue

                # Non-retryable error
                logger.error(f"HF embedding error (attempt {attempt}): {exc}")
                if attempt == _MAX_RETRIES:
                    raise RuntimeError(
                        f"HuggingFace embedding API failed after "
                        f"{_MAX_RETRIES} attempts: {exc}"
                    ) from exc

        raise RuntimeError(
            f"HuggingFace embedding failed: exhausted all {_MAX_RETRIES} retries."
        )

    @staticmethod
    def _parse_embeddings(data: Any, expected_count: int) -> List[List[float]]:
        """
        Normalise the HF feature-extraction response into List[List[float]].

        Possible shapes:
          - numpy array shape (N, D)            → standard sentence embedding
          - numpy array shape (N, T, D)         → token-level (need mean-pool)
          - List[List[float]]                   → standard
          - List[List[List[float]]]             → token-level
        """
        # Convert numpy arrays to Python lists
        try:
            data = data.tolist()
        except AttributeError:
            pass  # already a list

        if not isinstance(data, list) or len(data) == 0:
            raise ValueError(
                f"Unexpected HuggingFace embedding response: {type(data)}"
            )

        first = data[0]

        # List[List[float]] → standard sentence embeddings ✅
        if isinstance(first, list) and len(first) > 0 and isinstance(first[0], float):
            return data

        # List[List[List[float]]] → token-level, mean-pool over token dimension
        if isinstance(first, list) and len(first) > 0 and isinstance(first[0], list):
            pooled = []
            for token_matrix in data:
                n   = len(token_matrix)
                dim = len(token_matrix[0])
                mean_vec = [
                    sum(token_matrix[t][d] for t in range(n)) / n
                    for d in range(dim)
                ]
                pooled.append(mean_vec)
            return pooled

        # Single flat list (single input, no batch wrapper)
        if isinstance(first, float):
            return [data]

        raise ValueError(
            f"Could not parse HF embedding response. "
            f"First element type: {type(first)}"
        )

    # ── Public interface ───────────────────────────────────────────────────────

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents in batches, returns List[List[float]]."""
        if not texts:
            return []

        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            logger.debug(
                f"Embedding batch {i // _BATCH_SIZE + 1} "
                f"({len(batch)} texts) via HF API"
            )
            all_embeddings.extend(self._embed_batch(batch))

        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query string with BGE search instruction prefix."""
        prefixed = f"Represent this sentence for searching relevant passages: {query}"
        return self.embed_documents([prefixed])[0]

    def health_check(self) -> Dict[str, Any]:
        """Perform a live round-trip ping to verify the endpoint is reachable."""
        try:
            self.embed_documents(["health check ping"])
            return {
                "status":   "healthy",
                "provider": "huggingface_api",
                "model":    settings.HUGGINGFACE_EMBEDDING_MODEL,
                "mode":     "cloud_api",
            }
        except Exception as exc:
            return {
                "status":   "unhealthy",
                "provider": "huggingface_api",
                "model":    settings.HUGGINGFACE_EMBEDDING_MODEL,
                "error":    str(exc),
            }
