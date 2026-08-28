# backend/app/services/engineering_quality.py
"""
EngineeringQualityAnalyzer — Repository Maturity & Quality Scoring
===================================================================
Produces a scored quality report across 6 engineering dimensions.

Scoring dimensions (total 100 pts):
  Documentation    20  README, docstrings, inline comments
  Testing          20  test files, frameworks, coverage config
  CI/CD            15  GitHub Actions, CircleCI, Jenkins, etc.
  Security         15  (delegates to SecurityAnalyzer score)
  Configuration    15  typed config, .env.example, no inline secrets
  Architecture     15  layered structure, separation of concerns

Output:
  - Returns JSON dict with per-dimension scores and overall
  - Writes ENGINEERING_QUALITY_REPORT.md
  - Writes quality.json for API / dashboard use
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import settings

logger = logging.getLogger(__name__)

_EXCLUDED_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}


class EngineeringQualityAnalyzer:
    """
    Static analysis engine producing scored quality dimensions.

    Usage:
        result = EngineeringQualityAnalyzer.evaluate(
            repo_id, workspace_path, scan_results, entities, security_score
        )
    """

    @classmethod
    def evaluate(
        cls,
        repo_id: str,
        workspace_path: Path,
        scan_results: Dict[str, Any],
        entities: List[Dict[str, Any]],
        security_score: int = 100,
    ) -> Dict[str, Any]:
        """
        Runs all quality dimension evaluations and assembles the report.

        Returns:
            {
              "documentation": int,
              "testing":       int,
              "ci_cd":         int,
              "security":      int,
              "configuration": int,
              "architecture":  int,
              "overall":       int,
              "details":       { dimension: explanation_str }
            }
        """
        doc_score,   doc_detail   = cls._score_documentation(workspace_path, entities, scan_results)
        test_score,  test_detail  = cls._score_testing(workspace_path, scan_results)
        cicd_score,  cicd_detail  = cls._score_cicd(workspace_path)
        config_score,cfg_detail   = cls._score_configuration(workspace_path)
        arch_score,  arch_detail  = cls._score_architecture(workspace_path, entities, scan_results)

        # Security score comes from SecurityAnalyzer, scaled to 15 pts
        sec_contribution = round(security_score * 0.15)

        overall = (
            doc_score
            + test_score
            + cicd_score
            + sec_contribution
            + config_score
            + arch_score
        )
        overall = max(0, min(100, overall))

        result = {
            "documentation": doc_score,
            "testing":       test_score,
            "ci_cd":         cicd_score,
            "security":      sec_contribution,
            "configuration": config_score,
            "architecture":  arch_score,
            "overall":       overall,
            "details": {
                "documentation": doc_detail,
                "testing":       test_detail,
                "ci_cd":         cicd_detail,
                "security":      f"Scaled from security scan score ({security_score}/100)",
                "configuration": cfg_detail,
                "architecture":  arch_detail,
            }
        }

        cls._write_report(repo_id, result)
        logger.info(f"[Quality] '{repo_id}' overall score: {overall}/100")
        return result

    # ── Dimension Scorers ─────────────────────────────────────────────────────

    @classmethod
    def _score_documentation(
        cls,
        workspace_path: Path,
        entities: List[Dict[str, Any]],
        scan_results: Dict[str, Any],
    ) -> tuple:
        """Max 20 pts."""
        score = 0
        notes = []

        # README present (+5)
        for readme in ("README.md", "README.rst", "README.txt", "readme.md"):
            if (workspace_path / readme).exists():
                score += 5
                notes.append("README file present (+5)")
                break
        else:
            notes.append("No README found (-5 potential)")

        # CHANGELOG or CONTRIBUTING (+2)
        for fname in ("CHANGELOG.md", "CONTRIBUTING.md", "CHANGELOG"):
            if (workspace_path / fname).exists():
                score += 2
                notes.append(f"{fname} present (+2)")
                break

        # Docstrings / comments in code entities
        functions   = [e for e in entities if e.get("type") in ("function", "method")]
        has_docstring = 0
        for e in functions[:100]:
            content = e.get("content", "")
            if '"""' in content or "'''" in content or "/**" in content or "///" in content:
                has_docstring += 1
        if functions:
            docstring_pct = has_docstring / len(functions[:100])
            if docstring_pct >= 0.6:
                score += 8
                notes.append(f"{round(docstring_pct*100)}% functions have docstrings (+8)")
            elif docstring_pct >= 0.3:
                score += 4
                notes.append(f"{round(docstring_pct*100)}% functions have docstrings (+4)")
            else:
                notes.append(f"Only {round(docstring_pct*100)}% functions have docstrings")

        # Inline markdown docs in repo
        md_files = sum(
            1 for f in scan_results.get("indexed_files", [])
            if f.get("language") == "Markdown"
            and not f.get("file_path", "").startswith("docs/")
        )
        if md_files >= 3:
            score += 3
            notes.append(f"{md_files} documentation .md files (+3)")
        elif md_files >= 1:
            score += 1
            notes.append(f"{md_files} documentation .md files (+1)")

        return min(20, score), "; ".join(notes) or "No documentation signals found"

    @classmethod
    def _score_testing(
        cls,
        workspace_path: Path,
        scan_results: Dict[str, Any],
    ) -> tuple:
        """Max 20 pts."""
        score = 0
        notes = []

        indexed_files = scan_results.get("indexed_files", [])
        test_files    = [
            f for f in indexed_files
            if "test" in f.get("file_path", "").lower()
            or "spec" in f.get("file_path", "").lower()
        ]

        if test_files:
            ratio = len(test_files) / max(len(indexed_files), 1)
            if ratio >= 0.15:
                score += 10
                notes.append(f"{len(test_files)} test files ({round(ratio*100)}% of codebase) (+10)")
            elif ratio >= 0.05:
                score += 6
                notes.append(f"{len(test_files)} test files ({round(ratio*100)}% of codebase) (+6)")
            else:
                score += 3
                notes.append(f"{len(test_files)} test files (+3)")
        else:
            notes.append("No test files detected")

        # Test framework config files
        test_configs = {
            "pytest.ini":    "pytest",
            "setup.cfg":     "pytest/setuptools",
            "pyproject.toml":"pytest/poetry",
            "jest.config.js":"Jest",
            "jest.config.ts":"Jest",
            "vitest.config.ts": "Vitest",
            ".mocharc.js":   "Mocha",
            "karma.conf.js": "Karma",
        }
        for fname, framework in test_configs.items():
            if (workspace_path / fname).exists():
                score += 5
                notes.append(f"{framework} test config present (+5)")
                break

        # Coverage config
        coverage_files = {"coverage.xml", ".coveragerc", "codecov.yml", ".nycrc"}
        for cf in coverage_files:
            if (workspace_path / cf).exists():
                score += 5
                notes.append(f"Coverage configuration present (+5)")
                break

        return min(20, score), "; ".join(notes) or "No testing signals found"

    @classmethod
    def _score_cicd(cls, workspace_path: Path) -> tuple:
        """Max 15 pts."""
        score = 0
        notes = []

        cicd_signals = {
            ".github/workflows": ("GitHub Actions", 15),
            ".circleci":         ("CircleCI",        12),
            ".gitlab-ci.yml":    ("GitLab CI",       12),
            "Jenkinsfile":       ("Jenkins",         10),
            ".travis.yml":       ("Travis CI",       10),
            "azure-pipelines.yml": ("Azure Pipelines", 10),
            "Makefile":          ("Makefile",         5),
        }
        for path_str, (name, pts) in cicd_signals.items():
            if (workspace_path / path_str).exists():
                score = pts
                notes.append(f"{name} detected (+{pts})")
                break

        if not notes:
            notes.append("No CI/CD configuration found")

        return min(15, score), "; ".join(notes)

    @classmethod
    def _score_configuration(cls, workspace_path: Path) -> tuple:
        """Max 15 pts."""
        score = 0
        notes = []

        # .env.example present (+5)
        for fname in (".env.example", ".env.sample", ".env.template"):
            if (workspace_path / fname).exists():
                score += 5
                notes.append(f"{fname} present — good secret management (+5)")
                break

        # .env NOT committed (+3)
        env_committed = (workspace_path / ".env").exists()
        if not env_committed:
            score += 3
            notes.append(".env NOT committed (+3)")
        else:
            notes.append(".env file committed — secrets may be exposed (-0, flagged in security)")

        # typed config files (pydantic settings, etc.)
        config_signals = {
            "config.py":     "config.py present",
            "settings.py":   "settings.py present",
            "config.yaml":   "config.yaml present",
            "config.json":   "config.json present",
            "app/core/config.py": "Typed config module (pydantic-settings)",
        }
        for fname, note in config_signals.items():
            if (workspace_path / fname).exists():
                score += 4
                notes.append(f"{note} (+4)")
                break

        # Dependency lockfile
        lockfiles = {
            "requirements.txt": "requirements.txt",
            "Pipfile.lock":     "Pipfile.lock",
            "poetry.lock":      "poetry.lock",
            "package-lock.json":"package-lock.json",
        }
        for fname, note in lockfiles.items():
            if (workspace_path / fname).exists():
                score += 3
                notes.append(f"{note} lockfile present (+3)")
                break

        return min(15, score), "; ".join(notes) or "No configuration hygiene signals"

    @classmethod
    def _score_architecture(
        cls,
        workspace_path: Path,
        entities: List[Dict[str, Any]],
        scan_results: Dict[str, Any],
    ) -> tuple:
        """Max 15 pts."""
        score = 0
        notes = []

        # Layered directory structure
        indexed_files = scan_results.get("indexed_files", [])
        paths = [f.get("file_path", "") for f in indexed_files]

        layered_signals = {
            "services":    "Service layer",
            "models":      "Model layer",
            "controllers": "Controller layer",
            "routes":      "Routes layer",
            "api":         "API layer",
            "core":        "Core module",
            "schemas":     "Schema definitions",
            "middleware":  "Middleware layer",
        }
        detected_layers = []
        for keyword, name in layered_signals.items():
            if any(keyword in p.lower() for p in paths):
                detected_layers.append(name)

        if len(detected_layers) >= 4:
            score += 8
            notes.append(f"Well-layered: {', '.join(detected_layers[:4])} (+8)")
        elif len(detected_layers) >= 2:
            score += 4
            notes.append(f"Partial layering: {', '.join(detected_layers)} (+4)")
        else:
            notes.append("No clear architectural layers detected")

        # Separation by entity count
        classes    = sum(1 for e in entities if e.get("type") == "class")
        functions  = sum(1 for e in entities if e.get("type") in ("function", "method"))
        total_code = classes + functions
        if total_code > 20:
            score += 4
            notes.append(f"Substantial codebase: {classes} classes, {functions} functions (+4)")
        elif total_code > 5:
            score += 2
            notes.append(f"{total_code} code entities (+2)")

        # Single entry point
        entrypoint_names = {"main.py", "app.py", "index.js", "server.js", "main.ts"}
        for ep in entrypoint_names:
            if any(p.endswith(ep) for p in paths):
                score += 3
                notes.append(f"Entry point detected: {ep} (+3)")
                break

        return min(15, score), "; ".join(notes) or "No architecture signals detected"

    # ── Report Writers ────────────────────────────────────────────────────────

    @classmethod
    def _write_report(cls, repo_id: str, result: Dict[str, Any]) -> None:
        """Writes ENGINEERING_QUALITY_REPORT.md and quality.json."""
        report_dir = settings.REPORTS_DIR / repo_id
        report_dir.mkdir(parents=True, exist_ok=True)

        overall = result["overall"]
        grade   = cls._letter_grade(overall)

        md_lines = [
            "# Engineering Quality Report",
            "",
            f"**Overall Score:** `{overall}/100`  **Grade:** `{grade}`",
            "",
            "## Dimension Scores",
            "",
            "| Dimension | Score | Max | Details |",
            "| :--- | :---: | :---: | :--- |",
            f"| 📚 Documentation | {result['documentation']} | 20 | {result['details']['documentation']} |",
            f"| 🧪 Testing       | {result['testing']}       | 20 | {result['details']['testing']} |",
            f"| 🔄 CI/CD         | {result['ci_cd']}         | 15 | {result['details']['ci_cd']} |",
            f"| 🔐 Security      | {result['security']}      | 15 | {result['details']['security']} |",
            f"| ⚙️  Configuration | {result['configuration']} | 15 | {result['details']['configuration']} |",
            f"| 🏗️  Architecture  | {result['architecture']}  | 15 | {result['details']['architecture']} |",
            "",
            "## Score Interpretation",
            "",
            "| Range | Grade | Meaning |",
            "| :--- | :--- | :--- |",
            "| 90–100 | A | Exemplary engineering practices |",
            "| 75–89  | B | Good practices, minor gaps |",
            "| 60–74  | C | Adequate but needs improvement |",
            "| 45–59  | D | Significant quality issues |",
            "| 0–44   | F | Requires major quality work |",
        ]

        md_path = report_dir / "ENGINEERING_QUALITY_REPORT.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        json_path = report_dir / "quality.json"
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump({"repo_id": repo_id, **result}, jf, indent=2)

        logger.info(f"[Quality] Report written → {md_path}")

    @staticmethod
    def _letter_grade(score: int) -> str:
        if score >= 90: return "A"
        if score >= 75: return "B"
        if score >= 60: return "C"
        if score >= 45: return "D"
        return "F"

    @classmethod
    def load(cls, repo_id: str) -> Dict[str, Any]:
        """Loads quality.json. Returns {} if not found."""
        path = settings.REPORTS_DIR / repo_id / "quality.json"
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @classmethod
    def format_for_prompt(cls, repo_id: str) -> str:
        """Returns compact XML block for prompt injection."""
        data = cls.load(repo_id)
        if not data:
            return ""
        return (
            "<engineering_quality>\n"
            f"  <overall>{data.get('overall', 0)}/100</overall>\n"
            f"  <documentation>{data.get('documentation', 0)}/20</documentation>\n"
            f"  <testing>{data.get('testing', 0)}/20</testing>\n"
            f"  <ci_cd>{data.get('ci_cd', 0)}/15</ci_cd>\n"
            f"  <security>{data.get('security', 0)}/15</security>\n"
            f"  <configuration>{data.get('configuration', 0)}/15</configuration>\n"
            f"  <architecture>{data.get('architecture', 0)}/15</architecture>\n"
            "</engineering_quality>"
        )
