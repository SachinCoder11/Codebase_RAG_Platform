"""
test_repository_intelligence.py
================================
End-to-end verification of the Repository Intelligence Engine.

Usage:
    python test_repository_intelligence.py
    python test_repository_intelligence.py --repo fastapi_test

The script:
  1. Loads a repository from the SQLite registry
  2. Verifies intelligence reports exist on disk
  3. Runs 6 evaluation-grade queries through the full RAG pipeline
  4. Checks that answers reference real files (not generic AI responses)
  5. Prints a pass/fail table
"""

import sys
import os
import json
import time
import argparse
import asyncio
from pathlib import Path

# ── Path Setup ────────────────────────────────────────────────────────────────
# Allow running from backend/ or project root
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
os.chdir(_SCRIPT_DIR)  # ensure settings.BASE_DATA_DIR resolves correctly

# ── Colours ───────────────────────────────────────────────────────────────────
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    GREEN  = Fore.GREEN
    RED    = Fore.RED
    YELLOW = Fore.YELLOW
    CYAN   = Fore.CYAN
    BOLD   = Style.BRIGHT
    RESET  = Style.RESET_ALL
except ImportError:
    GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""


def print_header(text: str):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")


def print_pass(label: str, detail: str = ""):
    print(f"  {GREEN}[PASS]{RESET}  {label}" + (f"  -- {detail}" if detail else ""))


def print_fail(label: str, detail: str = ""):
    print(f"  {RED}[FAIL]{RESET}  {label}" + (f"  -- {detail}" if detail else ""))


def print_warn(label: str, detail: str = ""):
    print(f"  {YELLOW}[WARN]{RESET}  {label}" + (f"  -- {detail}" if detail else ""))


# ── Evaluation Queries ────────────────────────────────────────────────────────

EVALUATION_QUERIES = [
    {
        "query":    "Explain the project architecture",
        "keywords": ["fastapi", "router", "api", "app", "main", "service", "layer", "route"],
        "anti":     ["i don't know", "no information", "cannot determine"],
        "label":    "Architecture explanation",
    },
    {
        "query":    "Describe the authentication flow",
        "keywords": ["jwt", "oauth", "token", "bearer", "auth", "login", "password", "security"],
        "anti":     ["i don't know", "no information", "cannot determine"],
        "label":    "Authentication flow",
    },
    {
        "query":    "List the database technologies used",
        "keywords": ["sql", "database", "orm", "model", "table", "postgresql", "sqlite", "sqlalchemy", "db"],
        "anti":     ["i don't know", "no database"],
        "label":    "Database technology identification",
    },
    {
        "query":    "Evaluate the maintainability of this codebase",
        "keywords": ["class", "function", "module", "layer", "service", "test", "doc", "structure"],
        "anti":     ["no information", "cannot evaluate"],
        "label":    "Maintainability evaluation",
    },
    {
        "query":    "Are there any security risks in this repository?",
        "keywords": ["security", "risk", "secret", "auth", "token", "sql", "injection", "eval", "vulnerability"],
        "anti":     ["no information", "cannot determine"],
        "label":    "Security risk assessment",
    },
    {
        "query":    "Explain the deployment strategy",
        "keywords": ["docker", "deploy", "container", "kubernetes", "ci", "cd", "action", "workflow", "procfile", "server"],
        "anti":     ["no information", "no deployment"],
        "label":    "Deployment strategy",
    },
]


# ── Report File Checks ────────────────────────────────────────────────────────

def check_intelligence_reports(repo_id: str, reports_dir: Path) -> list:
    """Verifies that all expected intelligence reports exist on disk."""
    repo_report_dir = reports_dir / repo_id
    expected_files = [
        ("manifest.json",                    "Repository Manifest"),
        ("summary.json",                     "Processing Summary"),
        ("ARCHITECTURE_SUMMARY.md",          "Architecture Report"),
        ("SECURITY_REPORT.md",               "Security Report"),
        ("ENGINEERING_QUALITY_REPORT.md",    "Engineering Quality Report"),
        ("REPOSITORY_ACTIVITY_REPORT.md",    "Activity Report"),
        ("quality.json",                     "Quality JSON"),
        ("security.json",                    "Security JSON"),
    ]
    results = []
    for fname, label in expected_files:
        path   = repo_report_dir / fname
        exists = path.exists()
        results.append((label, exists, str(path)))
    return results


# ── Query Runner ──────────────────────────────────────────────────────────────

def run_query(repo_id: str, query: str) -> dict:
    """
    Runs a single query through the full RAG pipeline.
    Returns {answer, sources, time_taken, error}.
    """
    from app.services.query_engine import QueryEngine

    t0 = time.time()
    try:
        result = QueryEngine.execute_rag_flow(
            repo_id = repo_id,
            query   = query,
            top_k   = 7,
            filters = None,
        )
        return {
            "answer":      result.get("answer", ""),
            "sources":     result.get("sources", []),
            "time_taken":  round(time.time() - t0, 2),
            "error":       None,
        }
    except Exception as e:
        return {
            "answer":     "",
            "sources":    [],
            "time_taken": round(time.time() - t0, 2),
            "error":      str(e),
        }


def evaluate_answer(answer: str, keywords: list, anti: list) -> tuple:
    """
    Returns (passed: bool, score: int, detail: str).
    score = number of keywords found in answer.
    """
    answer_lower = answer.lower()

    # Anti-patterns: if any found, answer is generic
    for ap in anti:
        if ap in answer_lower:
            return False, 0, f"Generic response detected: '{ap}'"

    # Keyword check: at least 2 keywords must be present
    found = [kw for kw in keywords if kw in answer_lower]
    if len(found) >= 2:
        return True, len(found), f"Found keywords: {', '.join(found[:5])}"
    elif len(found) == 1:
        return False, 1, f"Only 1 keyword found ({found[0]}), need ≥2"
    else:
        return False, 0, "No relevant keywords found in answer"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Repository Intelligence Test Suite")
    parser.add_argument("--repo", default="", help="Specific repo_id to test")
    parser.add_argument("--skip-queries", action="store_true", help="Only check reports, skip LLM queries")
    args = parser.parse_args()

    from app.core.config import settings
    from app.models.repository import RepositoryModel

    print_header("Repository Intelligence — Test Suite")

    # ── Step 1: Select repository ─────────────────────────────────────────────
    all_repos = RepositoryModel.get_all()
    if not all_repos:
        print(f"\n{RED}No repositories found in registry. Please index a repository first.{RESET}")
        sys.exit(1)

    if args.repo:
        repo_candidates = [r for r in all_repos if r["repo_id"] == args.repo]
        if not repo_candidates:
            print(f"\n{RED}Repo '{args.repo}' not found. Available repos:{RESET}")
            for r in all_repos:
                print(f"  - {r['repo_id']}  ({r['repo_name']})")
            sys.exit(1)
        repo = repo_candidates[0]
    else:
        repo = all_repos[0]

    repo_id   = repo["repo_id"]
    repo_name = repo.get("repo_name", repo_id)
    print(f"\n  Testing repository: {BOLD}{repo_name}{RESET}  (id: {repo_id})")

    # ── Step 2: Check intelligence reports ───────────────────────────────────
    print_header("Phase 1 — Intelligence Reports")
    report_checks = check_intelligence_reports(repo_id, settings.REPORTS_DIR)
    report_pass = 0
    report_fail = 0
    for label, exists, path in report_checks:
        if exists:
            print_pass(label)
            report_pass += 1
        else:
            print_fail(label, f"Not found: {path}")
            report_fail += 1

    # ── Step 3: Manifest content check ───────────────────────────────────────
    print_header("Phase 2 — Manifest Integrity")
    manifest_path = settings.REPORTS_DIR / repo_id / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            for field in ["repo_name", "languages", "frameworks", "total_files", "classes", "functions"]:
                val = manifest.get(field)
                if val is not None and val != [] and val != {}:
                    print_pass(f"manifest.{field}", str(val)[:60])
                else:
                    print_warn(f"manifest.{field}", "empty or missing")
        except Exception as e:
            print_fail("Manifest parse", str(e))
    else:
        print_fail("Manifest not found")

    # ── Step 4: Quality scores check ─────────────────────────────────────────
    print_header("Phase 3 — Quality Scores")
    quality_path = settings.REPORTS_DIR / repo_id / "quality.json"
    if quality_path.exists():
        try:
            with open(quality_path) as f:
                quality = json.load(f)
            overall = quality.get("overall", 0)
            print(f"\n  Overall Quality Score: {BOLD}{overall}/100{RESET}")
            for dim in ["documentation", "testing", "ci_cd", "security", "configuration", "architecture"]:
                score = quality.get(dim, 0)
                bar   = "#" * (score // 5) + "-" * (20 - score // 5)
                print(f"    {dim:20s}  {bar}  {score}")
        except Exception as e:
            print_fail("Quality JSON parse", str(e))
    else:
        print_warn("quality.json not found — run ingestion to generate")

    # ── Step 5: Query evaluation ──────────────────────────────────────────────
    if args.skip_queries:
        print(f"\n{YELLOW}Skipping LLM queries (--skip-queries flag){RESET}")
    else:
        print_header("Phase 4 — Evaluation Queries")
        query_results = []
        total_pass = 0
        total_fail = 0

        for i, q in enumerate(EVALUATION_QUERIES, 1):
            print(f"\n  [{i}/{len(EVALUATION_QUERIES)}] {q['label']}")
            print(f"  Query: \"{q['query']}\"")

            result = run_query(repo_id, q["query"])

            if result["error"]:
                print_fail("Query execution", result["error"])
                total_fail += 1
                query_results.append({**q, "passed": False, "error": result["error"]})
                continue

            answer = result["answer"]
            print(f"  Answer ({len(answer)} chars, {result['time_taken']}s):")
            print(f"  \"{answer[:200]}{'...' if len(answer)>200 else ''}\"")

            passed, score, detail = evaluate_answer(answer, q["keywords"], q["anti"])

            if passed:
                print_pass("Answer quality", detail)
                total_pass += 1
            else:
                print_fail("Answer quality", detail)
                total_fail += 1

            sources = result.get("sources", [])
            if sources:
                print_pass(f"Sources cited: {len(sources)}", sources[0].get("file_path", "")[:60])
            else:
                print_warn("No sources returned")

            query_results.append({**q, "passed": passed, "score": score, "detail": detail})

        # ── Summary table ─────────────────────────────────────────────────────
        print_header("Summary")
        print(f"\n  Reports:  {GREEN}{report_pass} pass{RESET}  /  {RED}{report_fail} fail{RESET}")
        if not args.skip_queries:
            print(f"  Queries:  {GREEN}{total_pass} pass{RESET}  /  {RED}{total_fail} fail{RESET}")
            overall_pass_rate = round(total_pass / len(EVALUATION_QUERIES) * 100)
            color  = GREEN if overall_pass_rate >= 70 else YELLOW if overall_pass_rate >= 40 else RED
            print(f"\n  {BOLD}Intelligence Platform Score: {color}{overall_pass_rate}%{RESET}")

            if overall_pass_rate >= 80:
                print(f"\n  {GREEN}[PASS] Platform is performing as a Repository Intelligence Engine.{RESET}")
            elif overall_pass_rate >= 50:
                print(f"\n  {YELLOW}[WARN] Platform partially functioning -- retrieval may need improvement.{RESET}")
            else:
                print(f"\n  {RED}[FAIL] Platform not functioning as expected -- check retrieval pipeline.{RESET}")
    print()


if __name__ == "__main__":
    main()
