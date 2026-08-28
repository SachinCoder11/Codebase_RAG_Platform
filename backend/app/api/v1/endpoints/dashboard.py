# backend/app/api/v1/endpoints/dashboard.py
"""
Dashboard API — Due Diligence Intelligence Endpoints
=====================================================
Serves all structured intelligence data for the executive dashboard.

Endpoints:
  GET /api/v1/dashboard/{id}             — Full due diligence bundle
  GET /api/v1/dashboard/{id}/submission  — Submission readiness
  GET /api/v1/dashboard/{id}/compliance  — Compliance checklist only
  GET /api/v1/dashboard/{id}/dependencies— Dependency intelligence
  GET /api/v1/dashboard/{id}/license     — License analysis
  POST /api/v1/dashboard/{id}/generate   — Generate all reports & return paths
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.services.submission_engine   import SubmissionEngine
from app.services.dependency_analyzer import DependencyAnalyzer
from app.services.license_analyzer    import LicenseAnalyzer
from app.services.report_writer       import ReportWriter

router = APIRouter()
logger = logging.getLogger("dashboard_endpoint")


def _load_json(repo_id: str, filename: str) -> Dict[str, Any]:
    """Load a JSON artifact from the reports directory."""
    path = settings.REPORTS_DIR / repo_id / filename
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _require_repo(repo_id: str) -> None:
    """Raises 404 if the repo workspace doesn't exist."""
    workspace = settings.WORKSPACES_DIR / repo_id
    reports   = settings.REPORTS_DIR   / repo_id
    if not workspace.exists() and not (reports / "summary.json").exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repo_id}' not found or not yet indexed."
        )


def _build_full_bundle(repo_id: str) -> Dict[str, Any]:
    """
    Assembles the full due diligence intelligence bundle for a given repo.
    Lazy-computes submission, dependency, and license data if not cached.
    """
    workspace_path = settings.WORKSPACES_DIR / repo_id

    # ── Load pre-computed intelligence ───────────────────────────────────
    summary      = _load_json(repo_id, "summary.json")
    manifest     = _load_json(repo_id, "manifest.json")
    quality      = _load_json(repo_id, "quality.json")
    security     = _load_json(repo_id, "security.json")
    arch_summary = _load_json(repo_id, "summary.json")  # architecture is embedded in summary
    git_activity = _load_json(repo_id, "git_activity.json")

    # ── Lazy-compute if not cached ────────────────────────────────────────
    # Submission
    submission = _load_json(repo_id, "submission.json")
    if not submission:
        try:
            submission = SubmissionEngine.evaluate(repo_id)
        except Exception as e:
            logger.warning(f"[Dashboard] Submission eval failed for '{repo_id}': {e}")
            submission = {}

    # Dependencies
    dependencies = _load_json(repo_id, "dependencies.json")
    if not dependencies and workspace_path.exists():
        try:
            dependencies = DependencyAnalyzer.analyze(workspace_path, repo_id)
        except Exception as e:
            logger.warning(f"[Dashboard] Dependency analysis failed for '{repo_id}': {e}")
            dependencies = {}

    # License
    license_data = _load_json(repo_id, "license.json")
    if not license_data and workspace_path.exists():
        try:
            license_data = LicenseAnalyzer.analyze(workspace_path, repo_id)
        except Exception as e:
            logger.warning(f"[Dashboard] License analysis failed for '{repo_id}': {e}")
            license_data = {}

    # ── Build overview panel data ─────────────────────────────────────────
    repo_name = (
        manifest.get("repo_name")
        or summary.get("repo_name")
        or summary.get("repository_name")
        or f"Repo-{repo_id[:8]}"
    )
    owner = manifest.get("owner") or summary.get("owner", "local")

    # Architecture data lives inside summary.json under "architecture" key
    architecture = summary.get("architecture", {})
    if not architecture:
        # Try loading from ARCHITECTURE_SUMMARY within quality data
        architecture = {
            "application_type": "Unknown",
            "frameworks":       manifest.get("frameworks", []),
            "database_layer":   [],
            "auth_mechanism":   [],
            "deployment":       [],
            "ci_cd":            [],
            "entry_points":     [],
            "routes":           [],
            "services":         [],
            "models":           [],
            "route_count":      manifest.get("routes", 0),
            "service_count":    manifest.get("services", 0),
            "model_count":      manifest.get("models", 0),
        }

    overview = {
        "repo_id":     repo_id,
        "repo_name":   repo_name,
        "owner":       owner,
        "source_url":  summary.get("source_url", manifest.get("source_url", "Local upload")),
        "source_type": manifest.get("source_type", "zip"),
        "languages":   manifest.get("language_distribution") or summary.get("languages", {}),
        "frameworks":  manifest.get("frameworks") or summary.get("frameworks", []),
        "total_files": manifest.get("total_files") or summary.get("file_count", 0),
        "total_lines": manifest.get("total_lines") or summary.get("total_lines", 0),
        "classes":     manifest.get("classes", 0),
        "functions":   manifest.get("functions", 0),
        "docker":      manifest.get("docker_present", False),
        "ci_cd":       manifest.get("github_actions_present", False),
        "tests":       manifest.get("tests_present", False),
        "created_at":  git_activity.get("created_at", ""),
        "pushed_at":   git_activity.get("pushed_at", ""),
        "contributors":git_activity.get("contributor_count", 0),
    }

    return {
        "repo_id":      repo_id,
        "overview":     overview,
        "quality":      quality,
        "security": {
            "score":    security.get("score", 100),
            "counts":   security.get("counts", {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}),
            "findings": security.get("findings", [])[:50],  # limit payload
        },
        "architecture": architecture,
        "git_activity": git_activity,
        "submission":   submission,
        "dependencies": dependencies,
        "license":      license_data,
        "modern":       summary.get("modern", _load_json(repo_id, "modern_codebase.json")),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{id}", response_model=Dict[str, Any])
def get_dashboard(id: str):
    """
    Returns the full due diligence intelligence bundle for the dashboard.
    Lazy-computes any missing analysis components.
    """
    _require_repo(id)
    try:
        return _build_full_bundle(id)
    except Exception as e:
        logger.error(f"[Dashboard] Bundle build failed for '{id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assemble dashboard data: {str(e)}"
        )


@router.get("/{id}/submission", response_model=Dict[str, Any])
def get_submission_readiness(id: str):
    """Returns just the submission readiness score and checklist."""
    _require_repo(id)
    try:
        cached = _load_json(id, "submission.json")
        return cached if cached else SubmissionEngine.evaluate(id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{id}/compliance", response_model=Dict[str, Any])
def get_compliance_checklist(id: str):
    """Returns the Modern Codebase Compliance checklist."""
    _require_repo(id)
    try:
        submission = _load_json(id, "submission.json") or SubmissionEngine.evaluate(id)
        return {
            "checklist":       submission.get("checklist", {}),
            "passed_checks":   submission.get("passed_checks", 0),
            "total_checks":    submission.get("total_checks", 8),
            "checklist_summary": submission.get("checklist_summary", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{id}/dependencies", response_model=Dict[str, Any])
def get_dependencies(id: str):
    """Returns dependency intelligence analysis."""
    _require_repo(id)
    workspace_path = settings.WORKSPACES_DIR / id
    try:
        cached = _load_json(id, "dependencies.json")
        if cached:
            return cached
        if workspace_path.exists():
            return DependencyAnalyzer.analyze(workspace_path, id)
        return {"total_count": 0, "risk_score": 100, "dependencies": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{id}/license", response_model=Dict[str, Any])
def get_license(id: str):
    """Returns license detection and legal compatibility."""
    _require_repo(id)
    workspace_path = settings.WORKSPACES_DIR / id
    try:
        cached = _load_json(id, "license.json")
        if cached:
            return cached
        if workspace_path.exists():
            return LicenseAnalyzer.analyze(workspace_path, id)
        return {"license_id": "Unknown", "category": "UNKNOWN"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{id}/modern", response_model=Dict[str, Any])
def get_modern_codebase(id: str):
    """Returns modern codebase evaluation."""
    _require_repo(id)
    try:
        cached = _load_json(id, "modern_codebase.json")
        if cached:
            return cached
        bundle = _build_full_bundle(id)
        return bundle.get("modern", {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compare/{repoA}/{repoB}", response_model=Dict[str, Any])
def compare_repositories(repoA: str, repoB: str):
    """Compares two repositories side-by-side."""
    _require_repo(repoA)
    _require_repo(repoB)
    try:
        bundleA = _build_full_bundle(repoA)
        bundleB = _build_full_bundle(repoB)
        
        # Calculate comparison score based on some heuristic
        qualityA = bundleA.get("quality", {}).get("overall", 0)
        qualityB = bundleB.get("quality", {}).get("overall", 0)
        
        secA = bundleA.get("security", {}).get("score", 0)
        secB = bundleB.get("security", {}).get("score", 0)
        
        modA = bundleA.get("modern", {}).get("score", 0)
        modB = bundleB.get("modern", {}).get("score", 0)
        
        scoreA = (qualityA + secA + modA) / 3
        scoreB = (qualityB + secB + modB) / 3

        return {
            "repoA": bundleA,
            "repoB": bundleB,
            "comparison": {
                "scoreA": scoreA,
                "scoreB": scoreB,
                "winner": repoA if scoreA > scoreB else repoB if scoreB > scoreA else "tie"
            }
        }
    except Exception as e:
        logger.error(f"[Dashboard] Comparison failed for '{repoA}' and '{repoB}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{id}/generate", response_model=Dict[str, Any])
def generate_all_reports(id: str):
    """
    Triggers generation of all 5 due diligence Markdown report files.
    Returns paths to generated files.
    """
    _require_repo(id)
    try:
        bundle = _build_full_bundle(id)
        paths  = ReportWriter.generate_all(id, bundle)
        return {
            "status":  "success",
            "repo_id": id,
            "reports": paths,
        }
    except Exception as e:
        logger.error(f"[Dashboard] Report generation failed for '{id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation failed: {str(e)}"
        )
