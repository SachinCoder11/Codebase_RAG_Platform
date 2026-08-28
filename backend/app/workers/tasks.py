import logging
import asyncio
from celery.exceptions import SoftTimeLimitExceeded

from app.workers.celery_app import celery_app
from app.services.repository_processor import RepositoryProcessor
from app.services.ingestion import IngestionService
from app.services.repository_identity import RepositoryIdentityService

logger = logging.getLogger(__name__)

@celery_app.task(
    name="app.workers.tasks.process_zip_repository",
    bind=True,
    soft_time_limit=1800,  # 30 minutes
    time_limit=1860
)
def process_zip_repository(self, repo_id: str, temp_zip_path_str: str, archive_name: str):
    logger.info(f"[Celery] Starting ZIP processing for workspace: {repo_id}")
    try:
        from pathlib import Path
        temp_zip_path = Path(temp_zip_path_str)
        workspace_path = IngestionService.create_upload_workspace(repo_id, temp_zip_path)

        if temp_zip_path.exists():
            temp_zip_path.unlink()

        identity = RepositoryIdentityService.identify_zip_repo(workspace_path, archive_name)
        identity["repo_id"] = repo_id

        asyncio.run(RepositoryProcessor.process_repository(
            repo_id, identity["repo_name"], workspace_path, identity
        ))
        return {"status": "success", "repo_id": repo_id}
    except SoftTimeLimitExceeded:
        logger.error(f"[Celery] Timeout processing workspace: {repo_id}")
        RepositoryProcessor.update_processing_status(repo_id, "failed", 100, "Timeout during processing")
        return {"status": "error", "error": "Timeout"}
    except Exception as e:
        logger.exception(f"[Celery] Error processing workspace {repo_id}: {e}")
        RepositoryProcessor.update_processing_status(repo_id, "failed", 100, f"Extraction failed: {str(e)}")
        return {"status": "error", "error": str(e)}

@celery_app.task(
    name="app.workers.tasks.process_git_repository",
    bind=True,
    soft_time_limit=1800,
    time_limit=1860
)
def process_git_repository(self, repo_id: str, url_str: str, branch: str):
    logger.info(f"[Celery] Starting Git processing for workspace: {repo_id}")
    try:
        RepositoryProcessor.update_processing_status(
            repo_id=repo_id, status="processing", progress=5,
            message=f"Cloning branch '{branch}' from remote repository..."
        )
        workspace_path = IngestionService.create_clone_workspace(repo_id, url_str, branch)

        import re
        m = re.search(r'github\.com/([^/]+)/([^/.]+)', url_str)
        if m:
            identity = RepositoryIdentityService.identify_github_repo(url_str)
        else:
            parts    = url_str.split("/")
            raw_name = parts[-1].replace(".git", "") if parts else "repository"
            identity = {
                "repo_id":    repo_id,
                "repo_name":  raw_name.replace("-", " ").replace("_", " ").title(),
                "owner":      parts[-2] if len(parts) >= 2 else "unknown",
                "source_type":"github",
                "source_url": url_str,
            }

        identity["repo_id"] = repo_id

        asyncio.run(RepositoryProcessor.process_repository(
            repo_id, identity["repo_name"], workspace_path, identity
        ))
        return {"status": "success", "repo_id": repo_id}
    except SoftTimeLimitExceeded:
        logger.error(f"[Celery] Timeout processing workspace: {repo_id}")
        RepositoryProcessor.update_processing_status(repo_id, "failed", 100, "Timeout during processing")
        return {"status": "error", "error": "Timeout"}
    except Exception as e:
        logger.exception(f"[Celery] Error processing workspace {repo_id}: {e}")
        RepositoryProcessor.update_processing_status(repo_id, "failed", 100, f"Git clone failed: {str(e)}")
        return {"status": "error", "error": str(e)}
