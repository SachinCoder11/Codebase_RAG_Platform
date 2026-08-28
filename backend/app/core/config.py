import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Repository Analysis Platform"

    # Storage Paths
    BASE_DATA_DIR: Path = Path(os.getenv("BASE_DATA_DIR", "./data"))

    @property
    def UPLOADS_DIR(self) -> Path:
        p = self.BASE_DATA_DIR / "uploads"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def WORKSPACES_DIR(self) -> Path:
        p = self.BASE_DATA_DIR / "workspaces"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def REPORTS_DIR(self) -> Path:
        p = self.BASE_DATA_DIR / "reports"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def CHROMA_PERSIST_DIR(self) -> Path:
        p = self.BASE_DATA_DIR / "chromadb"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def LOG_FILE(self) -> Path:
        p = Path("./logs/rag_debug.log")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    # ── Provider Selectors ──────────────────────────────────────────────────
    # Valid: ollama | openrouter | inline_model | huggingface
    LLM_PROVIDER: str = "ollama"
    # Valid: local_chroma | cloud_chroma
    VECTOR_PROVIDER: str = "local_chroma"
    # Valid: local_bge | huggingface_api
    EMBEDDING_PROVIDER: str = "local_bge"

    # ── Debug Mode ──────────────────────────────────────────────────────────
    DEBUG_RAG: bool = False

    # ── Ollama (local LLM — PRIMARY) ────────────────────────────────────────
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3.5:4b"

    # ── OpenRouter (cloud LLM) ──────────────────────────────────────────────
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "mistralai/mistral-7b-instruct"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # ── Local Embedding ─────────────────────────────────────────────────────
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"

    # ── HuggingFace Inference API (cloud embedding) ─────────────────────────
    HUGGINGFACE_API_KEY: str = ""
    HUGGINGFACE_EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    HUGGINGFACE_API_URL: str = "https://api-inference.huggingface.co/models"

    # ── Hugging Face LLM Model ──────────────────────────────────────────────
    # Used when LLM_PROVIDER=huggingface. Change to switch models without code edits.
    HF_MODEL: str = "meta-llama/Llama-3.1-8B-Instruct"

    # ── Inline Model (custom OpenAI-compatible endpoint) ─────────────────────
    # Activate by setting LLM_PROVIDER=inline_model in .env
    # Provide the API key and base URL for any OpenAI-compatible provider
    # (Groq, Together AI, OpenAI, local vLLM, etc.)
    INLINE_MODEL_API_KEY: str = ""
    INLINE_MODEL_BASE_URL: str = ""
    INLINE_MODEL_NAME: str = ""

    # ── Chroma Cloud ────────────────────────────────────────────────────────
    CHROMA_HOST: str = ""
    CHROMA_API_KEY: str = ""
    CHROMA_TENANT: str = ""
    CHROMA_DATABASE: str = ""

    # ── GitHub API ──────────────────────────────────────────────────────────
    # Optional: set to increase rate limit from 60 → 5,000 req/hr
    GITHUB_TOKEN: str = ""

    class Config:
        # Resolve .env relative to this file's location (backend/app/core/config.py)
        # so settings load correctly regardless of CWD (e.g., running from backend/ or root)
        env_file = str(Path(__file__).resolve().parent.parent.parent.parent / ".env")
        case_sensitive = True

settings = Settings()
