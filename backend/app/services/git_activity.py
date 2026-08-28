# backend/app/services/git_activity.py
"""
GitActivityService — GitHub Repository Intelligence Layer
=========================================================
Fetches public metadata from the GitHub REST API for repositories
sourced from GitHub. Gracefully handles private repos and API failures.

Uses GITHUB_TOKEN from .env for authenticated requests (5,000 req/hr).
Falls back to unauthenticated (60 req/hr) if token is not set.

Collects:
  - Stars, forks, watchers, open issues
  - Contributor count, commit count
  - Release count, PR count
  - Last push date
  - License type
  - Primary language (GitHub's detection)

Writes:
  - REPOSITORY_ACTIVITY_REPORT.md
  - git_activity.json
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class GitActivityService:
    """Fetches GitHub activity data for public repositories."""

    _BASE_URL = "https://api.github.com"
    _TIMEOUT  = 10  # seconds per request

    @classmethod
    def _get_headers(cls) -> Dict[str, str]:
        """Build request headers, using GITHUB_TOKEN if configured."""
        headers = {
            "Accept":     "application/vnd.github.v3+json",
            "User-Agent": "RAG-Platform/1.0",
        }
        token = getattr(settings, "GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = f"token {token}"
        return headers

    @classmethod
    def _get(cls, url: str) -> Optional[Dict[str, Any]]:
        """Execute a GET request, returning parsed JSON or None on failure."""
        try:
            import urllib.request
            import urllib.error

            req = urllib.request.Request(url, headers=cls._get_headers())
            with urllib.request.urlopen(req, timeout=cls._TIMEOUT) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug(f"[GitActivity] GET {url} failed: {e}")
        return None

    @classmethod
    def fetch(cls, owner: str, repo_name: str) -> Dict[str, Any]:
        """
        Fetches all available GitHub metadata for a public repository.

        Args:
            owner     : GitHub username or organization
            repo_name : Repository name (no .git suffix)

        Returns:
            Dict with collected metrics. Empty dict if repo is private or
            API is unavailable.
        """
        if not owner or not repo_name or owner == "local":
            return {}

        logger.info(f"[GitActivity] Fetching metadata for {owner}/{repo_name}")

        base = f"{cls._BASE_URL}/repos/{owner}/{repo_name}"
        repo_data = cls._get(base)

        if not repo_data:
            logger.warning(f"[GitActivity] Could not fetch {owner}/{repo_name} — private or unavailable")
            return {"error": "Repository not accessible via GitHub API"}

        # ── Core repo stats ────────────────────────────────────────────────
        result: Dict[str, Any] = {
            "owner":          owner,
            "repo_name":      repo_name,
            "full_name":      repo_data.get("full_name", f"{owner}/{repo_name}"),
            "description":    repo_data.get("description", ""),
            "stars":          repo_data.get("stargazers_count", 0),
            "forks":          repo_data.get("forks_count", 0),
            "watchers":       repo_data.get("watchers_count", 0),
            "open_issues":    repo_data.get("open_issues_count", 0),
            "default_branch": repo_data.get("default_branch", "main"),
            "created_at":     repo_data.get("created_at", ""),
            "updated_at":     repo_data.get("updated_at", ""),
            "pushed_at":      repo_data.get("pushed_at", ""),
            "size_kb":        repo_data.get("size", 0),
            "language":       repo_data.get("language", ""),
            "license":        (repo_data.get("license") or {}).get("name", "None"),
            "topics":         repo_data.get("topics", []),
            "archived":       repo_data.get("archived", False),
            "fork":           repo_data.get("fork", False),
        }

        # ── Contributors (paginated, cap at 1 page = 30) ──────────────────
        contrib_data = cls._get(f"{base}/contributors?per_page=30&anon=0")
        result["contributor_count"] = len(contrib_data) if contrib_data else 0

        # ── Release count ─────────────────────────────────────────────────
        releases = cls._get(f"{base}/releases?per_page=100")
        result["release_count"] = len(releases) if releases else 0

        # ── Commit count (approximation: use stats/contributors) ──────────
        stats = cls._get(f"{base}/stats/contributors")
        if stats:
            total_commits = sum(c.get("total", 0) for c in stats if isinstance(c, dict))
            result["commit_count"] = total_commits
        else:
            result["commit_count"] = 0

        # ── Open Pull Requests ────────────────────────────────────────────
        prs = cls._get(f"{base}/pulls?state=open&per_page=1")
        # GitHub doesn't return total count in pulls endpoint easily,
        # so we use the search API
        search_prs = cls._get(
            f"{cls._BASE_URL}/search/issues?q=repo:{owner}/{repo_name}+type:pr+state:open&per_page=1"
        )
        result["open_pr_count"] = (
            search_prs.get("total_count", 0) if search_prs else 0
        )

        logger.info(
            f"[GitActivity] {owner}/{repo_name}: "
            f"⭐{result['stars']} 🍴{result['forks']} "
            f"👥{result['contributor_count']} commits={result['commit_count']}"
        )
        return result

    @classmethod
    def write_report(cls, repo_id: str, activity: Dict[str, Any]) -> Path:
        """
        Writes REPOSITORY_ACTIVITY_REPORT.md and git_activity.json.
        """
        report_dir = settings.REPORTS_DIR / repo_id
        report_dir.mkdir(parents=True, exist_ok=True)

        if not activity or "error" in activity:
            md_content = (
                "# Repository Activity Report\n\n"
                "> GitHub activity data is not available for this repository.\n"
                "> This may be a private repository or a local upload.\n"
            )
        else:
            pushed = activity.get("pushed_at", "")[:10] if activity.get("pushed_at") else "Unknown"
            topics = ", ".join(f"`{t}`" for t in activity.get("topics", [])) or "—"
            md_content = f"""# Repository Activity Report

## {activity.get('full_name', 'Repository')}

> {activity.get('description', 'No description available.')}

## GitHub Metrics

| Metric | Value |
| :--- | :--- |
| ⭐ Stars | {activity.get('stars', 0):,} |
| 🍴 Forks | {activity.get('forks', 0):,} |
| 👥 Contributors | {activity.get('contributor_count', 0)} |
| 📝 Total Commits | {activity.get('commit_count', 0):,} |
| 🐛 Open Issues | {activity.get('open_issues', 0):,} |
| 🔀 Open PRs | {activity.get('open_pr_count', 0):,} |
| 📦 Releases | {activity.get('release_count', 0)} |
| 📅 Last Push | {pushed} |
| 📏 Repo Size | {activity.get('size_kb', 0):,} KB |

## Meta

| Field | Value |
| :--- | :--- |
| Primary Language | {activity.get('language', 'Unknown')} |
| License | {activity.get('license', 'None')} |
| Default Branch | `{activity.get('default_branch', 'main')}` |
| Archived | {'Yes' if activity.get('archived') else 'No'} |
| Topics | {topics} |
"""

        md_path = report_dir / "REPOSITORY_ACTIVITY_REPORT.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        json_path = report_dir / "git_activity.json"
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump({"repo_id": repo_id, **activity}, jf, indent=2)

        logger.info(f"[GitActivity] Report written → {md_path}")
        return md_path

    @classmethod
    def load(cls, repo_id: str) -> Dict[str, Any]:
        """Loads git_activity.json. Returns {} if not found."""
        path = settings.REPORTS_DIR / repo_id / "git_activity.json"
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
