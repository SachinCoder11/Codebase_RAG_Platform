import json
import uuid
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, status

from app.core.config import settings
from app.services.ingestion import IngestionService
from app.services.repository_processor import RepositoryProcessor
from app.services.vector_store import VectorStore
from app.schemas.repository import GitCloneRequest, RepositoryResponse
from app.models.repository import RepositoryModel
from app.workers.tasks import process_zip_repository, process_git_repository

router  = APIRouter()
logger  = logging.getLogger("repository_endpoint")


# ── Upload ─────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=Dict[str, str], status_code=status.HTTP_202_ACCEPTED)
async def upload_repository(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Uploads a repository ZIP archive, extracts it, and indexes it asynchronously.
    Uses RepositoryIdentityService to derive a meaningful repo_name from the archive.
    """
    if not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only ZIP archives are supported"
        )

    repo_id       = str(uuid.uuid4())
    archive_name  = file.filename

    # Save zip temporarily
    temp_zip_path = settings.UPLOADS_DIR / f"{repo_id}.zip"
    try:
        with open(temp_zip_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}"
        )

    RepositoryProcessor.update_processing_status(
        repo_id=repo_id, status="pending", progress=0,
        message="Upload received. Extracting files..."
    )

    def run_process_zip_bg():
        process_zip_repository(None, repo_id, str(temp_zip_path), archive_name)
    background_tasks.add_task(run_process_zip_bg)
    return {"repository_id": repo_id, "name": archive_name, "message": "Extraction started"}


# ── Clone ──────────────────────────────────────────────────────────────────────

@router.post("/clone", response_model=Dict[str, str], status_code=status.HTTP_202_ACCEPTED)
async def clone_repository(
    request: GitCloneRequest,
    background_tasks: BackgroundTasks
):
    """
    Clones a Git repository from an HTTPS URL and processes it.
    Extracts owner/repo name from the GitHub URL for dashboard display.
    """
    repo_id  = str(uuid.uuid4())
    url_str  = str(request.url).rstrip("/")

    RepositoryProcessor.update_processing_status(
        repo_id=repo_id, status="pending", progress=0,
        message="Initializing Git clone request..."
    )

    def run_process_git_bg():
        process_git_repository(None, repo_id, url_str, request.branch)
    background_tasks.add_task(run_process_git_bg)
    return {"repository_id": repo_id, "name": url_str.split("/")[-1], "message": "Cloning started"}


# ── List ───────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[Dict[str, Any]])
def list_repositories():
    """
    Lists all indexed repositories.

    Priority order for display name:
      1. SQLite registry (repo_name, owner) — most reliable
      2. summary.json on disk
      3. Fallback: Repo-{id[:8]}
    """
    # Primary source: SQLite registry
    db_repos: Dict[str, Dict[str, Any]] = {}
    try:
        for r in RepositoryModel.get_all():
            db_repos[r["repo_id"]] = r
    except Exception as e:
        logger.warning(f"Failed to read SQLite registry: {e}")

    repositories = []

    if not settings.WORKSPACES_DIR.exists():
        return repositories

    for item in settings.WORKSPACES_DIR.iterdir():
        if not item.is_dir():
            continue

        repo_id    = item.name
        status_data = RepositoryProcessor.get_status(repo_id)
        db_entry    = db_repos.get(repo_id, {})

        # ── Load summary.json ──────────────────────────────────────────────
        summary_path = settings.REPORTS_DIR / repo_id / "summary.json"
        summary_data: Dict[str, Any] = {}
        if summary_path.exists():
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary_data = json.load(f)
            except Exception:
                pass

        # ── Load quality.json ──────────────────────────────────────────────
        quality_path = settings.REPORTS_DIR / repo_id / "quality.json"
        quality_data: Dict[str, Any] = {}
        if quality_path.exists():
            try:
                with open(quality_path, "r", encoding="utf-8") as f:
                    quality_data = json.load(f)
            except Exception:
                pass

        # ── Resolve display name (Priority: DB → summary → fallback) ──────
        repo_name = (
            db_entry.get("repo_name")
            or summary_data.get("repo_name")
            or summary_data.get("repository_name")
            or f"Repo-{repo_id[:8]}"
        )
        owner = (
            db_entry.get("owner")
            or summary_data.get("owner")
            or "local"
        )

        # ── Resolve status ─────────────────────────────────────────────────
        has_summary = summary_path.exists()
        if status_data.get("status") not in ("unknown",):
            repo_status   = status_data["status"]
            repo_progress = status_data["progress"]
            repo_message  = status_data["message"]
        elif has_summary:
            repo_status   = "completed"
            repo_progress = 100
            repo_message  = "Repository indexed and ready"
        else:
            repo_status   = "unknown"
            repo_progress = 0
            repo_message  = "Repository execution record not found"

        repositories.append({
            "id":             repo_id,
            "name":           repo_name,
            "owner":          owner,
            "status":         repo_status,
            "progress":       repo_progress,
            "message":        repo_message,
            "languages":      db_entry.get("languages") or summary_data.get("languages", {}),
            "frameworks":     db_entry.get("frameworks") or summary_data.get("frameworks", []),
            "file_count":     summary_data.get("file_count", 0),
            "total_lines":    summary_data.get("total_lines", 0),
            "chunk_count":    db_entry.get("chunk_count") or summary_data.get("chunk_count", 0),
            "vector_count":   db_entry.get("vector_count", 0),
            "quality_score":  db_entry.get("quality_score") or quality_data.get("overall", 0),
        })

    return repositories


# ── Status ─────────────────────────────────────────────────────────────────────

@router.get("/{id}/status", response_model=Dict[str, Any])
def get_repository_status(id: str):
    """Queries current task progress."""
    return RepositoryProcessor.get_status(id)


# ── Detail ─────────────────────────────────────────────────────────────────────

@router.get("/{id}", response_model=Dict[str, Any])
def get_repository_details(id: str):
    """
    Returns full catalog statistics for the repository dashboard.
    Merges summary.json + manifest.json + quality.json + DB record.
    """
    summary_path = settings.REPORTS_DIR / id / "summary.json"
    if not summary_path.exists():
        status_data = RepositoryProcessor.get_status(id)
        if status_data["status"] != "unknown":
            return status_data
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not indexed or doesn't exist"
        )

    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read repository summary: {str(e)}"
        )

    # Enrich from DB registry
    try:
        db_entry = RepositoryModel.get_by_id(id) or {}
    except Exception:
        db_entry = {}

    # Enrich from manifest
    manifest_path = settings.REPORTS_DIR / id / "manifest.json"
    manifest_data: Dict[str, Any] = {}
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except Exception:
            pass

    # Enrich from quality
    quality_path = settings.REPORTS_DIR / id / "quality.json"
    quality_data: Dict[str, Any] = {}
    if quality_path.exists():
        try:
            with open(quality_path, "r", encoding="utf-8") as f:
                quality_data = json.load(f)
        except Exception:
            pass

    # ── Resolve display name ──────────────────────────────────────────────────
    repo_name = (
        db_entry.get("repo_name")
        or manifest_data.get("repo_name")
        or data.get("repo_name")
        or data.get("repository_name")
        or f"Repo-{id[:8]}"
    )

    data["id"]            = id
    data["name"]          = repo_name
    data["owner"]         = db_entry.get("owner") or manifest_data.get("owner", "local")
    data["quality_score"] = quality_data.get("overall") or db_entry.get("quality_score", 0)
    data["manifest"]      = manifest_data
    data["quality"]       = quality_data

    return data


# ── File content ───────────────────────────────────────────────────────────────

@router.get("/{id}/file", response_model=Dict[str, str])
def get_repository_file(id: str, path: str):
    """Retrieves the raw text contents of a file inside the repository workspace."""
    workspace_path = settings.WORKSPACES_DIR / id
    file_path      = (workspace_path / path).resolve()

    if not str(file_path).startswith(str(workspace_path.resolve())):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return {"content": f.read()}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── Delete ─────────────────────────────────────────────────────────────────────

@router.delete("/{id}", response_model=Dict[str, str])
def delete_repository(id: str):
    """Deletes the repository workspace files and vector indexes."""
    workspace = settings.WORKSPACES_DIR / id
    reports   = settings.REPORTS_DIR   / id

    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)

    if reports.exists():
        shutil.rmtree(reports, ignore_errors=True)

    VectorStore.delete_repository(id)
    RepositoryModel.delete(id)

    if id in RepositoryProcessor.processing_status:
        del RepositoryProcessor.processing_status[id]

    return {"status": "success", "message": f"Repository {id} deleted successfully."}
