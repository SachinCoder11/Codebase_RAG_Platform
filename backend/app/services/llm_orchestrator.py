# backend/app/services/llm_orchestrator.py
"""
LLMOrchestrator — business logic wrapper.
All LLM calls go through ProviderFactory. Never call Ollama directly from here.
Public method signatures are preserved for backward compatibility.
"""
import logging
from app.services.providers.factory import ProviderFactory


class LLMOrchestrator:

    @classmethod
    def generate_answer(cls, prompt: str) -> str:
        return ProviderFactory.get_llm().generate(prompt)

    @classmethod
    def generate_answer_stream(cls, prompt: str):
        return ProviderFactory.get_llm().generate_stream(prompt)

    @classmethod
    def generate_summary(cls, code_preview: str) -> str:
        prompt = (
            "Summarize the following code file structure and explain its core role. "
            "Be brief and write in 2-3 sentences max.\n\n"
            f"Code:\n{code_preview}\n\nSummary:"
        )
        return ProviderFactory.get_llm().generate(prompt)

    @classmethod
    def generate_architecture_analysis(cls, directory_structure: str, languages: str) -> str:
        prompt = (
            "Analyze the software architecture of this project based on its directory layout "
            "and language footprint. Identify if it follows a Layered, Modular, MVC, or Hexagonal structure, "
            "detail the entry points, and give a brief critique.\n\n"
            f"Languages:\n{languages}\n\n"
            f"Directories/Files:\n{directory_structure}\n\nAnalysis:"
        )
        return ProviderFactory.get_llm().generate(prompt)

    @classmethod
    def generate_security_analysis(cls, dependencies: str, files_preview: str) -> str:
        prompt = (
            "Analyze the dependencies and files list below to identify high-level OWASP risks, "
            "vulnerable dependencies, or hardcoded secrets/credentials patterns. "
            "Outline key issues in markdown tables.\n\n"
            f"Dependencies:\n{dependencies}\n\n"
            f"Code preview structures:\n{files_preview}\n\nSecurity Audit Report:"
        )
        return ProviderFactory.get_llm().generate(prompt)
