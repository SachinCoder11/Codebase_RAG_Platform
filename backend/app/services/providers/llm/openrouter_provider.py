# backend/app/services/providers/llm/openrouter_provider.py
"""
OpenRouter / Inline-Model LLM Provider
========================================
Handles any OpenAI-compatible cloud LLM endpoint.

Activated via .env in two ways:
  1. OpenRouter:
       LLM_PROVIDER=openrouter
       OPENROUTER_API_KEY=sk-or-...
       OPENROUTER_MODEL=mistralai/mistral-7b-instruct

  2. Inline Model (Groq, Together AI, OpenAI, etc.):
       LLM_PROVIDER=inline_model
       INLINE_MODEL_API_KEY=gsk_xxx
       INLINE_MODEL_BASE_URL=https://api.groq.com/openai/v1
       INLINE_MODEL_NAME=llama-3.1-8b-instant

Both paths use identical code — the factory patches the env vars for inline_model
before instantiating this provider.
"""
import logging
from typing import Dict, Any, Iterator

import httpx

from app.services.providers.llm.base import BaseLLMProvider
from app.core.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_MSG = (
    "You are a helpful software engineering assistant specialised in repository "
    "analysis and code search. Ground your answers strictly in the provided context."
)


class OpenRouterProvider(BaseLLMProvider):
    """OpenAI-compatible cloud LLM provider (OpenRouter, Groq, Together AI, OpenAI…)."""

    def _base_url(self) -> str:
        return (settings.OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1").rstrip("/")

    def _api_key(self) -> str:
        return settings.OPENROUTER_API_KEY

    def _model(self) -> str:
        return settings.OPENROUTER_MODEL

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
            return (
                "API key not configured. "
                "Set OPENROUTER_API_KEY (or INLINE_MODEL_API_KEY) in .env"
            )
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
            logger.error(f"OpenRouter HTTP error: {exc.response.status_code} — {exc.response.text[:300]}")
            return f"OpenRouter request failed ({exc.response.status_code}): {exc.response.text[:200]}"
        except Exception as exc:
            logger.error(f"OpenRouter error: {exc}")
            return f"OpenRouter request failed: {str(exc)}"

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
            logger.error(f"OpenRouter stream error: {exc}")
            yield self.generate(prompt)

    def health_check(self) -> Dict[str, Any]:
        return {
            "status":   "configured" if self._api_key() else "not_configured",
            "provider": "openrouter",
            "model":    self._model(),
            "base_url": self._base_url(),
        }

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "openrouter",
            "model":    self._model(),
            "type":     "cloud_api",
            "base_url": self._base_url(),
        }
