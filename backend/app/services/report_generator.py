import os
import json
import re
from pathlib import Path
from typing import Dict, List, Any
from app.core.config import settings
from app.services.llm_orchestrator import LLMOrchestrator
from app.services.parser.dependency_extractor import DependencyExtractor

class ReportGenerator:
    @staticmethod
    def scan_for_secrets(workspace_path: Path) -> List[Dict[str, Any]]:
        """
        Scans code files for potential hardcoded API keys, tokens, or credentials patterns.
        """
        secret_patterns = [
            (re.compile(r"(api_key|apikey|secret|password|passwd|private_key|token)\s*=\s*['\"]([a-zA-Z0-9_\-\.\~]{8,})['\"]", re.IGNORECASE), "Possible hardcoded credential/secret"),
            (re.compile(r"aws_[a-z_]*key[a-z_]*\s*=\s*['\"]([a-zA-Z0-9/+=]{16,})['\"]", re.IGNORECASE), "Potential AWS access/secret key")
        ]
        
        findings = []
        # Walk directories (skip exclusions)
        exclude_dirs = {".git", "node_modules", "venv", ".venv", "dist", "build"}
        
        for root, dirs, files in os.walk(workspace_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() not in [".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml", ".ini", ".conf"]:
                    continue
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for idx, line in enumerate(f):
                            for pattern, desc in secret_patterns:
                                match = pattern.search(line)
                                if match:
                                    # Mask the secret for safety in report
                                    secret = match.group(2)
                                    masked = secret[:3] + "..." + secret[-3:] if len(secret) > 6 else "******"
                                    findings.append({
                                        "file_path": str(file_path.relative_to(workspace_path)).replace("\\", "/"),
                                        "line": idx + 1,
                                        "issue": desc,
                                        "match": f"{match.group(1)} = '{masked}'",
                                        "severity": "CRITICAL"
                                    })
                except Exception:
                    pass
        return findings

    @classmethod
    def generate_full_report(
        cls,
        repo_id: str,
        scan_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Aggregates static scans, dependency alerts, and queries the LLM for architectural critique.
        """
        workspace_path = settings.WORKSPACES_DIR / repo_id
        
        # 1. Scan for secrets
        secrets_findings = cls.scan_for_secrets(workspace_path)
        
        # 2. Extract dependencies
        dependencies = DependencyExtractor.extract_all(workspace_path)
        
        # 3. Analyze code complexity metrics (mocked metrics based on control structures found)
        complexity_count = 0
        exclude_dirs = {".git", "node_modules", "venv", ".venv"}
        total_files_scanned = 0
        
        for root, dirs, files in os.walk(workspace_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() in [".py", ".js", ".ts", ".java", ".cs"]:
                    total_files_scanned += 1
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            # Count control structures (if, for, while, catch, try)
                            complexity_count += len(re.findall(r"\b(if|for|while|catch|switch|except)\b", content))
                    except Exception:
                        pass

        # Maintainability scoring logic
        maintainability_score = 90
        if total_files_scanned > 0:
            avg_complexity = complexity_count / total_files_scanned
            maintainability_score = max(40, min(100, int(100 - (avg_complexity * 3))))
        
        # 4. Invoke LLM for structural & security analysis
        file_tree = "\n".join(f["file_path"] for f in scan_results.get("indexed_files", [])[:80])
        lang_dist = json.dumps(scan_results.get("languages", {}))
        
        # Architectural analysis
        arch_analysis = LLMOrchestrator.generate_architecture_analysis(
            directory_structure=file_tree,
            languages=lang_dist
        )

        # Security vulnerabilities evaluation
        sec_analysis = LLMOrchestrator.generate_security_analysis(
            dependencies=",".join(dependencies),
            files_preview=file_tree
        )

        # Assemble report object
        report_data = {
            "repository_id": repo_id,
            "architecture_score": maintainability_score, # Mapping score
            "security_score": max(20, 100 - (len(secrets_findings) * 15)),
            "maintainability_score": maintainability_score,
            "complexity_score": complexity_count,
            "metrics": {
                "total_files": scan_results.get("file_count", 0),
                "total_lines": scan_results.get("total_lines", 0),
                "avg_complexity_index": round(complexity_count / total_files_scanned, 1) if total_files_scanned > 0 else 0
            },
            "secrets_leakages": secrets_findings,
            "dependencies_count": len(dependencies),
            "dependencies_list": dependencies,
            "architecture_analysis": arch_analysis,
            "security_analysis": sec_analysis,
            "suggestions": [
                "Implement strict environment configurations to avoid hardcoding variables in files.",
                "Ensure package lockfiles (package-lock.json / requirements.txt) are checked for vulnerable package trees.",
                "Set up pre-commit hook scanning rules for secrets containment."
            ]
        }

        # 5. Export to markdown structure
        md_content = cls.compile_markdown_report(report_data)
        
        # Write files
        report_dir = settings.REPORTS_DIR / repo_id
        report_dir.mkdir(parents=True, exist_ok=True)
        
        with open(report_dir / "report.json", "w", encoding="utf-8") as jf:
            json.dump(report_data, jf, indent=2)
            
        with open(report_dir / "report.md", "w", encoding="utf-8") as mf:
            mf.write(md_content)

        return report_data

    @classmethod
    def compile_markdown_report(cls, r: Dict[str, Any]) -> str:
        """
        Assembles report dictionary into a polished Github Flavored Markdown text.
        """
        secrets_table = "| File Path | Line | Issue Found | Details |\n| :--- | :--- | :--- | :--- |\n"
        if r["secrets_leakages"]:
            for sec in r["secrets_leakages"]:
                secrets_table += f"| {sec['file_path']} | {sec['line']} | {sec['issue']} | `{sec['match']}` |\n"
        else:
            secrets_table += "| *No secrets leakages detected* | - | - | - |\n"

        deps_list = ", ".join(f"`{d}`" for d in r["dependencies_list"]) if r["dependencies_list"] else "*None detected*"

        md = f"""# Repository Audit and Analysis Report

## Executive Summary
* **Repository ID**: `{r['repository_id']}`
* **Architecture Integrity Score**: `{r['architecture_score']}/100`
* **Security Confidence Score**: `{r['security_score']}/100`
* **Maintainability Index**: `{r['maintainability_score']}/100`
* **Total Complexity Loops**: `{r['complexity_score']}`

## Codebase Metrics
* **Total Files**: {r['metrics']['total_files']}
* **Total Line Count**: {r['metrics']['total_lines']}
* **Average Complexity Index**: {r['metrics']['avg_complexity_index']}

---

## Architectural Analysis Critique
{r['architecture_analysis']}

---

## Dependency & Bill of Materials (BOM)
* **Total Dependencies**: {r['dependencies_count']}
* **Detected Dependencies**: {deps_list}

---

## Security Scan (Hardcoded Secrets Detection)
{secrets_table}

### Security Context Analysis
{r['security_analysis']}

---

## Modernization Suggestions
"""
        for idx, sug in enumerate(r["suggestions"]):
            md += f"{idx+1}. {sug}\n"
            
        return md
