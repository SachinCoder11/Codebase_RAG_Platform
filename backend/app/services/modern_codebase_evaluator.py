import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.core.config import settings

logger = logging.getLogger(__name__)

class ModernCodebaseEvaluator:
    """
    Evaluates a repository against the specific 'Modern Codebase Submission Checklist'.
    """

    @classmethod
    def evaluate(
        cls,
        repo_id: str,
        workspace_path: Path,
        summary_data: Dict[str, Any],
        security_data: Dict[str, Any],
        quality_data: Dict[str, Any],
        dependency_data: Dict[str, Any],
        git_data: Dict[str, Any],
        arch_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        
        # Extract base properties
        languages = [l.lower() for l in summary_data.get("languages", {}).keys()]
        if not languages and "languages" in summary_data.get("manifest", {}):
            languages = [l.lower() for l in summary_data["manifest"]["languages"]]
            
        repo_name = summary_data.get("repo_name", "").lower()
        desc = (git_data.get("description") or "").lower()
        is_github = git_data.get("owner") != "local" and "error" not in git_data

        # --- 1. Preferred Technologies ---
        preferred_techs = ["python", "typescript", "javascript", "go", "rust", "ruby", "swift", "kotlin"]
        tech_results = []
        for tech in preferred_techs:
            tech_results.append({
                "criterion": tech.capitalize() if tech != "javascript" else "JavaScript",
                "passed": tech in languages
            })
            if tech == "typescript":
                tech_results[-1]["criterion"] = "TypeScript"

        # --- 2. Repository Requirements ---
        pushed_at = git_data.get("pushed_at")
        active_history = False
        if pushed_at:
            try:
                pushed_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                active_history = (now - pushed_dt).days <= 365
            except Exception:
                active_history = True
                
        test_score = quality_data.get("testing", 0)
        ci_cd_score = quality_data.get("ci_cd", 0)

        repo_reqs = [
            {"criterion": "Hosted on GitHub, GitLab, or Bitbucket", "passed": is_github},
            {"criterion": "Active development history", "passed": active_history or not is_github}, # local assume active
            {"criterion": "Meaningful commit history", "passed": git_data.get("commits", 10) > 5 or not is_github},
            {"criterion": "Pull Requests and code reviews", "passed": git_data.get("open_pr_count", 0) > 0 or not is_github},
            {"criterion": "Issue tracking and bug-fix history", "passed": git_data.get("open_issues", 0) > 0 or not is_github},
            {"criterion": "Meaningful test coverage", "passed": test_score >= 5},
            {"criterion": "Modern development workflows", "passed": ci_cd_score > 0},
        ]

        # --- 3. Preferred Characteristics ---
        app_type = (arch_data.get("application_type") or "Unknown").lower()
        frameworks = [f.lower() for f in arch_data.get("frameworks", [])]
        
        is_web = app_type == "web" or "react" in frameworks or "vue" in frameworks or "express" in frameworks or "django" in frameworks
        is_cloud = bool(arch_data.get("deployment"))
        is_api = "fastapi" in frameworks or "flask" in frameworks or "express" in frameworks
        is_ml = "tensorflow" in frameworks or "pytorch" in frameworks or "scikit-learn" in frameworks or "langchain" in frameworks
        is_mobile = "react-native" in frameworks or "flutter" in frameworks or "swift" in languages or "kotlin" in languages

        chars = [
            {"criterion": "SaaS Applications", "passed": is_web and is_cloud},
            {"criterion": "Web Applications", "passed": is_web},
            {"criterion": "Cloud-Native Applications", "passed": is_cloud},
            {"criterion": "AI/ML Applications", "passed": is_ml},
            {"criterion": "Mobile Applications", "passed": is_mobile},
            {"criterion": "Developer Tools", "passed": "cli" in desc or "tool" in desc},
            {"criterion": "APIs and Backend Services", "passed": is_api},
            {"criterion": "Platform Engineering Projects", "passed": "kubernetes" in desc or "docker" in desc or is_cloud},
        ]

        # --- 4. Engineering Quality ---
        docs_score = quality_data.get("documentation", 0)
        sec_score = security_data.get("score", 100)
        
        quality_reqs = [
            {"criterion": "Well-structured code", "passed": quality_data.get("architecture", 0) >= 10},
            {"criterion": "Modern architecture patterns", "passed": bool(frameworks)},
            {"criterion": "CI/CD pipelines", "passed": ci_cd_score > 0},
            {"criterion": "Automated testing", "passed": test_score >= 5},
            {"criterion": "Documentation", "passed": docs_score >= 8},
            {"criterion": "Security best practices", "passed": sec_score >= 80},
            {"criterion": "Clear configuration management", "passed": quality_data.get("configuration", 0) >= 5},
        ]

        # --- 5. Ownership & Rights ---
        ownership = [
            {"criterion": "Private repository preferred", "passed": not is_github}, # We assume local upload is private
            {"criterion": "Repository owner has legal ownership or authority", "passed": True}, # Assumed for submission
            {"criterion": "Commercial usage rights can be provided if required", "passed": True}, # Assumed
        ]

        # --- 6. Not Preferred (True means it DOES NOT violate) ---
        is_tutorial = "tutorial" in repo_name or "tutorial" in desc or "learn" in repo_name
        is_demo = "demo" in repo_name or "demo" in desc or "example" in repo_name
        is_student = "homework" in desc or "assignment" in desc or "student" in desc
        is_small = summary_data.get("total_lines", 0) < 500
        is_inactive = not active_history and is_github
        is_experimental = "experiment" in desc or "poc" in desc

        not_pref = [
            {"criterion": "Tutorial projects", "passed": not is_tutorial},
            {"criterion": "Demo applications", "passed": not is_demo},
            {"criterion": "Student projects", "passed": not is_student},
            {"criterion": "Small personal projects", "passed": not is_small},
            {"criterion": "Inactive repositories", "passed": not is_inactive},
            {"criterion": "Repositories with little development history", "passed": not is_inactive and not is_small},
            {"criterion": "Experimental code with no real-world usage", "passed": not is_experimental},
        ]

        # --- 7. Before Submission (Metadata) ---
        loc = summary_data.get("total_lines", summary_data.get("manifest", {}).get("total_lines", 0))
        contributors = git_data.get("contributor_count", 1)
        age = "Unknown"
        created_at = git_data.get("created_at")
        if created_at:
            try:
                c_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                age = f"{(now - c_dt).days // 365} years" if (now - c_dt).days >= 365 else f"{(now - c_dt).days // 30} months"
            except: pass

        metadata = {
            "technology_stack": list(summary_data.get("languages", {}).keys())[:3] or frameworks[:3],
            "repository_age": age,
            "business_domain": app_type.capitalize(),
            "loc": loc,
            "contributors": contributors,
            "ownership_status": "Private/Local" if not is_github else "Public GitHub",
            "description": git_data.get("description") or "Local repository analysis."
        }

        result = {
            "technologies": tech_results,
            "requirements": repo_reqs,
            "characteristics": chars,
            "quality": quality_reqs,
            "ownership": ownership,
            "not_preferred": not_pref,
            "metadata": metadata
        }
        
        cls._save(repo_id, result)
        return result

    @classmethod
    def _save(cls, repo_id: str, result: Dict[str, Any]) -> None:
        report_dir = settings.REPORTS_DIR / repo_id
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / "modern_codebase.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        except Exception as e:
            logger.warning(f"[ModernCodebase] Failed to save modern_codebase.json: {e}")

    @classmethod
    def load(cls, repo_id: str) -> Dict[str, Any]:
        path = settings.REPORTS_DIR / repo_id / "modern_codebase.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
