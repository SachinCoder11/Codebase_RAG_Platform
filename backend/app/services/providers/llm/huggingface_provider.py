# backend/app/services/providers/llm/huggingface_provider.py
"""
Hugging Face Inference API — LLM Provider
==========================================
Connects to the Hugging Face Inference API for cloud-based LLM inference.
Model is fully configurable via HF_MODEL in .env.

Activate by setting:
    LLM_PROVIDER=huggingface
    HUGGINGFACE_API_KEY=hf_xxxxxxxxx
    HF_MODEL=meta-llama/Llama-3.1-8B-Instruct
"""
import logging
import time
from typing import Dict, Any

from app.services.providers.llm.base import BaseLLMProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

# Retry configuration for transient failures (rate limits, model loading)
_MAX_RETRIES = 3
_INITIAL_BACKOFF_SECS = 2


class HuggingFaceProvider(BaseLLMProvider):
    """Cloud LLM provider using the Hugging Face Inference API."""

    def __init__(self):
        # ── Startup validation ─────────────────────────────────────────────
        if not settings.HUGGINGFACE_API_KEY:
            msg = (
                "Hugging Face API key missing.\n\n"
                "Please configure:\n\n"
                "    HUGGINGFACE_API_KEY=hf_xxxxxxxxx\n\n"
                "in your .env file."
            )
            logger.error(msg)
            raise ValueError(msg)

        if not settings.HF_MODEL:
            msg = (
                "HF_MODEL is not set.\n\n"
                "Please configure:\n\n"
                "    HF_MODEL=meta-llama/Llama-3.1-8B-Instruct\n\n"
                "in your .env file."
            )
            logger.error(msg)
            raise ValueError(msg)

        from huggingface_hub import InferenceClient

        self._model = settings.HF_MODEL
        self._client = InferenceClient(
            model=self._model,
            token=settings.HUGGINGFACE_API_KEY,
            timeout=120,
        )
        logger.info(
            f"HuggingFaceProvider initialized — model: {self._model}"
        )

    def generate(self, prompt: str) -> str:
        """
        Send a prompt to the Hugging Face Inference API and return the response.
        Includes retry logic with exponential backoff for rate limits (429)
        and model loading delays (503).
        """
        last_error = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                messages = [
                    {"role": "system", "content": "You are a helpful software engineering assistant specialized in repository analysis and code search. Ground your answers strictly in the provided context and code."},
                    {"role": "user", "content": prompt}
                ]
                chat_resp = self._client.chat_completion(
                    messages=messages,
                    max_tokens=2048,
                    temperature=0.7,
                )
                
                # Support various response formats (dict, list, error, empty)
                logger.debug(f"Raw HF Response: {chat_resp}")
                
                response = ""
                if hasattr(chat_resp, "choices") and isinstance(chat_resp.choices, list) and len(chat_resp.choices) > 0:
                    response = chat_resp.choices[0].message.content
                elif isinstance(chat_resp, list) and len(chat_resp) > 0 and isinstance(chat_resp[0], dict):
                    # Handle raw text-generation lists
                    response = chat_resp[0].get("generated_text", "")
                elif isinstance(chat_resp, dict):
                    # Handle raw dict responses or errors
                    if "error" in chat_resp:
                        raise ValueError(f"API Error: {chat_resp['error']}")
                    if "choices" in chat_resp and isinstance(chat_resp["choices"], list) and len(chat_resp["choices"]) > 0:
                        choice = chat_resp["choices"][0]
                        response = choice.get("message", {}).get("content", "")
                        
                if response:
                    return response.strip()
                    
                logger.warning("HuggingFace returned an empty response or unsupported schema.")
                return ""

            except Exception as e:
                last_error = e
                error_msg = str(e)

                # Retry on rate limit or model loading
                is_retryable = (
                    "429" in error_msg
                    or "rate" in error_msg.lower()
                    or "503" in error_msg
                    or "loading" in error_msg.lower()
                )

                if is_retryable and attempt < _MAX_RETRIES:
                    backoff = _INITIAL_BACKOFF_SECS * (2 ** (attempt - 1))
                    logger.warning(
                        f"HuggingFace transient error (attempt {attempt}/{_MAX_RETRIES}): "
                        f"{error_msg[:100]}. Retrying in {backoff}s..."
                    )
                    time.sleep(backoff)
                    continue

                # Non-retryable or final attempt
                logger.error(f"HuggingFace generation failed: {error_msg}")
                break

        return (
            f"HuggingFace request failed after {_MAX_RETRIES} attempts. "
            f"Error: {str(last_error)}"
        )

    def generate_stream(self, prompt: str):
        """
        Yield tokens or strings from the Hugging Face Inference API.
        Falls back to generate() on failure or error.
        """
        try:
            messages = [
                {"role": "system", "content": "You are a helpful software engineering assistant specialized in repository analysis and code search. Ground your answers strictly in the provided context and code."},
                {"role": "user", "content": prompt}
            ]
            for chunk in self._client.chat_completion(
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
                stream=True
            ):
                content = ""
                if hasattr(chunk, "choices") and isinstance(chunk.choices, list) and len(chunk.choices) > 0:
                    content = chunk.choices[0].delta.content
                elif isinstance(chunk, dict) and "choices" in chunk and isinstance(chunk["choices"], list) and len(chunk["choices"]) > 0:
                    choice = chunk["choices"][0]
                    content = choice.get("delta", {}).get("content", "")
                    
                if content:
                    yield content
        except Exception as e:
            logger.error(f"HuggingFace stream generation failed: {e}")
            yield self.generate(prompt)

    def health_check(self) -> Dict[str, Any]:
        """Verify authentication and model reachability."""
        try:
            # Send a tiny ping message to verify endpoint & authentication
            self._client.chat_completion(
                messages=[{"role": "user", "content": "Ping"}],
                max_tokens=1,
            )
            return {
                "provider": "huggingface",
                "status": "healthy",
                "model": self._model,
            }
        except Exception as e:
            return {
                "provider": "huggingface",
                "status": "error",
                "model": self._model,
                "error": str(e),
            }

    def get_model_info(self) -> Dict[str, Any]:
        """Return provider metadata."""
        return {
            "provider": "huggingface",
            "model": self._model,
            "type": "cloud_api",
            "api": "huggingface_inference",
        }
