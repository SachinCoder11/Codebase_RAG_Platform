# backend/app/services/providers/llm/ollama_provider.py
import requests
import logging
from typing import Dict, Any
from app.services.providers.llm.base import BaseLLMProvider
from app.core.config import settings

class OllamaProvider(BaseLLMProvider):
    """Local Ollama inference provider."""

    def generate(self, prompt: str) -> str:
        url = f"{settings.OLLAMA_HOST}/api/generate"
        payload = {"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False}
        try:
            response = requests.post(url, json=payload, timeout=120)
            if response.status_code == 200:
                return response.json().get("response", "")
            logging.error(f"Ollama error status: {response.status_code}")
            return (
                f"Ollama server returned error status: {response.status_code}. "
                "Run: ollama pull llama3"
            )
        except requests.exceptions.RequestException as e:
            logging.error(f"Ollama connection failed: {str(e)}")
            return (
                f"Could not connect to Ollama at {settings.OLLAMA_HOST}. "
                "Run: ollama serve"
            )

    def generate_stream(self, prompt: str):
        """Yield tokens or strings from the local Ollama API."""
        url = f"{settings.OLLAMA_HOST}/api/generate"
        payload = {"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": True}
        try:
            with requests.post(url, json=payload, stream=True, timeout=120) as response:
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            import json
                            chunk = json.loads(line.decode("utf-8"))
                            content = chunk.get("response", "")
                            if content:
                                yield content
                else:
                    logging.error(f"Ollama stream error status: {response.status_code}")
                    yield self.generate(prompt)
        except Exception as e:
            logging.error(f"Ollama stream generation failed: {e}")
            yield self.generate(prompt)

    def health_check(self) -> Dict[str, Any]:
        try:
            response = requests.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=5)
            return {
                "status": "healthy" if response.status_code == 200 else "degraded",
                "provider": "ollama",
                "host": settings.OLLAMA_HOST,
                "model": settings.OLLAMA_MODEL
            }
        except Exception as e:
            return {"status": "unreachable", "provider": "ollama", "error": str(e)}

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "ollama",
            "model": settings.OLLAMA_MODEL,
            "host": settings.OLLAMA_HOST,
            "type": "local"
        }
