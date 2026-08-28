import logging
import sys
import os
from pathlib import Path

# Ensure the backend directory is in the python path to prevent ModuleNotFoundError
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.v1.router import api_router

# Setup system logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("api_main")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Enterprise-grade code repository search and semantic analysis platform using local LLM inference.",
    version="1.0.0"
)

# Enable CORS for local testing side-by-side
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register endpoints router
app.include_router(api_router, prefix="/api/v1")

# Simple health check endpoint
@app.get("/api/v1/health")
def health_check():
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "ollama_host": settings.OLLAMA_HOST,
        "embedding_model": settings.EMBEDDING_MODEL_NAME
    }

@app.get("/api/v1/model")
def get_active_model():
    from app.services.providers.factory import ProviderFactory
    try:
        return ProviderFactory.get_llm().get_model_info()
    except Exception as e:
        return {"error": f"Failed to get active model info: {str(e)}"}


# Resolve and serve frontend directory statically
current_dir = Path(__file__).resolve().parent  # app/
backend_dir = current_dir.parent               # backend/
frontend_dir = backend_dir.parent / "frontend" # frontend/

if frontend_dir.exists():
    logger.info(f"Mounting static frontend assets from: {frontend_dir}")
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:
    logger.warning(f"Frontend static asset directory not found at: {frontend_dir}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
