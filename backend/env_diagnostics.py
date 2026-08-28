"""
env_diagnostics.py
==================
Prints all active environment variables the backend reads,
confirms which .env file was loaded, and masks sensitive values.

Run from the backend/ directory:
    python env_diagnostics.py
"""
import sys
import os

# Ensure backend/app is importable when run from backend/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings

def mask(value: str, show_prefix: int = 8, show_suffix: int = 4) -> str:
    """Show first N and last N characters; replace middle with '...'"""
    if not value:
        return "[NOT SET]"
    if len(value) <= show_prefix + show_suffix + 3:
        return "[SET - too short to mask]"
    return f"SET -> {value[:show_prefix]}...{value[-show_suffix:]}"

def env_file_path() -> str:
    """Resolve where pydantic-settings would look for .env"""
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(backend_dir, ".env")
    if os.path.exists(candidate):
        return f"{candidate}  [FOUND]"
    root_candidate = os.path.join(os.path.dirname(backend_dir), ".env")
    if os.path.exists(root_candidate):
        return f"{root_candidate}  [FOUND - root]"
    return f"{candidate}  [NOT FOUND]"

SEP = "=" * 65
SEC = "-" * 65

print()
print(SEP)
print("  ENV DIAGNOSTICS - AI Repository Analysis Platform")
print(SEP)

print("\n[.env File]")
print(f"  Resolved path : {env_file_path()}")
print(f"  CWD           : {os.getcwd()}")

print(f"\n[Provider Selectors]")
print(f"  LLM_PROVIDER       : {settings.LLM_PROVIDER}")
print(f"  VECTOR_PROVIDER    : {settings.VECTOR_PROVIDER}")
print(f"  EMBEDDING_PROVIDER : {settings.EMBEDDING_PROVIDER}")

print(f"\n[Ollama - Local LLM]")
print(f"  OLLAMA_HOST  : {settings.OLLAMA_HOST}")
print(f"  OLLAMA_MODEL : {settings.OLLAMA_MODEL}")

print(f"\n[Chroma Cloud]")
print(f"  CHROMA_HOST     : {settings.CHROMA_HOST or '[NOT SET]'}")
print(f"  CHROMA_TENANT   : {settings.CHROMA_TENANT or '[NOT SET]'}")
print(f"  CHROMA_DATABASE : {settings.CHROMA_DATABASE or '[NOT SET]'}")
print(f"  CHROMA_API_KEY  : {mask(settings.CHROMA_API_KEY)}")

print(f"\n[OpenRouter - Cloud LLM]")
print(f"  OPENROUTER_MODEL   : {settings.OPENROUTER_MODEL}")
print(f"  OPENROUTER_API_KEY : {mask(settings.OPENROUTER_API_KEY)}")

print(f"\n[HuggingFace API - Cloud Embedding]")
print(f"  HUGGINGFACE_EMBEDDING_MODEL : {settings.HUGGINGFACE_EMBEDDING_MODEL}")
print(f"  HUGGINGFACE_API_URL         : {settings.HUGGINGFACE_API_URL}")
print(f"  HUGGINGFACE_API_KEY         : {mask(settings.HUGGINGFACE_API_KEY)}")

print(f"\n[Local Embedding]")
print(f"  EMBEDDING_MODEL_NAME : {settings.EMBEDDING_MODEL_NAME}")

print(f"\n[Storage Paths]")
print(f"  BASE_DATA_DIR      : {settings.BASE_DATA_DIR}")
print(f"  CHROMA_PERSIST_DIR : {settings.CHROMA_PERSIST_DIR}")

print(f"\n[Readiness Summary]")
issues = []
if not settings.CHROMA_HOST:
    issues.append("CHROMA_HOST is not set -- Chroma Cloud will not connect")
if not settings.CHROMA_API_KEY:
    issues.append("CHROMA_API_KEY is not set -- Chroma Cloud auth will fail")
if not settings.CHROMA_TENANT:
    issues.append("CHROMA_TENANT is not set -- requests will use wrong tenant")
if not settings.CHROMA_DATABASE:
    issues.append("CHROMA_DATABASE is not set")

if issues:
    print("  [ISSUES FOUND]")
    for issue in issues:
        print(f"    - {issue}")
else:
    print("  [OK] All required Chroma Cloud vars are set")
    print("  [OK] Provider selectors loaded")

print()
print(SEP)
