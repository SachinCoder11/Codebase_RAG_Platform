# backend/app/services/report_writer.py
"""
ReportWriter — Due Diligence Markdown Report Generator
=======================================================
Generates the 5 required due diligence deliverables:

  1. DUE_DILIGENCE_REPORT.md      — Comprehensive overview
  2. SUBMISSION_READINESS_REPORT.md — Submission score & checklist
  3. ARCHITECTURE_OVERVIEW.md     — Architecture card
  4. DEPENDENCY_INTELLIGENCE_REPORT.md — Dependency analysis
  5. LICENSE_ANALYSIS_REPORT.md   — (delegated to LicenseAnalyzer)

All reports are written to data/reports/{repo_id}/
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import settings

logger = logging.getLogger(__name__)


class ReportWriter:
    """Generates structured Markdown reports from intelligence data."""

    @classmethod
    def generate_all(cls, repo_id: str, dashboard_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Generates all 5 report files and returns their paths.
        """
        paths = {}
        report_dir = settings.REPORTS_DIR / repo_id
        report_dir.mkdir(parents=True, exist_ok=True)

        paths["due_diligence"]   = cls._write_due_diligence(repo_id, dashboard_data)
        paths["submission"]      = cls._write_submission_report(repo_id, dashboard_data)
        paths["architecture"]    = cls._write_architecture_overview(repo_id, dashboard_data)
        paths["dependency"]      = cls._write_dependency_report(repo_id, dashboard_data)

        logger.info(f"[ReportWriter] All 5 reports written for '{repo_id}'")
        return paths

    # ── DUE DILIGENCE REPORT ─────────────────────────────────────────────────

    @classmethod
    def _write_due_diligence(cls, repo_id: str, data: Dict[str, Any]) -> str:
        overview    = data.get("overview", {})
        quality     = data.get("quality", {})
        security    = data.get("security", {})
        git         = data.get("git_activity", {})
        submission  = data.get("submission", {})
        arch        = data.get("architecture", {})

        repo_name = overview.get("repo_name", repo_id)
        owner     = overview.get("owner", "Unknown")

        sec_counts = security.get("counts", {})
        checklist  = submission.get("checklist", {})
        score      = submission.get("submission_score", 0)
        rec        = submission.get("approval_recommendation", "UNKNOWN")
        rec_icon   = {"APPROVE": "✅", "REVIEW": "⚠️", "REJECT": "🔴"}.get(rec, "❓")

        compliance_rows = "\n".join(
            f"| {v.get('label','—')} | {'✅ PASS' if v.get('pass') else '❌ FAIL'} | {v.get('detail','—')} |"
            for v in checklist.values()
        )

        top_findings = security.get("findings", [])[:10]
        findings_rows = "\n".join(
            f"| `{f.get('file_path','—')}` | {f.get('line','—')} | {f.get('severity','—')} | {f.get('description','—')} |"
            for f in top_findings
        ) or "| — | — | — | No findings |"

        md = f"""# Repository Due Diligence Report

**Repository:** {repo_name}  
**Owner:** {owner}  
**Source:** {overview.get("source_url", "N/A")}  
**Report Generated:** {_now()}  

---

## Executive Summary

| Metric | Value |
| :--- | :--- |
| **Submission Score** | `{score}/100` |
| **Recommendation** | {rec_icon} {rec} |
| **Confidence** | `{round(submission.get("confidence_score", 0) * 100)}%` |
| **Overall Quality** | `{quality.get("overall", 0)}/100` |
| **Security Score** | `{security.get("score", 100)}/100` |
| **Total Files** | {overview.get("total_files", 0):,} |
| **Lines of Code** | {overview.get("total_lines", 0):,} |
| **Contributors** | {git.get("contributor_count", "N/A")} |

---

## Repository Overview

| Property | Value |
| :--- | :--- |
| **Name** | {repo_name} |
| **Owner** | {owner} |
| **Source URL** | {overview.get("source_url", "Local upload")} |
| **Primary Language** | {", ".join(overview.get("languages", {}).keys())[:100] or "N/A"} |
| **Frameworks** | {", ".join(overview.get("frameworks", [])) or "None detected"} |
| **Total Files** | {overview.get("total_files", 0):,} |
| **Total LOC** | {overview.get("total_lines", 0):,} |

---

## Engineering Quality

| Dimension | Score | Max |
| :--- | :---: | :---: |
| 📚 Documentation | {quality.get("documentation", 0)} | 20 |
| 🧪 Testing | {quality.get("testing", 0)} | 20 |
| 🔄 CI/CD | {quality.get("ci_cd", 0)} | 15 |
| 🔐 Security | {quality.get("security", 0)} | 15 |
| ⚙️ Configuration | {quality.get("configuration", 0)} | 15 |
| 🏗️ Architecture | {quality.get("architecture", 0)} | 15 |
| **Overall** | **{quality.get("overall", 0)}** | **100** |

---

## Security Analysis

| Severity | Count |
| :--- | :--- |
| 🔴 Critical | {sec_counts.get("CRITICAL", 0)} |
| 🟠 High | {sec_counts.get("HIGH", 0)} |
| 🟡 Medium | {sec_counts.get("MEDIUM", 0)} |
| 🟢 Low | {sec_counts.get("LOW", 0)} |

### Top Findings

| File | Line | Severity | Description |
| :--- | :--- | :--- | :--- |
{findings_rows}

---

## Modern Codebase Compliance

| Check | Status | Detail |
| :--- | :--- | :--- |
{compliance_rows}

---

## Architecture

| Property | Value |
| :--- | :--- |
| **Application Type** | {arch.get("application_type", "Unknown")} |
| **Frameworks** | {", ".join(arch.get("frameworks", [])) or "N/A"} |
| **Database** | {", ".join(arch.get("database_layer", [])) or "N/A"} |
| **Authentication** | {", ".join(arch.get("auth_mechanism", [])) or "N/A"} |
| **Deployment** | {", ".join(arch.get("deployment", [])) or "N/A"} |
| **CI/CD** | {", ".join(arch.get("ci_cd", [])) or "None"} |

---

## Git Activity

| Metric | Value |
| :--- | :--- |
| ⭐ Stars | {git.get("stars", "N/A")} |
| 🍴 Forks | {git.get("forks", "N/A")} |
| 👥 Contributors | {git.get("contributor_count", "N/A")} |
| 🐛 Open Issues | {git.get("open_issues", "N/A")} |
| 🔀 Open PRs | {git.get("open_pr_count", "N/A")} |
| 📅 Last Commit | {git.get("pushed_at", "N/A")[:10] if git.get("pushed_at") else "N/A"} |

---

*Generated by Antigravity RAG Platform — Due Diligence Engine*
"""
        path = settings.REPORTS_DIR / repo_id / "DUE_DILIGENCE_REPORT.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        return str(path)

    # ── SUBMISSION READINESS REPORT ──────────────────────────────────────────

    @classmethod
    def _write_submission_report(cls, repo_id: str, data: Dict[str, Any]) -> str:
        submission = data.get("submission", {})
        overview   = data.get("overview", {})
        score      = submission.get("submission_score", 0)
        rec        = submission.get("approval_recommendation", "UNKNOWN")
        conf       = round(submission.get("confidence_score", 0) * 100)
        checklist  = submission.get("checklist", {})

        rec_icon = {"APPROVE": "✅", "REVIEW": "⚠️", "REJECT": "🔴"}.get(rec, "❓")
        passed = submission.get("passed_checks", 0)
        total  = submission.get("total_checks", 8)

        score_bar_filled = round(score / 5)
        score_bar = "█" * score_bar_filled + "░" * (20 - score_bar_filled)

        checklist_rows = "\n".join(
            f"| {v.get('label','—')} | {'+' + str(v.get('weight','?'))+'pts' if v.get('pass') else '—'} | {'✅ PASS' if v.get('pass') else '❌ FAIL'} | {v.get('detail','—')} |"
            for v in checklist.values()
        )

        md = f"""# Submission Readiness Report

**Repository:** {overview.get("repo_name", repo_id)}  
**Generated:** {_now()}  

---

## Submission Score

```
Score: {score}/100
[{score_bar}]
```

| Metric | Value |
| :--- | :--- |
| **Score** | `{score}/100` |
| **Recommendation** | {rec_icon} **{rec}** |
| **Confidence** | `{conf}%` |
| **Checks Passed** | `{passed}/{total}` |

### Recommendation Guide

| Score | Recommendation | Meaning |
| :--- | :--- | :--- |
| 80–100 | ✅ APPROVE | Repository meets modern engineering standards |
| 55–79  | ⚠️ REVIEW  | Meets minimum bar but has gaps to address |
| 0–54   | 🔴 REJECT  | Does not meet submission criteria |

---

## Modern Codebase Compliance Checklist

| Check | Points | Status | Detail |
| :--- | :---: | :--- | :--- |
{checklist_rows}

---

## Recommendations

"""
        failed_items = [v for v in checklist.values() if not v.get("pass")]
        if failed_items:
            for item in failed_items:
                md += f"- **{item['label']}**: {item['detail']}\n"
        else:
            md += "All compliance checks passed. Repository is in excellent shape.\n"

        md += "\n---\n\n*Generated by Antigravity RAG Platform — Submission Readiness Engine*\n"

        path = settings.REPORTS_DIR / repo_id / "SUBMISSION_READINESS_REPORT.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        return str(path)

    # ── ARCHITECTURE OVERVIEW ─────────────────────────────────────────────────

    @classmethod
    def _write_architecture_overview(cls, repo_id: str, data: Dict[str, Any]) -> str:
        arch     = data.get("architecture", {})
        overview = data.get("overview", {})

        app_type    = arch.get("application_type", "Unknown")
        frameworks  = ", ".join(arch.get("frameworks", [])) or "None detected"
        db_layer    = ", ".join(arch.get("database_layer", [])) or "None detected"
        auth        = ", ".join(arch.get("auth_mechanism", [])) or "None detected"
        deployment  = ", ".join(arch.get("deployment", [])) or "None detected"
        ci_cd       = ", ".join(arch.get("ci_cd", [])) or "None detected"
        entrypoints = "\n".join(f"  - `{e}`" for e in arch.get("entry_points", [])[:10]) or "  - None detected"
        routes      = "\n".join(f"  - `{r}`" for r in arch.get("routes", [])[:15]) or "  - None detected"
        services    = "\n".join(f"  - `{s}`" for s in arch.get("services", [])[:15]) or "  - None detected"
        models      = "\n".join(f"  - `{m}`" for m in arch.get("models", [])[:15]) or "  - None detected"

        md = f"""# Architecture Overview

**Repository:** {overview.get("repo_name", repo_id)}  
**Generated:** {_now()}  

---

## Architecture Card

| Property | Value |
| :--- | :--- |
| **Application Type** | {app_type} |
| **Frameworks** | {frameworks} |
| **Database / ORM** | {db_layer} |
| **Cache** | {", ".join(v for v in arch.get("database_layer", []) if "Redis" in v) or "None detected"} |
| **Authentication** | {auth} |
| **Deployment** | {deployment} |
| **CI/CD** | {ci_cd} |
| **Routes Detected** | {arch.get("route_count", 0)} |
| **Services Detected** | {arch.get("service_count", 0)} |
| **Models Detected** | {arch.get("model_count", 0)} |

---

## System Architecture Diagram

```mermaid
flowchart LR
    A[Repository Source] --> B[Identity Service]
    B --> C[Repository Scanner]
    C --> D[Code Chunker]
    D --> E[Embedding Engine]
    E --> F[(Chroma Vector DB)]
    F --> G[Intelligence Engine]
    G --> H[Due Diligence Dashboard]
    G --> I[AI Chat Interface]
    
    subgraph Intelligence Engine
        G1[Architecture Analyzer]
        G2[Security Analyzer]
        G3[Engineering Quality]
        G4[Git Activity]
        G5[Submission Engine]
        G6[Dependency Analyzer]
        G7[License Analyzer]
    end
    
    G --> G1
    G --> G2
    G --> G3
    G --> G4
    G --> G5
    G --> G6
    G --> G7
```

---

## Entry Points
{entrypoints}

## Routes ({arch.get("route_count", 0)} detected)
{routes}

## Services ({arch.get("service_count", 0)} detected)
{services}

## Models ({arch.get("model_count", 0)} detected)
{models}

---

*Generated by Antigravity RAG Platform — Architecture Intelligence Engine*
"""
        path = settings.REPORTS_DIR / repo_id / "ARCHITECTURE_OVERVIEW.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        return str(path)

    # ── DEPENDENCY INTELLIGENCE REPORT ───────────────────────────────────────

    @classmethod
    def _write_dependency_report(cls, repo_id: str, data: Dict[str, Any]) -> str:
        deps     = data.get("dependencies", {})
        overview = data.get("overview", {})

        total    = deps.get("total_count", 0)
        direct   = deps.get("direct_count", 0)
        dev_cnt  = deps.get("dev_count", 0)
        risk     = deps.get("risk_score", 100)
        outdated = deps.get("outdated_count", 0)
        flagged  = deps.get("flagged_packages", [])
        dep_list = deps.get("dependencies", [])
        mtype    = deps.get("manifest_type", "none")
        files    = ", ".join(deps.get("manifest_files", [])) or "None"

        risk_icon = "✅" if risk >= 80 else ("⚠️" if risk >= 60 else "🔴")

        flagged_rows = "\n".join(
            f"| `{f['name']}` | {f.get('severity','—')} | {f.get('reason','—')} |"
            for f in flagged[:20]
        ) or "| — | — | No flagged packages |"

        # Separate direct vs dev for display
        direct_deps = [d for d in dep_list if d.get("type") == "direct"][:30]
        dev_deps    = [d for d in dep_list if d.get("type") == "dev"][:20]

        direct_rows = "\n".join(
            f"| `{d['name']}` | `{d.get('version','*')}` | {'⚠️ ' + d['flag_reason'][:50] if d.get('flagged') else '✅ OK'} |"
            for d in direct_deps
        ) or "| — | — | No direct dependencies |"

        dev_rows = "\n".join(
            f"| `{d['name']}` | `{d.get('version','*')}` | {'⚠️ ' + d['flag_reason'][:50] if d.get('flagged') else '✅ OK'} |"
            for d in dev_deps
        ) or "| — | — | No dev dependencies |"

        md = f"""# Dependency Intelligence Report

**Repository:** {overview.get("repo_name", repo_id)}  
**Generated:** {_now()}  

---

## Summary

| Metric | Value |
| :--- | :--- |
| **Manifest Type** | `{mtype}` |
| **Manifest Files** | `{files}` |
| **Total Dependencies** | {total} |
| **Direct** | {direct} |
| **Dev / Build** | {dev_cnt} |
| **Risk Score** | {risk_icon} `{risk}/100` |
| **Flagged Packages** | {outdated} |

---

## Flagged / Risky Packages

| Package | Severity | Reason |
| :--- | :--- | :--- |
{flagged_rows}

---

## Direct Dependencies ({direct} total)

| Package | Version | Status |
| :--- | :--- | :--- |
{direct_rows}

---

## Dev Dependencies ({dev_cnt} total)

| Package | Version | Status |
| :--- | :--- | :--- |
{dev_rows}

---

*Generated by Antigravity RAG Platform — Dependency Intelligence Engine*
"""
        path = settings.REPORTS_DIR / repo_id / "DEPENDENCY_INTELLIGENCE_REPORT.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        return str(path)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
