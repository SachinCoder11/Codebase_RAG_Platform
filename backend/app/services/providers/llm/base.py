# backend/app/services/providers/llm/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseLLMProvider(ABC):
    """Abstract interface all LLM providers must implement."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Send a prompt and return the text response."""
        ...

    def generate_stream(self, prompt: str):
        """Yield tokens or strings from the model response. Defaults to yielding generate() as a single chunk."""
        yield self.generate(prompt)

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Return provider health status."""
        ...

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Return model metadata (name, context window, etc.)."""
        ...
