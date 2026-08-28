# backend/app/services/providers/llm/future_provider_stub.py
"""
Future LLM Provider Stubs
These are placeholder classes for providers not yet implemented.
To activate a provider:
1. Implement the generate() method
2. Add a case to ProviderFactory.get_llm()
3. Set LLM_PROVIDER=<name> in .env
"""
from app.services.providers.llm.base import BaseLLMProvider

class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude — not yet implemented."""
    def generate(self, prompt: str) -> str:
        raise NotImplementedError("ClaudeProvider not yet implemented.")
    def health_check(self): return {"status": "not_implemented", "provider": "claude"}
    def get_model_info(self): return {"provider": "claude", "type": "cloud_api"}

class GeminiProvider(BaseLLMProvider):
    """Google Gemini — not yet implemented."""
    def generate(self, prompt: str) -> str:
        raise NotImplementedError("GeminiProvider not yet implemented.")
    def health_check(self): return {"status": "not_implemented", "provider": "gemini"}
    def get_model_info(self): return {"provider": "gemini", "type": "cloud_api"}

class AzureOpenAIProvider(BaseLLMProvider):
    """Azure OpenAI — not yet implemented."""
    def generate(self, prompt: str) -> str:
        raise NotImplementedError("AzureOpenAIProvider not yet implemented.")
    def health_check(self): return {"status": "not_implemented", "provider": "azure_openai"}
    def get_model_info(self): return {"provider": "azure_openai", "type": "cloud_api"}
