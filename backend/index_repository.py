"""
index_repository.py — Phase 1 Repository Indexer
==================================================
Indexes a local repository into Chroma (cloud or local, controlled by .env).

Usage (from backend/ directory with .venv active):

    # Index FastAPI repo
    python index_repository.py --repo fastapi --id fastapi_test

    # Index LangChain repo
    python index_repository.py --repo langchain --id langchain_test

    # Custom path + repo id
    python index_repository.py --path C:/path/to/myrepo --id my_repo

    # Limit chunks (for quick smoke tests)
    python index_repository.py --repo fastapi --id fastapi_test --limit 200

Requirements:
    VECTOR_PROVIDER=cloud_chroma  (or local_chroma) in ../.env
    EMBEDDING_PROVIDER=local_bge  in ../.env
"""

import sys
import time
import argparse
import logging
from pathlib import Path

# ── Make app imports work when running from backend/ ───────   ──────────────────
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import settings
from app.services.repository_scanner import RepositoryScanner
from app.services.parser.analyzer import CodeParserAnalyzer
from app.services.chunker import Chunker
from app.services.metadata_builder import MetadataBuilder
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStore

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,  # suppress noisy library logs
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("indexer")

# ── Well-known local repo paths ───────────────────────────────────────────────
REPOS_DIR = Path(__file__).parent.parent / "Repos"
KNOWN_REPOS = {
    "fastapi":   REPOS_DIR / "fastapi",
    "langchain": REPOS_DIR / "langchain",
    "chroma":    REPOS_DIR / "chroma",
}

# ── Default repo_id mapping ───────────────────────────────────────────────────
DEFAULT_IDS = {
    "fastapi":   "fastapi_test",
    "langchain": "langchain_test",
    "chroma":    "chroma_test",
}

BATCH_SIZE = 100  # Chroma Cloud safe batch size


def _sep(title: str = "", char: str = "=", width: int = 60) -> None:
    if title:
        pad = max(0, width - len(title) - 2)
        print(f"\n{'=' * (pad // 2)} {title} {'=' * (pad - pad // 2)}")
    else:
        print(char * width)


def _step(n: int, label: str) -> None:
    print(f"\n[STEP {n}] {label}")
    print("-" * 50)


def index_repository(repo_path: Path, repo_id: str, chunk_limit: int = 0) -> dict:
    """
    Runs the full ingestion pipeline for one repository.

    Returns a statistics dict with counts and durations.
    """
    start_total = time.time()
    stats = {
        "repo_id": repo_id,
        "repo_path": str(repo_path),
        "files_scanned": 0,
        "entities_parsed": 0,
        "chunks_total": 0,
        "chunks_indexed": 0,
        "embeddings_generated": 0,
        "batches_uploaded": 0,
        "scan_duration_s": 0.0,
        "embed_duration_s": 0.0,
        "store_duration_s": 0.0,
        "total_duration_s": 0.0,
        "errors": [],
    }

    # ── STEP 1: SCAN ──────────────────────────────────────────────────────────
    _step(1, f"Scanning repository: {repo_path.name}")
    t0 = time.time()
    scan_results = RepositoryScanner.scan_repository(repo_path)
    stats["scan_duration_s"] = round(time.time() - t0, 2)
    stats["files_scanned"] = scan_results["file_count"]

    print(f"  Files scanned   : {scan_results['file_count']}")
    print(f"  Languages       : {scan_results['languages']}")
    print(f"  Frameworks      : {scan_results['frameworks']}")
    print(f"  Total lines     : {scan_results['total_lines']:,}")
    print(f"  Duration        : {stats['scan_duration_s']}s")

    # ── STEP 2: PARSE (AST) ───────────────────────────────────────────────────
    _step(2, "Parsing code entities (AST)")
    entities = CodeParserAnalyzer.analyze_workspace(repo_path, scan_results["indexed_files"])
    stats["entities_parsed"] = len(entities)
    print(f"  Entities parsed : {len(entities):,}")

    # ── STEP 3: CHUNK ─────────────────────────────────────────────────────────
    _step(3, "Chunking entities")
    chunks = Chunker.chunk_entities(repo_path, entities)
    stats["chunks_total"] = len(chunks)
    print(f"  Chunks total    : {len(chunks):,}")

    if chunk_limit and chunk_limit < len(chunks):
        print(f"  ⚠  Limit applied: using first {chunk_limit} chunks (--limit flag)")
        chunks = chunks[:chunk_limit]

    stats["chunks_indexed"] = len(chunks)

    # ── STEP 4: BUILD METADATA ────────────────────────────────────────────────
    _step(4, "Building metadata (hash, file path, entity type)")
    enriched: list[dict] = []
    for chunk in chunks:
        metadata = MetadataBuilder.build_metadata(
            repo_id=repo_id,
            repo_name=repo_path.name,
            owner="local",
            source_type="local",
            file_path=chunk["file_path"],
            language=chunk["language"],
            chunk_type=chunk["chunk_type"],
            class_name=chunk.get("class_name"),
            function_name=chunk.get("function_name"),
            start_line=chunk["start_line"],
            end_line=chunk["end_line"],
            dependencies=chunk.get("dependencies", []),
            content=chunk["content"]
        )
        enriched.append({"content": chunk["content"], "metadata": metadata})

    print(f"  Enriched chunks : {len(enriched):,}")
    print(f"  Sample hash     : {enriched[0]['metadata']['hash'][:16]}..." if enriched else "  No chunks.")

    # ── STEP 5: EMBED ─────────────────────────────────────────────────────────
    _step(5, f"Generating embeddings (batch_size={BATCH_SIZE})")
    documents = [c["content"] for c in enriched]
    metadatas = [c["metadata"] for c in enriched]

    t0 = time.time()
    all_embeddings: list[list[float]] = []
    total_batches = (len(documents) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(documents))
        batch_docs = documents[start:end]

        batch_embeddings = EmbeddingService.generate_embeddings(batch_docs)
        all_embeddings.extend(batch_embeddings)

        pct = int((batch_idx + 1) / total_batches * 100)
        bar = "#" * (pct // 5) + "." * (20 - pct // 5)
        print(f"  [{bar}] {pct:3d}%  Batch {batch_idx + 1}/{total_batches} "
              f"({end}/{len(documents)} chunks)", end="\r", flush=True)

    print()  # newline after progress bar
    stats["embed_duration_s"] = round(time.time() - t0, 2)
    stats["embeddings_generated"] = len(all_embeddings)
    print(f"  Embeddings      : {len(all_embeddings):,}")
    print(f"  Embed duration  : {stats['embed_duration_s']}s")

    # ── STEP 6: STORE IN CHROMA ───────────────────────────────────────────────
    _step(6, f"Storing vectors in Chroma [{settings.VECTOR_PROVIDER}]")
    t0 = time.time()
    VectorStore.create_collection(repo_id)

    total_batches_store = (len(documents) + BATCH_SIZE - 1) // BATCH_SIZE
    for batch_idx in range(total_batches_store):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(documents))

        VectorStore.insert_chunks(
            repo_id=repo_id,
            documents=documents[start:end],
            embeddings=all_embeddings[start:end],
            metadatas=metadatas[start:end]
        )
        stats["batches_uploaded"] += 1

        pct = int((batch_idx + 1) / total_batches_store * 100)
        bar = "#" * (pct // 5) + "." * (20 - pct // 5)
        print(f"  [{bar}] {pct:3d}%  Upload batch {batch_idx + 1}/{total_batches_store}", end="\r", flush=True)

    print()
    stats["store_duration_s"] = round(time.time() - t0, 2)
    print(f"  Store duration  : {stats['store_duration_s']}s")

    # ── FINAL STATS ───────────────────────────────────────────────────────────
    stats["total_duration_s"] = round(time.time() - start_total, 2)

    # Verify count in Chroma
    chroma_stats = VectorStore.repository_statistics(repo_id)
    stats["chroma_vector_count"] = chroma_stats.get("vector_count", "?")

    return stats


def print_summary(stats: dict) -> None:
    _sep("INDEXING COMPLETE")
    print(f"  Repo ID            : {stats['repo_id']}")
    print(f"  Repo Path          : {stats['repo_path']}")
    print(f"  Files Scanned      : {stats['files_scanned']:,}")
    print(f"  Entities Parsed    : {stats['entities_parsed']:,}")
    print(f"  Chunks Total       : {stats['chunks_total']:,}")
    print(f"  Chunks Indexed     : {stats['chunks_indexed']:,}")
    print(f"  Embeddings Created : {stats['embeddings_generated']:,}")
    print(f"  Batches Uploaded   : {stats['batches_uploaded']}")
    print(f"  Chroma Vector Count: {stats.get('chroma_vector_count', '?')}")
    print(f"  Scan Duration      : {stats['scan_duration_s']}s")
    print(f"  Embed Duration     : {stats['embed_duration_s']}s")
    print(f"  Store Duration     : {stats['store_duration_s']}s")
    print(f"  TOTAL Duration     : {stats['total_duration_s']}s")
    _sep()


def main():
    parser = argparse.ArgumentParser(
        description="Index a repository into Chroma for RAG retrieval."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--repo", choices=list(KNOWN_REPOS.keys()),
        help="Well-known repo name (fastapi | langchain | chroma)"
    )
    group.add_argument(
        "--path", type=Path,
        help="Absolute or relative path to a local repository directory"
    )
    parser.add_argument(
        "--id", dest="repo_id", type=str, default=None,
        help="Repo ID used as Chroma collection name. Defaults to <repo>_test."
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Cap the number of chunks to index (0 = no limit). Use for smoke tests."
    )
    args = parser.parse_args()

    # Resolve path and repo_id
    if args.repo:
        repo_path = KNOWN_REPOS[args.repo]
        repo_id = args.repo_id or DEFAULT_IDS[args.repo]
    else:
        repo_path = args.path.resolve()
        repo_id = args.repo_id or repo_path.name.replace("-", "_").replace(" ", "_")

    if not repo_path.exists():
        print(f"\n❌ ERROR: Repository path does not exist: {repo_path}")
        print(f"   Make sure to clone the repo first:\n")
        print(f"   git clone https://github.com/tiangolo/fastapi.git Repos/fastapi")
        sys.exit(1)

    _sep(f"RAG INDEXER — {repo_id.upper()}")
    print(f"  Provider   : {settings.VECTOR_PROVIDER}")
    print(f"  Embedding  : {settings.EMBEDDING_MODEL_NAME}")
    print(f"  Repo Path  : {repo_path}")
    print(f"  Repo ID    : {repo_id}")
    if args.limit:
        print(f"  Chunk Limit: {args.limit} (smoke-test mode)")
    _sep()

    stats = index_repository(repo_path, repo_id, chunk_limit=args.limit)
    print_summary(stats)

    if stats["errors"]:
        print("\n⚠  Errors encountered:")
        for e in stats["errors"]:
            print(f"   - {e}")


if __name__ == "__main__":
    main()
