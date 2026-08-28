# backend/app/services/security_analyzer.py
"""
SecurityAnalyzer — Deep Security Scan Engine
=============================================
Replaces the basic scan in report_generator.py with a comprehensive,
multi-pattern security analysis engine.

Detection categories:
  - Hardcoded secrets (API keys, tokens, passwords, JWT secrets)
  - Dangerous code patterns (eval, exec, pickle, subprocess shell=True)
  - SQL injection vectors (string interpolation in queries)
  - Insecure deserialization (pickle.loads, yaml.load without Loader)
  - Path traversal risks (open() with user input)
  - Exposed .env files or credential files committed to repo

Severity tiers: CRITICAL > HIGH > MEDIUM > LOW
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Detection rule definitions ────────────────────────────────────────────────

# Each rule: (compiled_regex, description, severity, category)
_RULES: List[Tuple[re.Pattern, str, str, str]] = [

    # ── Hardcoded Secrets ────────────────────────────────────────────────────
    (
        re.compile(
            r'(?:api[_-]?key|apikey|secret[_-]?key|access[_-]?key|auth[_-]?token|'
            r'bearer[_-]?token|private[_-]?key)\s*[=:]\s*["\']([A-Za-z0-9_\-\.~]{8,})["\']',
            re.IGNORECASE
        ),
        "Hardcoded API key or secret token",
        "CRITICAL",
        "secret"
    ),
    (
        re.compile(
            r'(?:password|passwd|db_pass|db_password|mysql_pass)\s*[=:]\s*["\']([^"\']{4,})["\']',
            re.IGNORECASE
        ),
        "Hardcoded password",
        "CRITICAL",
        "secret"
    ),
    (
        re.compile(
            r'(?:jwt[_-]?secret|jwt[_-]?key|token[_-]?secret)\s*[=:]\s*["\']([^"\']{6,})["\']',
            re.IGNORECASE
        ),
        "Hardcoded JWT secret",
        "CRITICAL",
        "secret"
    ),
    (
        re.compile(
            r'AKIA[0-9A-Z]{16}',  # AWS Access Key ID
        ),
        "AWS Access Key ID detected",
        "CRITICAL",
        "aws"
    ),
    (
        re.compile(
            r'(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}',  # GitHub tokens
        ),
        "GitHub Personal Access Token detected",
        "CRITICAL",
        "token"
    ),

    # ── Dangerous Code Patterns ──────────────────────────────────────────────
    (
        re.compile(r'\beval\s*\(', re.IGNORECASE),
        "Use of eval() — arbitrary code execution risk",
        "HIGH",
        "code_exec"
    ),
    (
        re.compile(r'\bexec\s*\(', re.IGNORECASE),
        "Use of exec() — arbitrary code execution risk",
        "HIGH",
        "code_exec"
    ),
    (
        re.compile(r'subprocess\.[a-zA-Z_]+\(.*shell\s*=\s*True', re.IGNORECASE),
        "subprocess with shell=True — command injection risk",
        "HIGH",
        "command_injection"
    ),
    (
        re.compile(r'os\.system\s*\(', re.IGNORECASE),
        "os.system() — command injection risk",
        "MEDIUM",
        "command_injection"
    ),

    # ── SQL Injection ────────────────────────────────────────────────────────
    (
        re.compile(
            r'(?:execute|query|cursor\.execute)\s*\(\s*["\'].*?%s.*?["\']|'
            r'(?:execute|query)\s*\(\s*f["\'].*?{.*?}.*?["\']',
            re.IGNORECASE | re.DOTALL
        ),
        "Potential SQL injection — query built with string formatting",
        "HIGH",
        "sql_injection"
    ),
    (
        re.compile(
            r'(?:execute|query)\s*\([^)]*\+\s*[a-zA-Z_]',
            re.IGNORECASE
        ),
        "Potential SQL injection — query built with string concatenation",
        "HIGH",
        "sql_injection"
    ),

    # ── Insecure Deserialization ─────────────────────────────────────────────
    (
        re.compile(r'pickle\.loads?\s*\(', re.IGNORECASE),
        "pickle.load/loads — insecure deserialization risk",
        "HIGH",
        "deserialization"
    ),
    (
        re.compile(r'yaml\.load\s*\([^)]*\)(?!\s*,\s*Loader)', re.IGNORECASE),
        "yaml.load() without Loader — code execution risk",
        "MEDIUM",
        "deserialization"
    ),
    (
        re.compile(r'marshal\.loads?\s*\(', re.IGNORECASE),
        "marshal.load/loads — insecure deserialization",
        "HIGH",
        "deserialization"
    ),

    # ── Path Traversal ───────────────────────────────────────────────────────
    (
        re.compile(
            r'open\s*\(\s*(?:request\.|params\[|args\[|user_input)',
            re.IGNORECASE
        ),
        "open() with user-controlled path — path traversal risk",
        "MEDIUM",
        "path_traversal"
    ),

    # ── Debug / Info Exposure ────────────────────────────────────────────────
    (
        re.compile(r'DEBUG\s*=\s*True', re.IGNORECASE),
        "DEBUG mode enabled — may expose stack traces in production",
        "LOW",
        "config"
    ),
    (
        re.compile(r'ALLOWED_HOSTS\s*=\s*\[?\s*["\'][*]["\']', re.IGNORECASE),
        "ALLOWED_HOSTS = ['*'] — allows requests from any host",
        "MEDIUM",
        "config"
    ),
]

# Files to scan (by extension)
_SCAN_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".cs", ".go",
    ".json", ".yaml", ".yml", ".ini", ".conf", ".env", ".cfg"
}

# Extensions to skip content scan (binary / lock files)
_SKIP_EXTENSIONS = {
    ".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".woff", ".woff2", ".ttf", ".eot", ".ico",
    ".zip", ".tar", ".gz", ".db", ".sqlite"
}

_EXCLUDED_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}


class SecurityFinding:
    """Represents a single security finding."""

    __slots__ = ("file_path", "line", "description", "severity", "category", "snippet")

    def __init__(
        self,
        file_path: str,
        line: int,
        description: str,
        severity: str,
        category: str,
        snippet: str = "",
    ):
        self.file_path   = file_path
        self.line        = line
        self.description = description
        self.severity    = severity
        self.category    = category
        self.snippet     = snippet

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path":   self.file_path,
            "line":        self.line,
            "description": self.description,
            "severity":    self.severity,
            "category":    self.category,
            "snippet":     self.snippet,
        }


class SecurityAnalyzer:
    """
    Deep static security scanner.

    Usage:
        findings = SecurityAnalyzer.scan(workspace_path)
        score    = SecurityAnalyzer.score(findings)
        SecurityAnalyzer.write_report(repo_id, findings, score)
    """

    _SEVERITY_WEIGHTS = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 5, "LOW": 1}

    @classmethod
    def scan(cls, workspace_path: Path) -> List[SecurityFinding]:
        """
        Scans all source files in workspace_path and returns a list of findings.
        """
        findings: List[SecurityFinding] = []

        # Check for committed .env files
        for env_file in workspace_path.rglob(".env"):
            rel = str(env_file.relative_to(workspace_path)).replace("\\", "/")
            findings.append(SecurityFinding(
                file_path   = rel,
                line        = 0,
                description = ".env file committed to repository — credentials exposed",
                severity    = "CRITICAL",
                category    = "exposed_credentials",
                snippet     = ""
            ))

        # Walk and scan source files
        for root, dirs, files in os.walk(workspace_path):
            dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIRS]
            for fname in files:
                fpath = Path(root) / fname
                ext   = fpath.suffix.lower()
                if ext in _SKIP_EXTENSIONS:
                    continue
                if ext not in _SCAN_EXTENSIONS:
                    continue

                rel_path = str(fpath.relative_to(workspace_path)).replace("\\", "/")

                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for lineno, line in enumerate(f, 1):
                            for pattern, desc, severity, category in _RULES:
                                match = pattern.search(line)
                                if match:
                                    # Mask any captured secret group
                                    snippet = line.rstrip()
                                    if match.lastindex and match.lastindex >= 1:
                                        secret_val = match.group(match.lastindex)
                                        masked     = (
                                            secret_val[:3] + "***" + secret_val[-2:]
                                            if len(secret_val) > 5
                                            else "***"
                                        )
                                        snippet = snippet.replace(secret_val, masked)

                                    findings.append(SecurityFinding(
                                        file_path   = rel_path,
                                        line        = lineno,
                                        description = desc,
                                        severity    = severity,
                                        category    = category,
                                        snippet     = snippet.strip()[:120],
                                    ))
                except Exception:
                    pass

        logger.info(
            f"[Security] Scan complete — {len(findings)} findings "
            f"({sum(1 for f in findings if f.severity=='CRITICAL')} CRITICAL)"
        )
        return findings

    @classmethod
    def score(cls, findings: List[SecurityFinding]) -> int:
        """
        Returns a security score (0–100). 100 = no issues found.
        Deducts points per finding weighted by severity.
        """
        total_deduction = 0
        for f in findings:
            total_deduction += cls._SEVERITY_WEIGHTS.get(f.severity, 1)
        return max(0, min(100, 100 - total_deduction))

    @classmethod
    def write_report(
        cls,
        repo_id: str,
        findings: List[SecurityFinding],
        score: int,
    ) -> Path:
        """
        Writes SECURITY_REPORT.md and security.json to data/reports/{repo_id}/.
        Returns the path to the markdown file.
        """
        report_dir = settings.REPORTS_DIR / repo_id
        report_dir.mkdir(parents=True, exist_ok=True)

        # Group by severity
        by_severity: Dict[str, List[SecurityFinding]] = {
            "CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []
        }
        for f in findings:
            by_severity.setdefault(f.severity, []).append(f)

        # ── Markdown report ────────────────────────────────────────────────
        md_lines = [
            "# Security Analysis Report",
            "",
            f"**Security Score:** `{score}/100`  ",
            f"**Total Findings:** `{len(findings)}`  ",
            f"**Critical:** `{len(by_severity['CRITICAL'])}`  |  "
            f"**High:** `{len(by_severity['HIGH'])}`  |  "
            f"**Medium:** `{len(by_severity['MEDIUM'])}`  |  "
            f"**Low:** `{len(by_severity['LOW'])}`",
            "",
        ]

        for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            sev_findings = by_severity.get(severity, [])
            if not sev_findings:
                continue
            icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}[severity]
            md_lines += [
                f"## {icon} {severity} ({len(sev_findings)} findings)",
                "",
                "| File | Line | Description | Snippet |",
                "| :--- | :--- | :--- | :--- |",
            ]
            for f in sev_findings[:30]:  # cap per severity
                snippet = f.snippet.replace("|", "\\|") if f.snippet else "—"
                md_lines.append(
                    f"| `{f.file_path}` | {f.line} | {f.description} | `{snippet}` |"
                )
            md_lines.append("")

        if not findings:
            md_lines += [
                "## ✅ No Security Issues Detected",
                "",
                "No patterns matching known vulnerability signatures were found.",
            ]

        md_content = "\n".join(md_lines)
        md_path = report_dir / "SECURITY_REPORT.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        # ── JSON for programmatic access ───────────────────────────────────
        json_data = {
            "repo_id": repo_id,
            "score":   score,
            "counts":  {s: len(v) for s, v in by_severity.items()},
            "findings": [f.to_dict() for f in findings],
        }
        json_path = report_dir / "security.json"
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(json_data, jf, indent=2)

        logger.info(f"[Security] Report written → {md_path}")
        return md_path

    @classmethod
    def load_summary(cls, repo_id: str) -> Dict[str, Any]:
        """Loads security.json and returns just the summary (score + counts)."""
        path = settings.REPORTS_DIR / repo_id / "security.json"
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "score":  data.get("score", 100),
                "counts": data.get("counts", {}),
            }
        except Exception:
            return {}

    @classmethod
    def format_for_prompt(cls, repo_id: str) -> str:
        """
        Returns a compact XML block of HIGH/CRITICAL findings for prompt injection.
        """
        path = settings.REPORTS_DIR / repo_id / "security.json"
        if not path.exists():
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return ""

        critical_high = [
            f for f in data.get("findings", [])
            if f.get("severity") in ("CRITICAL", "HIGH")
        ]
        if not critical_high:
            return (
                "<security_summary>\n"
                "  <status>No critical or high severity findings</status>\n"
                f"  <score>{data.get('score', 100)}/100</score>\n"
                "</security_summary>"
            )

        lines = [
            "<security_summary>",
            f"  <score>{data.get('score', 100)}/100</score>",
            f"  <critical>{data.get('counts', {}).get('CRITICAL', 0)}</critical>",
            f"  <high>{data.get('counts', {}).get('HIGH', 0)}</high>",
            "  <top_findings>",
        ]
        for f in critical_high[:5]:
            lines.append(
                f"    <finding severity=\"{f['severity']}\" file=\"{f['file_path']}\" "
                f"line=\"{f['line']}\">{f['description']}</finding>"
            )
        lines += ["  </top_findings>", "</security_summary>"]
        return "\n".join(lines)
