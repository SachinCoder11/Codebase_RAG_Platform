import os
import json
import re
from pathlib import Path
from typing import Dict, Any

class RepositoryIdentityService:
    @classmethod
    def identify_github_repo(cls, url: str) -> Dict[str, Any]:
        """
        Extract identity from a GitHub URL.
        Example: https://github.com/tiangolo/fastapi
        """
        match = re.search(r'github\.com/([^/]+)/([^/.]+)', url)
        owner = match.group(1) if match else "unknown"
        repo_name_raw = match.group(2) if match else "unknown_repo"
        
        # Make a friendly display name out of raw repo name
        repo_name = repo_name_raw.replace("-", " ").replace("_", " ").title()
        
        # We can use the raw string as repo_id
        repo_id = f"{owner}_{repo_name_raw}"
        
        return {
            "repo_id": repo_id,
            "repo_name": repo_name,
            "owner": owner,
            "source_type": "github",
            "source_url": url
        }

    @classmethod
    def identify_zip_repo(cls, workspace_path: Path, archive_filename: str) -> Dict[str, Any]:
        """
        Detect identity from extracted ZIP contents using priority heuristics.
        1. Root folder name
        2. package.json name
        3. pyproject.toml name
        4. setup.py name
        5. pom.xml artifact name
        6. archive filename
        """
        repo_name = ""
        
        # Scan root files for priority metadata files
        if workspace_path.exists():
            pkg_json = workspace_path / "package.json"
            if pkg_json.exists():
                try:
                    with open(pkg_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if "name" in data:
                            repo_name = data["name"]
                except: pass

            if not repo_name:
                pyproject = workspace_path / "pyproject.toml"
                if pyproject.exists():
                    try:
                        with open(pyproject, "r", encoding="utf-8") as f:
                            content = f.read()
                            match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                            if match:
                                repo_name = match.group(1)
                    except: pass

            if not repo_name:
                setup_py = workspace_path / "setup.py"
                if setup_py.exists():
                    try:
                        with open(setup_py, "r", encoding="utf-8") as f:
                            content = f.read()
                            match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                            if match:
                                repo_name = match.group(1)
                    except: pass

            if not repo_name:
                pom_xml = workspace_path / "pom.xml"
                if pom_xml.exists():
                    try:
                        with open(pom_xml, "r", encoding="utf-8") as f:
                            content = f.read()
                            match = re.search(r'<artifactId>([^<]+)</artifactId>', content)
                            if match:
                                repo_name = match.group(1)
                    except: pass
                    
            # Fallback to root folder name
            if not repo_name:
                items = list(workspace_path.iterdir())
                # If there's a single root directory extracted from zip
                if len(items) == 1 and items[0].is_dir():
                    repo_name = items[0].name

        # Fallback to archive filename
        if not repo_name:
            repo_name = archive_filename.rsplit(".", 1)[0]
            
        # Cleanup name
        display_name = repo_name.replace("-", " ").replace("_", " ").title()
        
        return {
            "repo_id": repo_name.lower().replace(" ", "_"),
            "repo_name": display_name,
            "owner": "local",
            "source_type": "zip",
            "source_url": f"file://{archive_filename}"
        }
