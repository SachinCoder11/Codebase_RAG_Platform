# backend/app/services/providers/factory.py
"""
ProviderFactory — reads LLM_PROVIDER, VECTOR_PROVIDER, EMBEDDING_PROVIDER from config
and returns the appropriate singleton provider instance.
"""
import logging
from app.core.config import settings
from app.services.providers.llm.base import BaseLLMProvider
from app.services.providers.vector_store.base import BaseVectorStoreProvider
from app.services.providers.embedding.base import BaseEmbeddingProvider

_llm_instance: BaseLLMProvider = None
_vector_instance: BaseVectorStoreProvider = None
_embedding_instance: BaseEmbeddingProvider = None


class ProviderFactory:

    @staticmethod
    def get_llm() -> BaseLLMProvider:
        global _llm_instance
        if _llm_instance is None:
            provider = settings.LLM_PROVIDER.lower()
            logging.info(f"Initializing LLM provider: {provider}")
            if provider == "ollama":
                from app.services.providers.llm.ollama_provider import OllamaProvider
                _llm_instance = OllamaProvider()
            elif provider == "openrouter":
                from app.services.providers.llm.openrouter_provider import OpenRouterProvider
                _llm_instance = OpenRouterProvider()
            elif provider == "inline_model":
                # ── Inline Model (any OpenAI-compatible endpoint) ─────────────
                # Set INLINE_MODEL_API_KEY, INLINE_MODEL_BASE_URL,
                # and INLINE_MODEL_NAME in .env, then set LLM_PROVIDER=inline_model.
                # Supported providers: NVIDIA NIM, Groq, Together AI, OpenAI, vLLM, etc.
                if not settings.INLINE_MODEL_API_KEY:
                    raise ValueError(
                        "LLM_PROVIDER=inline_model but INLINE_MODEL_API_KEY is not set. "
                        "Fill in INLINE_MODEL_API_KEY, INLINE_MODEL_BASE_URL, and "
                        "INLINE_MODEL_NAME in .env first."
                    )
                if not settings.INLINE_MODEL_BASE_URL:
                    raise ValueError(
                        "INLINE_MODEL_BASE_URL is not set. "
                        "Example: https://integrate.api.nvidia.com/v1"
                    )
                from app.services.providers.llm.inline_model_provider import InlineModelProvider
                _llm_instance = InlineModelProvider(
                    api_key=settings.INLINE_MODEL_API_KEY,
                    base_url=settings.INLINE_MODEL_BASE_URL,
                    model=settings.INLINE_MODEL_NAME,
                )
                logging.info(
                    f"Inline model provider active: {settings.INLINE_MODEL_NAME} "
                    f"@ {settings.INLINE_MODEL_BASE_URL}"
                )
            elif provider == "huggingface":
                if not settings.HUGGINGFACE_API_KEY:
                    raise ValueError(
                        "LLM_PROVIDER=huggingface but HUGGINGFACE_API_KEY is not set.\n\n"
                        "Please configure:\n\n"
                        "    HUGGINGFACE_API_KEY=hf_xxxxxxxxx\n\n"
                        "in your .env file."
                    )
                from app.services.providers.llm.huggingface_provider import HuggingFaceProvider
                _llm_instance = HuggingFaceProvider()
            else:
                raise ValueError(
                    f"Unknown LLM_PROVIDER: '{provider}'. "
                    f"Valid: ollama, openrouter, inline_model, huggingface"
                )
        return _llm_instance

    @staticmethod
    def get_vector_store() -> BaseVectorStoreProvider:
        global _vector_instance
        if _vector_instance is None:
            provider = settings.VECTOR_PROVIDER.lower()
            logging.info(f"Initializing vector store provider: {provider}")
            if provider == "local_chroma":
                from app.services.providers.vector_store.local_chroma_provider import LocalChromaProvider
                _vector_instance = LocalChromaProvider()
            elif provider == "cloud_chroma":
                from app.services.providers.vector_store.cloud_chroma_provider import CloudChromaProvider
                _vector_instance = CloudChromaProvider()
            else:
                raise ValueError(f"Unknown VECTOR_PROVIDER: '{provider}'. Valid: local_chroma, cloud_chroma")
        return _vector_instance

    @staticmethod
    def get_embedding() -> BaseEmbeddingProvider:
        global _embedding_instance
        if _embedding_instance is None:
            provider = settings.EMBEDDING_PROVIDER.lower()
            logging.info(f"Initializing embedding provider: {provider}")
            if provider == "local_bge":
                from app.services.providers.embedding.local_bge_provider import LocalBGEProvider
                _embedding_instance = LocalBGEProvider()
            elif provider == "huggingface_api":
                from app.services.providers.embedding.huggingface_api_provider import HuggingFaceAPIProvider
                _embedding_instance = HuggingFaceAPIProvider()
            else:
                raise ValueError(f"Unknown EMBEDDING_PROVIDER: '{provider}'. Valid: local_bge, huggingface_api")
        return _embedding_instance

    @staticmethod
    def reset():
        """Force re-initialization of all providers. Use when .env changes at runtime."""
        global _llm_instance, _vector_instance, _embedding_instance
        _llm_instance = None
        _vector_instance = None
        _embedding_instance = None
