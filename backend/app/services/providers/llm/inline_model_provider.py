# backend/app/services/providers/llm/inline_model_provider.py
"""
Inline Model LLM Provider
========================================
Handles any OpenAI-compatible cloud LLM endpoint dynamically configured.
"""
import logging
from typing import Dict, Any, Iterator
import httpx

from app.services.providers.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

_SYSTEM_MSG = (
    "You are a helpful software engineering assistant specialised in repository "
    "analysis and code search. Ground your answers strictly in the provided context."
)


class InlineModelProvider(BaseLLMProvider):
    """OpenAI-compatible LLM provider initialized with custom settings."""

    def __init__(self, api_key: str, base_url: str, model: str):
        self._api_key_val = api_key
        self._base_url_val = base_url.rstrip("/")
        self._model_val = model
        logger.info(f"InlineModelProvider initialized for model {self._model_val} @ {self._base_url_val}")

    def _base_url(self) -> str:
        return self._base_url_val

    def _api_key(self) -> str:
        return self._api_key_val

    def _model(self) -> str:
        return self._model_val

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type":  "application/json",
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _build_payload(self, prompt: str, stream: bool = False) -> Dict:
        return {
            "model": self._model(),
            "messages": [
                {"role": "system", "content": _SYSTEM_MSG},
                {"role": "user",   "content": prompt},
            ],
            "max_tokens":  2048,
            "temperature": 0.7,
            "stream":      stream,
        }

    # ── Public interface ───────────────────────────────────────────────────────

    def generate(self, prompt: str) -> str:
        if not self._api_key():
            return "API key not configured. Set INLINE_MODEL_API_KEY in .env"
        try:
            response = httpx.post(
                f"{self._base_url()}/chat/completions",
                json=self._build_payload(prompt, stream=False),
                headers=self._headers(),
                timeout=120,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            logger.error(f"InlineModel HTTP error: {exc.response.status_code} — {exc.response.text[:300]}")
            return f"InlineModel request failed ({exc.response.status_code}): {exc.response.text[:200]}"
        except Exception as exc:
            logger.error(f"InlineModel error: {exc}")
            return f"InlineModel request failed: {str(exc)}"

    def generate_stream(self, prompt: str) -> Iterator[str]:
        """Yield text tokens from a streaming chat completion."""
        if not self._api_key():
            yield "API key not configured."
            return

        try:
            import json as _json
            with httpx.stream(
                "POST",
                f"{self._base_url()}/chat/completions",
                json=self._build_payload(prompt, stream=True),
                headers=self._headers(),
                timeout=120,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    line = line.strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    try:
                        chunk   = _json.loads(line)
                        content = chunk["choices"][0].get("delta", {}).get("content", "")
                        if content:
                            yield content
                    except Exception:
                        continue
        except Exception as exc:
            logger.error(f"InlineModel stream error: {exc}")
            yield self.generate(prompt)

    def health_check(self) -> Dict[str, Any]:
        return {
            "status":   "configured" if self._api_key() else "not_configured",
            "provider": "inline_model",
            "model":    self._model(),
            "base_url": self._base_url(),
        }

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "inline_model",
            "model":    self._model(),
            "type":     "cloud_api",
            "base_url": self._base_url(),
        }
