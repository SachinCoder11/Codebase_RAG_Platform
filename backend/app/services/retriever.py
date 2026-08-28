# backend/app/services/retriever.py
"""
RetrieverService — Phase 0 Extraction
======================================
Clean separation of the retrieval layer from the orchestration layer.

  Question
     ↓
  EmbeddingService.generate_query_embedding()
     ↓
  VectorStore.similarity_search()
     ↓
  List[RetrievedChunk]

Benefits over inlining in QueryEngine:
  - Independent unit testing
  - Retrieval benchmarking via validate_retrieval.py
  - Pluggable re-ranking without touching orchestration
  - Clean interface for Phase 0 validation (no LLM involved)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStore

logger = logging.getLogger("retriever_service")


@dataclass
class RetrievedChunk:
    """Structured representation of one retrieved vector chunk."""
    content:       str
    file_path:     str
    language:      str
    chunk_type:    str
    start_line:    int
    end_line:      int
    distance:      float
    class_name:    str = ""
    function_name: str = ""
    chunk_hash:    str = ""
    repository_id: str = ""
    repo_id:       str = ""
    framework:     str = ""
    symbol_name:   str = ""

    @property
    def relevance_score(self) -> float:
        """
        Convert Chroma cosine distance (0 = identical, higher = less similar)
        into a human-readable 0–1 relevance score.
        BGE distances are typically in [0, 1.5]; we clamp to [0, 1].
        """
        return round(max(0.0, min(1.0, 1.0 - (self.distance / 2.0))), 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content":       self.content,
            "file_path":     self.file_path,
            "language":      self.language,
            "chunk_type":    self.chunk_type,
            "start_line":    self.start_line,
            "end_line":      self.end_line,
            "distance":      self.distance,
            "score":         self.relevance_score,
            "class_name":    self.class_name,
            "function_name": self.function_name,
            "chunk_hash":    self.chunk_hash,
            "repository_id": self.repository_id,
            "repo_id":       self.repo_id,
            "framework":     self.framework,
            "symbol_name":   self.symbol_name,
        }


@dataclass
class RetrievalResult:
    """
    Full result bundle returned by RetrieverService.retrieve().
    Consumed by ContextBuilder and validate_retrieval.py.
    """
    query:           str
    repo_id:         str
    chunks:          List[RetrievedChunk]
    query_time_s:    float
    retrieved_files: List[str] = field(default_factory=list)

    def __post_init__(self):
        # Deduplicated ordered list of source files
        seen = set()
        files = []
        for c in self.chunks:
            if c.file_path not in seen:
                seen.add(c.file_path)
                files.append(c.file_path)
        self.retrieved_files = files

    @property
    def avg_distance(self) -> float:
        if not self.chunks:
            return 1.0
        return round(sum(c.distance for c in self.chunks) / len(self.chunks), 4)

    @property
    def avg_score(self) -> float:
        if not self.chunks:
            return 0.0
        return round(sum(c.relevance_score for c in self.chunks) / len(self.chunks), 4)


class RetrieverService:
    """
    Standalone retrieval layer.

    Usage:
        result = RetrieverService.retrieve(
            repo_id  = "fastapi_test",
            query    = "How are routes registered?",
            top_k    = 7,
        )
        for chunk in result.chunks:
            print(chunk.file_path, chunk.relevance_score)
    """

    @classmethod
    def retrieve(
        cls,
        repo_id:  str,
        query:    str,
        top_k:    int = 7,
        filters:  Optional[Dict[str, Any]] = None,
    ) -> RetrievalResult:
        """
        Execute the full retrieval flow without any LLM involvement.

        Args:
            repo_id:  Chroma collection name (e.g. "fastapi_test")
            query:    Natural language question
            top_k:    Number of chunks to retrieve
            filters:  Optional Chroma metadata filters e.g. {"language": "Python"}

        Returns:
            RetrievalResult containing ranked RetrievedChunk objects
        """
        t0 = time.time()

        # 1. Generate query embedding using BAAI/bge-small-en-v1.5
        logger.debug(f"[RetrieverService] Embedding query: '{query[:80]}'")
        query_embedding = EmbeddingService.generate_query_embedding(query)

        # 2. Similarity search in Chroma (cloud or local)
        raw_chunks = VectorStore.similarity_search(
            repo_id        = repo_id,
            query_embedding = query_embedding,
            top_k          = top_k,
            filters        = filters,
        )

        elapsed = round(time.time() - t0, 3)
        logger.info(
            f"[RetrieverService] repo={repo_id} query='{query[:60]}' "
            f"→ {len(raw_chunks)} chunks in {elapsed}s"
        )

        # 3. Map raw Chroma dicts → RetrievedChunk dataclasses
        chunks: List[RetrievedChunk] = []
        for raw in raw_chunks:
            meta = raw.get("metadata", {})
            chunks.append(RetrievedChunk(
                content       = raw.get("document", ""),
                file_path     = meta.get("file_path",     "unknown"),
                language      = meta.get("language",      ""),
                chunk_type    = meta.get("chunk_type",    "code"),
                start_line    = int(meta.get("start_line", 0)),
                end_line      = int(meta.get("end_line",   0)),
                distance      = float(raw.get("distance",  1.0)),
                class_name    = meta.get("class_name",    ""),
                function_name = meta.get("function_name", ""),
                chunk_hash    = meta.get("hash",          "")[:16],
                repository_id = meta.get("repository_id", repo_id),
                repo_id       = meta.get("repo_id", meta.get("repository_id", repo_id)),
                framework     = meta.get("framework",     ""),
                symbol_name   = meta.get("symbol_name",   ""),
            ))

        return RetrievalResult(
            query        = query,
            repo_id      = repo_id,
            chunks       = chunks,
            query_time_s = elapsed,
        )

    @classmethod
    def retrieve_raw(
        cls,
        repo_id: str,
        query:   str,
        top_k:   int = 7,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Backward-compatible method — returns the raw Chroma dict format
        that ContextBuilder and QueryEngine currently expect.

        Use retrieve() for new code. This method lets QueryEngine migrate
        to RetrieverService without changing ContextBuilder at this stage.
        """
        result = cls.retrieve(repo_id, query, top_k, filters)
        # Re-map to the dict shape that ContextBuilder.format_sources() expects
        raw = []
        for chunk in result.chunks:
            raw.append({
                "document": chunk.content,
                "metadata": {
                    "file_path":     chunk.file_path,
                    "language":      chunk.language,
                    "chunk_type":    chunk.chunk_type,
                    "start_line":    chunk.start_line,
                    "end_line":      chunk.end_line,
                    "class_name":    chunk.class_name,
                    "function_name": chunk.function_name,
                    "hash":          chunk.chunk_hash,
                    "repository_id": chunk.repository_id,
                    "repo_id":       chunk.repo_id,
                    "framework":     chunk.framework,
                    "symbol_name":   chunk.symbol_name,
                },
                "distance": chunk.distance,
            })
        return raw
