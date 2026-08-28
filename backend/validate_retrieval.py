"""
validate_retrieval.py — Phase 0 Retrieval Validation
======================================================
Validates retrieval quality by running structured benchmark questions against
indexed repositories in Chroma WITHOUT any LLM involvement.

The purpose is to prove that the retrieval layer surfaces relevant code chunks
before investing in LLM integration, provider work, or frontend polish.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE (run from backend/ with .venv active)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  # Validate a single already-indexed repo
  python validate_retrieval.py --repo fastapi_test

  # Validate all three repos (fastapi + langchain + chroma)
  python validate_retrieval.py --all

  # Clone + index a repo automatically, then validate
  python validate_retrieval.py --clone fastapi

  # Clone + index ALL three repos, then validate each
  python validate_retrieval.py --clone-all

  # Control chunk retrieval depth (default: 5)
  python validate_retrieval.py --repo fastapi_test --top-k 7

  # Save JSON report to data/reports/
  python validate_retrieval.py --repo fastapi_test --report

  # Run only FastAPI questions (skip LangChain/Chroma suite)
  python validate_retrieval.py --repo fastapi_test --suite fastapi

  # List all collections currently in Chroma
  python validate_retrieval.py --list-collections

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUCCESS CRITERIA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  PASS     ≥ 70% of retrieved chunks contain expected keywords
  MARGINAL 40–69%
  FAIL     < 40%  → fix chunking/metadata before continuing

Distance thresholds (BGE cosine distance, lower = more similar):
  EXCELLENT ≤ 0.20 | GOOD ≤ 0.35 | FAIR ≤ 0.50 | WEAK ≤ 0.70 | POOR > 0.70

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  VECTOR_PROVIDER=cloud_chroma  (or local_chroma)  in ../.env
  EMBEDDING_PROVIDER=local_bge                     in ../.env
  Repository must be indexed first (or use --clone / --clone-all).
"""

import sys
import time
import json
import shutil
import argparse
import textwrap
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

# Force UTF-8 output on Windows to avoid cp1252 UnicodeEncodeError
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Path setup — must precede all app imports ─────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import settings
from app.services.retriever import RetrieverService, RetrievalResult, RetrievedChunk
from app.services.vector_store import VectorStore

# ── ANSI colours (graceful Windows fallback) ──────────────────────────────────
try:
    import colorama
    colorama.init(autoreset=True)
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    RED    = "\033[91m"
    BLUE   = "\033[94m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"
except ImportError:
    GREEN = YELLOW = CYAN = RED = BLUE = BOLD = DIM = RESET = ""

# ── Well-known repo definitions ───────────────────────────────────────────────
REPOS_DIR = Path(__file__).parent.parent / "Repos"

KNOWN_REPOS = {
    "fastapi":   {
        "path":       REPOS_DIR / "fastapi",
        "clone_url":  "https://github.com/tiangolo/fastapi.git",
        "default_id": "fastapi_test",
        "branch":     "master",
        "suite":      "fastapi",
    },
    "langchain": {
        "path":       REPOS_DIR / "langchain",
        "clone_url":  "https://github.com/langchain-ai/langchain.git",
        "default_id": "langchain_test",
        "branch":     "master",
        "suite":      "langchain",
    },
    "chroma":    {
        "path":       REPOS_DIR / "chroma",
        "clone_url":  "https://github.com/chroma-core/chroma.git",
        "default_id": "chroma_test",
        "branch":     "main",
        "suite":      "chroma",
    },
}

# ── Validation question banks ─────────────────────────────────────────────────
#
# Each question:
#   id       — short slug (shown in tables)
#   query    — natural-language question sent to RetrieverService
#   keywords — strings expected in relevant chunks (used for automatic scoring)
#   suite    — which repo this question targets ("fastapi" | "langchain" | "chroma" | "all")
#

VALIDATION_QUESTIONS = [

    # ── FastAPI suite ────────────────────────────────────────────────────────
    {
        "id":       "fastapi_Q1_routes",
        "query":    "How are routes registered in the application?",
        "keywords": ["APIRouter", "include_router", "app.get", "app.post",
                     "app.add_api_route", "router", "decorator", "@app"],
        "suite":    "fastapi",
    },
    {
        "id":       "fastapi_Q2_dependency_injection",
        "query":    "How does dependency injection work in FastAPI?",
        "keywords": ["Depends", "dependency", "inject", "get_db",
                     "yield", "dependencies", "FastAPI"],
        "suite":    "fastapi",
    },
    {
        "id":       "fastapi_Q3_request_validation",
        "query":    "How are incoming HTTP requests validated?",
        "keywords": ["BaseModel", "pydantic", "validator", "Field",
                     "schema", "body", "Query", "Path", "Header"],
        "suite":    "fastapi",
    },
    {
        "id":       "fastapi_Q4_middleware",
        "query":    "How does middleware work in FastAPI?",
        "keywords": ["middleware", "add_middleware", "BaseHTTPMiddleware",
                     "dispatch", "call_next", "Middleware", "CORS"],
        "suite":    "fastapi",
    },
    {
        "id":       "fastapi_Q5_exception_handling",
        "query":    "How are exceptions handled in FastAPI?",
        "keywords": ["HTTPException", "exception_handler", "RequestValidationError",
                     "status_code", "detail", "raise", "ExceptionHandler"],
        "suite":    "fastapi",
    },

    # ── LangChain suite ──────────────────────────────────────────────────────
    {
        "id":       "langchain_Q1_chain_execution",
        "query":    "How are chains executed in LangChain?",
        "keywords": ["chain", "invoke", "run", "pipe", "RunnableSequence",
                     "LLMChain", "__call__", "arun"],
        "suite":    "langchain",
    },
    {
        "id":       "langchain_Q2_tool_registration",
        "query":    "How are tools registered and used in LangChain agents?",
        "keywords": ["Tool", "tool", "@tool", "BaseTool", "agent",
                     "tools", "AgentExecutor", "bind_tools"],
        "suite":    "langchain",
    },
    {
        "id":       "langchain_Q3_memory",
        "query":    "How does memory work in LangChain conversations?",
        "keywords": ["memory", "ConversationBufferMemory", "chat_history",
                     "MessagesPlaceholder", "history", "BaseMemory"],
        "suite":    "langchain",
    },
    {
        "id":       "langchain_Q4_prompts",
        "query":    "How are prompts processed and formatted in LangChain?",
        "keywords": ["PromptTemplate", "ChatPromptTemplate", "format",
                     "template", "HumanMessage", "SystemMessage", "prompt"],
        "suite":    "langchain",
    },
    {
        "id":       "langchain_Q5_retrieval",
        "query":    "How is retrieval implemented in LangChain RAG?",
        "keywords": ["retriever", "vectorstore", "similarity_search",
                     "RetrievalQA", "VectorStoreRetriever", "get_relevant_documents"],
        "suite":    "langchain",
    },

    # ── Chroma suite ─────────────────────────────────────────────────────────
    {
        "id":       "chroma_Q1_collection_creation",
        "query":    "How are Chroma collections created?",
        "keywords": ["create_collection", "get_or_create_collection",
                     "Collection", "collection", "chromadb"],
        "suite":    "chroma",
    },
    {
        "id":       "chroma_Q2_embedding_storage",
        "query":    "How are embeddings stored in Chroma?",
        "keywords": ["add", "upsert", "embeddings", "documents",
                     "metadatas", "ids", "insert"],
        "suite":    "chroma",
    },
    {
        "id":       "chroma_Q3_similarity_search",
        "query":    "How does similarity search work in Chroma?",
        "keywords": ["query", "query_embeddings", "n_results",
                     "distances", "similarity", "search", "where"],
        "suite":    "chroma",
    },
    {
        "id":       "chroma_Q4_persistence",
        "query":    "How does Chroma handle data persistence?",
        "keywords": ["persist", "PersistentClient", "path", "storage",
                     "disk", "sqlite", "DuckDB", "persist_directory"],
        "suite":    "chroma",
    },
    {
        "id":       "chroma_Q5_filtering",
        "query":    "How are metadata filters applied in Chroma queries?",
        "keywords": ["where", "where_document", "filter", "metadata",
                     "operator", "$contains", "$eq", "$and"],
        "suite":    "chroma",
    },
]

# Display constants
PREVIEW_CHARS = 400   # max chars in chunk preview
PREVIEW_LINES = 8     # max lines in chunk preview
TABLE_WIDTH   = 78


# ------------------------------------------------------------------------------
# Formatting helpers
# ------------------------------------------------------------------------------

def _sep(title: str = "", char: str = "=", width: int = TABLE_WIDTH) -> None:
    if title:
        inner   = f"  {title}  "
        pad_tot = max(0, width - len(inner))
        left    = char * (pad_tot // 2)
        right   = char * (pad_tot - pad_tot // 2)
        print(f"\n{BOLD}{CYAN}{left}{inner}{right}{RESET}")
    else:
        print(f"{DIM}{char * width}{RESET}")


def _score_label(distance: float) -> str:
    """Human-readable relevance label from Chroma cosine distance."""
    if distance <= 0.20:
        return f"{GREEN}EXCELLENT{RESET}"
    elif distance <= 0.35:
        return f"{GREEN}GOOD{RESET}"
    elif distance <= 0.50:
        return f"{YELLOW}FAIR{RESET}"
    elif distance <= 0.70:
        return f"{YELLOW}WEAK{RESET}"
    else:
        return f"{RED}POOR{RESET}"


def _keyword_hits(text: str, keywords: list) -> list:
    return [kw for kw in keywords if kw.lower() in text.lower()]


def _preview(text: str) -> str:
    lines = text.strip().splitlines()[:PREVIEW_LINES]
    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line.rstrip(), width=90) or [""])
    preview_lines = wrapped[:PREVIEW_LINES]
    return "\n".join(f"    {ln}" for ln in preview_lines)


def _entity_label(chunk: RetrievedChunk) -> str:
    """Shows class::method or just function name if available."""
    if chunk.class_name and chunk.function_name:
        return f"{chunk.class_name}::{chunk.function_name}"
    return chunk.function_name or chunk.class_name or ""


# ------------------------------------------------------------------------------
# Clone + Index helpers
# ------------------------------------------------------------------------------

def clone_repo(name: str) -> Path:
    """Shallow-clone a known repo into Repos/<name>."""
    meta       = KNOWN_REPOS[name]
    clone_path = meta["path"]
    url        = meta["clone_url"]
    branch     = meta["branch"]

    if clone_path.exists() and any(clone_path.iterdir()):
        print(f"  {YELLOW}[SKIP]{RESET} {name} already cloned → {clone_path}")
        return clone_path

    print(f"  {CYAN}[CLONE]{RESET} {url} (branch: {branch}) → {clone_path}")
    clone_path.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            ["git", "clone", "--depth=1", f"--branch={branch}", url, str(clone_path)],
            check=True,
            capture_output=True,
        )
        print(f"  {GREEN}[OK]{RESET} Cloned {name} successfully.")
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace") if e.stderr else ""
        print(f"  {RED}[ERROR]{RESET} git clone failed: {stderr[:300]}")
        raise RuntimeError(f"Could not clone {name}: {stderr[:200]}")

    return clone_path


def index_repo(name: str) -> None:
    """Run index_repository.py for a known repo."""
    meta    = KNOWN_REPOS[name]
    repo_id = meta["default_id"]

    print(f"\n  {CYAN}[INDEX]{RESET} Indexing '{name}' as collection '{repo_id}'...")
    indexer = Path(__file__).parent / "index_repository.py"
    result  = subprocess.run(
        [sys.executable, str(indexer), "--repo", name, "--id", repo_id],
        capture_output=False,   # stream output to terminal
    )
    if result.returncode != 0:
        print(f"  {RED}[ERROR]{RESET} Indexing failed with return code {result.returncode}.")
        raise RuntimeError(f"Indexing failed for '{name}'")
    print(f"  {GREEN}[OK]{RESET} Indexing complete for '{name}'.")


# ------------------------------------------------------------------------------
# Core validation logic
# ------------------------------------------------------------------------------

def validate_question(
    repo_id:  str,
    question: dict,
    top_k:    int = 5,
) -> dict:
    """
    Execute one retrieval benchmark question using RetrieverService.
    No LLM is involved.
    """
    q_id  = question["id"]
    query = question["query"]
    kws   = question["keywords"]

    result: RetrievalResult = RetrieverService.retrieve(
        repo_id = repo_id,
        query   = query,
        top_k   = top_k,
    )

    # Score each chunk by keyword presence
    scored = []
    for chunk in result.chunks:
        combined_text = chunk.content + " " + chunk.file_path
        hits          = _keyword_hits(combined_text, kws)
        scored.append({
            "chunk":        chunk,
            "keyword_hits": hits,
            "hit_count":    len(hits),
        })

    total_hits    = sum(1 for s in scored if s["hit_count"] > 0)
    relevance_pct = round(total_hits / max(len(scored), 1) * 100)

    return {
        "question_id":   q_id,
        "query":         query,
        "suite":         question["suite"],
        "keywords":      kws,
        "chunks":        scored,
        "avg_distance":  result.avg_distance,
        "avg_score":     result.avg_score,
        "relevance_pct": relevance_pct,
        "elapsed_s":     result.query_time_s,
        "retrieved_files": result.retrieved_files,
    }


# ------------------------------------------------------------------------------
# Display functions
# ------------------------------------------------------------------------------

def print_question_result(res: dict, q_number: int, total_qs: int) -> None:
    """Pretty-prints one question's retrieval results."""
    _sep(f"Q{q_number}/{total_qs} · {res['question_id']}")

    print(f"\n  {BOLD}Query   :{RESET}  {CYAN}{res['query']}{RESET}")
    print(f"  Suite   :  {res['suite']}")
    print(
        f"  Results :  {len(res['chunks'])} chunks  |  "
        f"AvgDist={res['avg_distance']}  |  "
        f"AvgScore={res['avg_score']}  |  "
        f"Relevance={res['relevance_pct']}%  |  "
        f"Time={res['elapsed_s']}s"
    )
    if res["retrieved_files"]:
        print(f"  Files   :  {', '.join(res['retrieved_files'][:4])}"
              + ("..." if len(res["retrieved_files"]) > 4 else ""))
    print()

    for rank, entry in enumerate(res["chunks"], 1):
        chunk: RetrievedChunk = entry["chunk"]
        entity_str = _entity_label(chunk)
        entity_tag = f" → {entity_str}" if entity_str else ""

        dist_label = _score_label(chunk.distance)
        lang_tag   = f"[{chunk.language}] " if chunk.language else ""

        print(
            f"  {BOLD}[#{rank}]{RESET} "
            f"{YELLOW}{lang_tag}{chunk.file_path}{entity_tag}{RESET}\n"
            f"         {chunk.chunk_type.upper()}  "
            f"L{chunk.start_line}–{chunk.end_line}  "
            f"dist={chunk.distance:.4f}  score={chunk.relevance_score:.3f}  "
            f"{dist_label}"
        )

        if entry["keyword_hits"]:
            hits_str = "  ".join(entry["keyword_hits"][:6])
            print(f"         {GREEN}✓ Keywords:{RESET} {hits_str}")
        else:
            print(f"         {DIM}✗ No keyword hits{RESET}")

        if chunk.chunk_hash:
            print(f"         {DIM}hash: {chunk.chunk_hash}...{RESET}")

        print()
        print(_preview(chunk.content))
        print()


def print_summary_table(results: list, repo_id: str) -> None:
    """Final comparison table across all questions."""
    _sep(f"RETRIEVAL VALIDATION SUMMARY — {repo_id}")

    print(f"\n  Repository : {BOLD}{repo_id}{RESET}")
    print(f"  Provider   : {settings.VECTOR_PROVIDER}")
    print(f"  Embedding  : {settings.EMBEDDING_MODEL_NAME}")
    print(f"  Timestamp  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Column widths
    c1, c2, c3, c4, c5, c6 = 36, 7, 10, 10, 11, 8
    header = (
        f"  {'Question':<{c1}} {'Chunks':>{c2}} "
        f"{'AvgDist':>{c3}} {'AvgScore':>{c5}} {'Relevance':>{c4}} {'Time':>{c6}}"
    )
    print(BOLD + header + RESET)
    print("  " + "-" * (c1 + c2 + c3 + c4 + c5 + c6 + 5))

    all_relevance = []
    all_distances = []

    for r in results:
        q_short  = r["question_id"].replace("_", " ")[:c1]
        rel      = r["relevance_pct"]
        dist     = r["avg_distance"]
        score    = r["avg_score"]
        n_chunks = len(r["chunks"])
        all_relevance.append(rel)
        all_distances.append(dist)

        if rel >= 70:
            rel_str = f"{GREEN}{rel:>9}%{RESET}"
        elif rel >= 40:
            rel_str = f"{YELLOW}{rel:>9}%{RESET}"
        else:
            rel_str = f"{RED}{rel:>9}%{RESET}"

        print(
            f"  {q_short:<{c1}} {n_chunks:>{c2}} "
            f"{dist:>{c3}.4f} {score:>{c5}.3f} {rel_str} {r['elapsed_s']:>{c6}.2f}s"
        )

    print("  " + "─" * (c1 + c2 + c3 + c4 + c5 + c6 + 5))

    avg_rel  = round(sum(all_relevance) / max(len(all_relevance), 1))
    avg_dist = round(sum(all_distances) / max(len(all_distances), 1), 4)

    if avg_rel >= 70:
        verdict_color = GREEN
        verdict = "[PASS]"
        action  = "Retrieval quality meets the 70% threshold. Continue to LLM integration."
    elif avg_rel >= 40:
        verdict_color = YELLOW
        verdict = "[MARGINAL]"
        action  = "Retrieval is borderline. Review low-scoring questions and improve chunking."
    else:
        verdict_color = RED
        verdict = "[FAIL]"
        action  = "STOP. Fix chunking, metadata, or re-index before continuing."

    print(
        f"  {'OVERALL':<{c1}} {'':{c2}} "
        f"{avg_dist:>{c3}.4f} {'':{c5}} "
        f"{verdict_color}{avg_rel:>9}%{RESET} {'':{c6}}"
    )
    print()
    print(f"  {BOLD}Verdict : {verdict_color}{verdict}{RESET}")
    print(f"  Action  : {action}")
    print()
    _sep(char="-")
    print(
        "  Distance guide: EXCELLENT <=0.20 | GOOD <=0.35 | FAIR <=0.50 | "
        "WEAK <=0.70 | POOR >0.70\n"
        "  Relevance = % of retrieved chunks containing expected keywords"
    )
    _sep()


def print_cross_repo_summary(all_results: dict) -> None:
    """Prints a comparison table when multiple repos were validated."""
    _sep("CROSS-REPOSITORY COMPARISON")
    print()

    c1, c2, c3, c4 = 20, 12, 12, 10
    header = f"  {'Repository':<{c1}} {'Questions':>{c2}} {'AvgDist':>{c3}} {'Relevance':>{c4}}"
    print(BOLD + header + RESET)
    print("  " + "-" * (c1 + c2 + c3 + c4 + 3))

    for repo_id, results in all_results.items():
        avg_rel  = round(sum(r["relevance_pct"] for r in results) / max(len(results), 1))
        avg_dist = round(sum(r["avg_distance"]  for r in results) / max(len(results), 1), 4)
        n_qs     = len(results)
        col      = GREEN if avg_rel >= 70 else (YELLOW if avg_rel >= 40 else RED)
        print(
            f"  {repo_id:<{c1}} {n_qs:>{c2}} "
            f"{avg_dist:>{c3}.4f} {col}{avg_rel:>{c4}}%{RESET}"
        )

    print("  " + "-" * (c1 + c2 + c3 + c4 + 3))
    print()
    _sep()


# ------------------------------------------------------------------------------
# Report serialization
# ═══════════════════════════════════════════════════════════════════════════════

def save_report(results: list, repo_id: str, out_dir: Path) -> Path:
    """Save JSON report to disk."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"retrieval_report_{repo_id}_{ts}.json"

    serializable = []
    for r in results:
        entry = {k: v for k, v in r.items() if k != "chunks"}
        entry["chunks"] = [
            {
                "file_path":     c["chunk"].file_path,
                "language":      c["chunk"].language,
                "chunk_type":    c["chunk"].chunk_type,
                "start_line":    c["chunk"].start_line,
                "end_line":      c["chunk"].end_line,
                "distance":      c["chunk"].distance,
                "score":         c["chunk"].relevance_score,
                "keyword_hits":  c["keyword_hits"],
                "preview":       c["chunk"].content[:300],
            }
            for c in r["chunks"]
        ]
        serializable.append(entry)

    report = {
        "repo_id":   repo_id,
        "provider":  settings.VECTOR_PROVIDER,
        "embedding": settings.EMBEDDING_MODEL_NAME,
        "timestamp": datetime.now().isoformat(),
        "questions": serializable,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# Validation runner
# ═══════════════════════════════════════════════════════════════════════════════

def run_validation(
    repo_id:  str,
    suite:    Optional[str],
    top_k:    int,
    save:     bool,
    verbose:  bool = True,
) -> list:
    """
    Run all benchmark questions for a single repo_id.
    Returns list of result dicts.
    """
    # Verify collection exists
    chroma_stats = VectorStore.repository_statistics(repo_id)
    vector_count = chroma_stats.get("vector_count", 0)

    if vector_count == 0:
        print(f"\n  {RED}[ERROR]{RESET} Collection '{repo_id}' is empty or does not exist.")
        print(f"  Run:  python index_repository.py --repo fastapi --id {repo_id}")
        print(f"  Or :  python validate_retrieval.py --clone fastapi\n")
        return []

    print(f"\n  {GREEN}[OK]{RESET} Collection '{repo_id}' → {vector_count:,} vectors")

    # Filter questions by suite
    questions = VALIDATION_QUESTIONS
    if suite and suite != "all":
        questions = [q for q in VALIDATION_QUESTIONS if q["suite"] == suite]
        if not questions:
            print(f"  {YELLOW}[WARN]{RESET} No questions found for suite='{suite}'. "
                  f"Valid: fastapi, langchain, chroma, all")
            return []

    print(f"  Running {len(questions)} question(s) with top_k={top_k} ...\n")

    results = []
    for i, question in enumerate(questions, 1):
        print(f"  {DIM}[{i}/{len(questions)}] {question['id']}...{RESET}", end="\r", flush=True)
        res = validate_question(repo_id, question, top_k=top_k)
        results.append(res)
        if verbose:
            print_question_result(res, i, len(questions))

    print_summary_table(results, repo_id)

    if save:
        reports_dir = Path(__file__).parent / "data" / "reports" / repo_id
        path = save_report(results, repo_id, reports_dir)
        print(f"  {CYAN}[REPORT]{RESET} Saved → {path}\n")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Phase 0 — Retrieval quality validation (no LLM).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.strip().split("━")[0],
    )

    # Target selection (mutually exclusive)
    target_group = parser.add_mutually_exclusive_group()
    target_group.add_argument(
        "--repo", metavar="REPO_ID",
        help="Chroma collection ID to validate (e.g. fastapi_test)."
    )
    target_group.add_argument(
        "--all", action="store_true",
        help="Validate all three collections: fastapi_test, langchain_test, chroma_test."
    )
    target_group.add_argument(
        "--clone", metavar="NAME", choices=list(KNOWN_REPOS.keys()),
        help="Clone + index a known repo (fastapi | langchain | chroma), then validate."
    )
    target_group.add_argument(
        "--clone-all", action="store_true",
        help="Clone + index ALL three repos, then validate each."
    )
    target_group.add_argument(
        "--list-collections", action="store_true",
        help="List all Chroma collections and their vector counts, then exit."
    )

    # Options
    parser.add_argument("--top-k",  type=int, default=5,
                        help="Chunks to retrieve per query (default: 5).")
    parser.add_argument("--suite",  choices=["fastapi", "langchain", "chroma", "all"],
                        default="all",
                        help="Question suite to run (default: all).")
    parser.add_argument("--report", action="store_true",
                        help="Save JSON report to data/reports/<repo_id>/.")
    parser.add_argument("--quiet",  action="store_true",
                        help="Suppress per-chunk output, show only summary table.")

    args = parser.parse_args()
    verbose = not args.quiet

    # ── --list-collections ────────────────────────────────────────────────────
    if args.list_collections:
        _sep("CHROMA COLLECTIONS")
        print(f"\n  Provider : {settings.VECTOR_PROVIDER}\n")
        for name, meta in KNOWN_REPOS.items():
            repo_id = meta["default_id"]
            try:
                stats = VectorStore.repository_statistics(repo_id)
                vc    = stats.get("vector_count", 0)
                col   = GREEN if vc > 0 else DIM
                print(f"  {col}{repo_id:<20}{RESET}  {vc:>8,} vectors")
            except Exception as e:
                print(f"  {RED}{repo_id:<20}{RESET}  ERROR: {e}")
        print()
        return

    # ── --clone / --clone-all ─────────────────────────────────────────────────
    repos_to_clone = []
    if args.clone:
        repos_to_clone = [args.clone]
    elif args.clone_all:
        repos_to_clone = list(KNOWN_REPOS.keys())

    if repos_to_clone:
        _sep(f"CLONING {len(repos_to_clone)} REPO(S)")
        for name in repos_to_clone:
            try:
                clone_repo(name)
                index_repo(name)
            except RuntimeError as e:
                print(f"  {RED}[ABORT]{RESET} {e}")
                sys.exit(1)

    # ── Determine which repo_ids to validate ──────────────────────────────────
    if args.clone or args.clone_all:
        names   = repos_to_clone
        repo_ids = [KNOWN_REPOS[n]["default_id"] for n in names]
        suites   = [KNOWN_REPOS[n]["suite"]       for n in names]
    elif args.all:
        repo_ids = [m["default_id"] for m in KNOWN_REPOS.values()]
        suites   = [m["suite"]      for m in KNOWN_REPOS.values()]
    elif args.repo:
        repo_ids = [args.repo]
        suites   = [args.suite]
    else:
        parser.print_help()
        sys.exit(0)

    # ── Run validation for each repo ──────────────────────────────────────────
    all_results = {}

    _sep("PHASE 0 · RETRIEVAL VALIDATOR")
    print(f"\n  Provider  : {settings.VECTOR_PROVIDER}")
    print(f"  Embedding : {settings.EMBEDDING_MODEL_NAME}")
    print(f"  Top-K     : {args.top_k}")
    print(f"  Suite     : {args.suite}")
    print(f"  Repos     : {', '.join(repo_ids)}")
    _sep()

    for repo_id, suite_hint in zip(repo_ids, suites):
        # Use suite_hint only if user didn't specify --suite explicitly
        effective_suite = args.suite if args.suite != "all" else suite_hint

        results = run_validation(
            repo_id = repo_id,
            suite   = effective_suite,
            top_k   = args.top_k,
            save    = args.report,
            verbose = verbose,
        )
        if results:
            all_results[repo_id] = results

    # ── Cross-repo comparison (only when more than one repo ran) ──────────────
    if len(all_results) > 1:
        print_cross_repo_summary(all_results)


if __name__ == "__main__":
    main()
