# backend/app/services/submission_engine.py
"""
SubmissionEngine — Repository Due Diligence Scoring
=====================================================
Produces a Submission Readiness Score (0-100), an Approval Recommendation,
and a Confidence Score based on the Modern Codebase Compliance Checklist.

Compliance Checklist (8 dimensions, weighted):
  Modern Frameworks          +15  (known modern fw detected)
  CI/CD Pipeline             +15  (CI/CD config present)
  Documentation              +15  (README + docstrings)
  Security                   +15  (security score >= 60)
  Testing                    +15  (test files present, ratio >= 5%)
  Active Development         +10  (pushed within 12 months or local)
  Cloud Native / Docker      +10  (Dockerfile or docker-compose present)
  Issue Tracking / Activity  + 5  (GitHub open issues or PRs tracked)

Approval Thresholds:
  Score >= 80  → APPROVE
  Score >= 55  → REVIEW
  Score < 55   → REJECT
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

# Modern framework list (signals active, opinionated, community-backed choices)
_MODERN_FRAMEWORKS = {
    "FastAPI", "NestJS", "Next.js", "Nuxt", "SvelteKit", "Remix",
    "Spring Boot", "Django", "Flask", "Express", "React", "Vue",
    "Angular", "ASP.NET", "Gin", "Fiber", "Actix",
}

_CHECKLIST_ITEMS = [
    "modern_frameworks",
    "ci_cd",
    "documentation",
    "security",
    "testing",
    "active_development",
    "cloud_native",
    "issue_tracking",
]

_CHECKLIST_WEIGHTS = {
    "modern_frameworks":  15,
    "ci_cd":             15,
    "documentation":     15,
    "security":          15,
    "testing":           15,
    "active_development":10,
    "cloud_native":      10,
    "issue_tracking":     5,
}

_CHECKLIST_LABELS = {
    "modern_frameworks":  "Modern Frameworks",
    "ci_cd":             "CI/CD Pipeline",
    "documentation":     "Documentation",
    "security":          "Security Posture",
    "testing":           "Test Coverage",
    "active_development":"Active Development",
    "cloud_native":      "Cloud Native / Docker",
    "issue_tracking":    "Issue Tracking",
}


class SubmissionEngine:
    """
    Computes submission readiness from all pre-computed intelligence artifacts.
    """

    @classmethod
    def evaluate(cls, repo_id: str) -> Dict[str, Any]:
        """
        Loads all available intelligence for repo_id and computes submission score.

        Returns:
            {
              "submission_score":      int (0-100),
              "approval_recommendation": "APPROVE" | "REVIEW" | "REJECT",
              "confidence_score":      float (0.0-1.0),
              "checklist":             { item: { pass: bool, weight: int, label: str } },
              "checklist_summary":     str,
            }
        """
        manifest  = cls._load_json(repo_id, "manifest.json")
        quality   = cls._load_json(repo_id, "quality.json")
        security  = cls._load_json(repo_id, "security.json")
        activity  = cls._load_json(repo_id, "git_activity.json")
        summary   = cls._load_json(repo_id, "summary.json")

        # ── Evaluate each checklist item ──────────────────────────────────
        checklist: Dict[str, Dict[str, Any]] = {}
        total_score = 0
        data_points = 0  # for confidence calculation

        # 1. Modern Frameworks
        frameworks = (
            manifest.get("frameworks", [])
            or summary.get("frameworks", [])
        )
        fw_pass = bool(frameworks) and any(
            f in _MODERN_FRAMEWORKS for f in frameworks
        )
        checklist["modern_frameworks"] = {
            "pass":   fw_pass,
            "weight": _CHECKLIST_WEIGHTS["modern_frameworks"],
            "label":  _CHECKLIST_LABELS["modern_frameworks"],
            "detail": f"Detected: {', '.join(frameworks[:5])}" if frameworks else "No modern framework detected",
        }
        if fw_pass:
            total_score += _CHECKLIST_WEIGHTS["modern_frameworks"]
        if manifest or summary:
            data_points += 1

        # 2. CI/CD
        ci_cd_pass = bool(
            manifest.get("github_actions_present")
            or (quality.get("ci_cd", 0) > 0)
        )
        ci_cd_detail = quality.get("details", {}).get("ci_cd", "No CI/CD detected")
        checklist["ci_cd"] = {
            "pass":   ci_cd_pass,
            "weight": _CHECKLIST_WEIGHTS["ci_cd"],
            "label":  _CHECKLIST_LABELS["ci_cd"],
            "detail": ci_cd_detail,
        }
        if ci_cd_pass:
            total_score += _CHECKLIST_WEIGHTS["ci_cd"]
        if quality:
            data_points += 1

        # 3. Documentation
        doc_score = quality.get("documentation", 0)
        doc_pass = doc_score >= 8  # at least 8/20
        checklist["documentation"] = {
            "pass":   doc_pass,
            "weight": _CHECKLIST_WEIGHTS["documentation"],
            "label":  _CHECKLIST_LABELS["documentation"],
            "detail": quality.get("details", {}).get("documentation", f"Score: {doc_score}/20"),
        }
        if doc_pass:
            total_score += _CHECKLIST_WEIGHTS["documentation"]

        # 4. Security
        sec_score = security.get("score", 100)
        sec_pass = sec_score >= 60
        sec_counts = security.get("counts", {})
        checklist["security"] = {
            "pass":   sec_pass,
            "weight": _CHECKLIST_WEIGHTS["security"],
            "label":  _CHECKLIST_LABELS["security"],
            "detail": (
                f"Score: {sec_score}/100 — "
                f"Critical: {sec_counts.get('CRITICAL', 0)}, "
                f"High: {sec_counts.get('HIGH', 0)}, "
                f"Medium: {sec_counts.get('MEDIUM', 0)}"
            ),
        }
        if sec_pass:
            total_score += _CHECKLIST_WEIGHTS["security"]
        if security:
            data_points += 1

        # 5. Testing
        test_score = quality.get("testing", 0)
        test_pass = test_score >= 5  # at least 5/20
        checklist["testing"] = {
            "pass":   test_pass,
            "weight": _CHECKLIST_WEIGHTS["testing"],
            "label":  _CHECKLIST_LABELS["testing"],
            "detail": quality.get("details", {}).get("testing", f"Score: {test_score}/20"),
        }
        if test_pass:
            total_score += _CHECKLIST_WEIGHTS["testing"]

        # 6. Active Development (pushed within 12 months or local upload)
        pushed_at = activity.get("pushed_at", "")
        is_local = not bool(activity) or activity.get("repo_id") == "local"
        active_pass = is_local  # local uploads assumed active
        if pushed_at:
            try:
                pushed_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_since_push = (now - pushed_dt).days
                active_pass = days_since_push <= 365
                act_detail = f"Last push: {pushed_at[:10]} ({days_since_push} days ago)"
            except Exception:
                active_pass = True
                act_detail = "Push date available"
        else:
            act_detail = "Local upload — assumed active"
        checklist["active_development"] = {
            "pass":   active_pass,
            "weight": _CHECKLIST_WEIGHTS["active_development"],
            "label":  _CHECKLIST_LABELS["active_development"],
            "detail": act_detail,
        }
        if active_pass:
            total_score += _CHECKLIST_WEIGHTS["active_development"]
        if activity:
            data_points += 1

        # 7. Cloud Native / Docker
        docker_pass = bool(manifest.get("docker_present"))
        checklist["cloud_native"] = {
            "pass":   docker_pass,
            "weight": _CHECKLIST_WEIGHTS["cloud_native"],
            "label":  _CHECKLIST_LABELS["cloud_native"],
            "detail": "Dockerfile or docker-compose detected" if docker_pass else "No containerization config found",
        }
        if docker_pass:
            total_score += _CHECKLIST_WEIGHTS["cloud_native"]

        # 8. Issue Tracking (GitHub activity present and issues tracked)
        open_issues = activity.get("open_issues", 0)
        stars = activity.get("stars", 0)
        issue_pass = bool(activity and not activity.get("error") and (open_issues > 0 or stars > 0))
        checklist["issue_tracking"] = {
            "pass":   issue_pass,
            "weight": _CHECKLIST_WEIGHTS["issue_tracking"],
            "label":  _CHECKLIST_LABELS["issue_tracking"],
            "detail": (
                f"GitHub: ⭐{stars} stars, {open_issues} open issues"
                if issue_pass else "No GitHub activity data (local or private repo)"
            ),
        }
        if issue_pass:
            total_score += _CHECKLIST_WEIGHTS["issue_tracking"]

        # ── Confidence Score ──────────────────────────────────────────────
        # Based on how many data sources we successfully loaded
        max_data_sources = 4  # manifest, quality, security, activity
        confidence = round(min(1.0, 0.4 + (data_points / max_data_sources) * 0.6), 2)

        # ── Approval Recommendation ───────────────────────────────────────
        if total_score >= 80:
            recommendation = "APPROVE"
        elif total_score >= 55:
            recommendation = "REVIEW"
        else:
            recommendation = "REJECT"

        # ── Checklist summary string ──────────────────────────────────────
        passed = sum(1 for v in checklist.values() if v["pass"])
        total_items = len(checklist)
        checklist_summary = f"{passed}/{total_items} compliance checks passed"

        result = {
            "submission_score":        total_score,
            "approval_recommendation": recommendation,
            "confidence_score":        confidence,
            "checklist":               checklist,
            "checklist_summary":       checklist_summary,
            "passed_checks":           passed,
            "total_checks":            total_items,
        }

        # Cache to disk
        cls._save(repo_id, result)
        logger.info(
            f"[Submission] '{repo_id}' score={total_score}/100 "
            f"recommendation={recommendation} confidence={confidence}"
        )
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    @classmethod
    def _load_json(cls, repo_id: str, filename: str) -> Dict[str, Any]:
        path = settings.REPORTS_DIR / repo_id / filename
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @classmethod
    def _save(cls, repo_id: str, result: Dict[str, Any]) -> None:
        report_dir = settings.REPORTS_DIR / repo_id
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / "submission.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        except Exception as e:
            logger.warning(f"[Submission] Failed to save submission.json: {e}")

    @classmethod
    def load(cls, repo_id: str) -> Dict[str, Any]:
        """Loads cached submission.json or recomputes."""
        path = settings.REPORTS_DIR / repo_id / "submission.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return cls.evaluate(repo_id)
