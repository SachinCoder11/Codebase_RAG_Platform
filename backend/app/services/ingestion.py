import os
import shutil
import zipfile
from pathlib import Path
import git
from app.core.config import settings

class IngestionService:
    @staticmethod
    def validate_zip(file_path: Path) -> bool:
        """
        Validate ZIP by checking its header (magic bytes: PK..)
        """
        if not file_path.exists():
            return False
        try:
            with open(file_path, "rb") as f:
                header = f.read(4)
                return header == b"PK\x03\x04"
        except Exception:
            return False

    @staticmethod
    def extract_zip(zip_path: Path, extract_to: Path) -> Path:
        """
        Safe extraction checking for zip-slip (path traversal) vulnerabilities.
        """
        extract_to.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.infolist():
                # Resolve destination path
                filename = member.filename
                # Path traversal check
                target_path = Path(os.path.abspath(extract_to / filename))
                base_path = Path(os.path.abspath(extract_to))
                
                # Check that target_path starts with base_path
                if not str(target_path).startswith(str(base_path)):
                    raise Exception(f"Potential Path Traversal Attack detected in ZIP: {filename}")
                
                # Extract
                if member.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zip_ref.open(member) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                        
        return extract_to

    @staticmethod
    def clone_repository(repo_url: str, branch: str, clone_to: Path) -> Path:
        """
        Clones a repository from a git URL.
        """
        clone_to.mkdir(parents=True, exist_ok=True)
        try:
            # Shallow clone for efficiency
            git.Repo.clone_from(repo_url, clone_to, branch=branch, depth=1)
            # Remove the .git directory to avoid scanning it later
            git_dir = clone_to / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir, ignore_errors=True)
            return clone_to
        except Exception as e:
            # Clean up on failure
            if clone_to.exists():
                shutil.rmtree(clone_to, ignore_errors=True)
            raise Exception(f"Failed to clone repository: {str(e)}")
            
    @classmethod
    def create_upload_workspace(cls, repo_id: str, zip_file_path: Path) -> Path:
        """
        Takes uploaded zip, validates and extracts it.
        """
        if not cls.validate_zip(zip_file_path):
            raise Exception("Invalid ZIP file format")
            
        workspace_path = settings.WORKSPACES_DIR / repo_id
        cls.extract_zip(zip_file_path, workspace_path)
        return workspace_path
        
    @classmethod
    def create_clone_workspace(cls, repo_id: str, repo_url: str, branch: str = "main") -> Path:
        """
        Clones a repository into a workspace.
        """
        workspace_path = settings.WORKSPACES_DIR / repo_id
        cls.clone_repository(repo_url, branch, workspace_path)
        return workspace_path
