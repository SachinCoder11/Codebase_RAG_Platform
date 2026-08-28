# backend/app/services/repository_manifest.py
"""
RepositoryManifest — Repository-Level Metadata Engine
======================================================
Generates a rich manifest JSON during ingestion that captures:
  - Languages, frameworks, total counts
  - Detected routes, services, models, middlewares
  - Infrastructure presence (Docker, CI/CD, tests)
  - Dependencies list

The manifest is:
  1. Written to disk: data/reports/{repo_id}/manifest.json
  2. Stored in SQLite (JSON blob in repositories.manifest column)
  3. Injected into LLM prompts by ContextBuilder for grounded answers
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class RepositoryManifest:
    """Generates and persists the repository-level intelligence manifest."""

    # ── Infrastructure detection file patterns ────────────────────────────────
    _DOCKER_FILES      = {"Dockerfile", "docker-compose.yml", "docker-compose.yaml"}
    _CICD_PATHS        = {".github/workflows", ".circleci", ".gitlab-ci.yml",
                          "Jenkinsfile", ".travis.yml", "azure-pipelines.yml"}
    _TEST_PATTERNS     = {"test_", "_test.", ".spec.", ".test.", "tests/", "__tests__/"}
    _EXCLUDED_DIRS     = {".git", "node_modules", "venv", ".venv", "__pycache__",
                          "dist", "build", ".idea", ".vscode"}

    @classmethod
    def generate(
        cls,
        repo_id: str,
        repo_name: str,
        owner: str,
        source_type: str,
        scan_results: Dict[str, Any],
        entities: List[Dict[str, Any]],
        workspace_path: Path,
    ) -> Dict[str, Any]:
        """
        Generates the full repository manifest from scan + entity data.

        Args:
            repo_id       : Repository identifier
            repo_name     : Human-readable name
            owner         : Owner / organization
            source_type   : "github" | "zip"
            scan_results  : Output of RepositoryScanner.scan_repository()
            entities      : Output of CodeParserAnalyzer.analyze_workspace()
            workspace_path: Local workspace directory

        Returns:
            Manifest dict (also written to disk)
        """
        # ── Count code entity types ────────────────────────────────────────
        classes     = sum(1 for e in entities if e.get("type") == "class")
        functions   = sum(1 for e in entities if e.get("type") in ("function", "method"))
        routes      = sum(1 for e in entities if e.get("chunk_type") == "route")
        services    = sum(1 for e in entities if e.get("chunk_type") == "service")
        models      = sum(1 for e in entities if e.get("chunk_type") == "model")
        middlewares = sum(1 for e in entities if e.get("chunk_type") == "middleware")

        # ── Infrastructure detection ────────────────────────────────────────
        docker_present         = cls._detect_docker(workspace_path)
        github_actions_present = cls._detect_cicd(workspace_path)
        tests_present          = cls._detect_tests(workspace_path, scan_results)

        # ── Dependencies ────────────────────────────────────────────────────
        dependencies = cls._extract_dependencies(workspace_path)

        manifest: Dict[str, Any] = {
            "repo_id":                  repo_id,
            "repo_name":                repo_name,
            "owner":                    owner,
            "source_type":              source_type,
            "languages":                list(scan_results.get("languages", {}).keys()),
            "language_distribution":    scan_results.get("languages", {}),
            "frameworks":               scan_results.get("frameworks", []),
            "total_files":              scan_results.get("file_count", 0),
            "total_lines":              scan_results.get("total_lines", 0),
            "classes":                  classes,
            "functions":                functions,
            "routes":                   routes,
            "services":                 services,
            "models":                   models,
            "middlewares":              middlewares,
            "dependencies":             dependencies,
            "docker_present":           docker_present,
            "github_actions_present":   github_actions_present,
            "tests_present":            tests_present,
        }

        cls.save(repo_id, manifest)
        logger.info(f"[Manifest] Generated for '{repo_id}': {classes} classes, {functions} functions, {routes} routes")
        return manifest

    # ── Persistence ───────────────────────────────────────────────────────────

    @classmethod
    def save(cls, repo_id: str, manifest: Dict[str, Any]) -> None:
        """Writes manifest.json to data/reports/{repo_id}/."""
        report_dir = settings.REPORTS_DIR / repo_id
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / "manifest.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        logger.debug(f"[Manifest] Saved → {path}")

    @classmethod
    def load(cls, repo_id: str) -> Dict[str, Any]:
        """Loads manifest from disk. Returns {} if not found."""
        path = settings.REPORTS_DIR / repo_id / "manifest.json"
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[Manifest] Failed to load '{repo_id}': {e}")
            return {}

    @classmethod
    def format_for_prompt(cls, manifest: Dict[str, Any]) -> str:
        """
        Formats manifest as a compact XML block for LLM prompt injection.
        Keeps it short to not consume too many tokens.
        """
        if not manifest:
            return ""
        lines = [
            "<repository_manifest>",
            f"  <name>{manifest.get('repo_name', 'Unknown')}</name>",
            f"  <owner>{manifest.get('owner', 'Unknown')}</owner>",
            f"  <languages>{', '.join(manifest.get('languages', []))}</languages>",
            f"  <frameworks>{', '.join(manifest.get('frameworks', []))}</frameworks>",
            f"  <total_files>{manifest.get('total_files', 0)}</total_files>",
            f"  <total_lines>{manifest.get('total_lines', 0):,}</total_lines>",
            f"  <classes>{manifest.get('classes', 0)}</classes>",
            f"  <functions>{manifest.get('functions', 0)}</functions>",
            f"  <routes>{manifest.get('routes', 0)}</routes>",
            f"  <services>{manifest.get('services', 0)}</services>",
            f"  <models>{manifest.get('models', 0)}</models>",
            f"  <docker>{manifest.get('docker_present', False)}</docker>",
            f"  <ci_cd>{manifest.get('github_actions_present', False)}</ci_cd>",
            f"  <tests>{manifest.get('tests_present', False)}</tests>",
        ]
        deps = manifest.get("dependencies", [])
        if deps:
            lines.append(f"  <dependencies>{', '.join(deps[:20])}</dependencies>")
        lines.append("</repository_manifest>")
        return "\n".join(lines)

    # ── Infrastructure detectors ──────────────────────────────────────────────

    @classmethod
    def _detect_docker(cls, workspace_path: Path) -> bool:
        for fname in cls._DOCKER_FILES:
            if (workspace_path / fname).exists():
                return True
        # Also check one level deep
        for item in workspace_path.iterdir():
            if item.is_dir() and item.name not in cls._EXCLUDED_DIRS:
                for fname in cls._DOCKER_FILES:
                    if (item / fname).exists():
                        return True
        return False

    @classmethod
    def _detect_cicd(cls, workspace_path: Path) -> bool:
        for pattern in cls._CICD_PATHS:
            candidate = workspace_path / pattern
            if candidate.exists():
                return True
        return False

    @classmethod
    def _detect_tests(cls, workspace_path: Path, scan_results: Dict[str, Any]) -> bool:
        indexed_files = scan_results.get("indexed_files", [])
        for f in indexed_files:
            fp = f.get("file_path", "").lower()
            for pattern in cls._TEST_PATTERNS:
                if pattern in fp:
                    return True
        return False

    @classmethod
    def _extract_dependencies(cls, workspace_path: Path) -> List[str]:
        """Best-effort dependency extraction from common manifest files."""
        deps: List[str] = []

        # Python
        req_path = workspace_path / "requirements.txt"
        if req_path.exists():
            try:
                with open(req_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            # Strip version specifiers
                            pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip()
                            if pkg:
                                deps.append(pkg)
            except Exception:
                pass

        # pyproject.toml (basic)
        pp_path = workspace_path / "pyproject.toml"
        if pp_path.exists() and not deps:
            try:
                import re
                with open(pp_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                for match in re.finditer(r'"([a-zA-Z0-9_\-]+)(?:[>=<~!][^"]*)?"\s*,', content):
                    deps.append(match.group(1))
            except Exception:
                pass

        # Node.js
        pkg_path = workspace_path / "package.json"
        if pkg_path.exists() and not deps:
            try:
                import json
                with open(pkg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                deps = list(all_deps.keys())
            except Exception:
                pass

        return deps[:50]  # cap at 50 to avoid bloat
