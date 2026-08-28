# backend/app/services/query_engine.py
"""
QueryEngine — Full RAG Orchestration
======================================
Flow:
  Question
     ↓  RetrieverService (embed → Chroma search)
     ↓  ContextBuilder   (assemble XML prompt)
     ↓  LLMOrchestrator  (Ollama / OpenRouter)
     ↓  Answer + Sources + retrieved_files

RetrieverService is now used for the retrieval step so that:
  - validate_retrieval.py can benchmark retrieval independently
  - Retrieval can be tested without touching LLM code
  - Architecture matches the documented flow
"""

import time
import logging
from typing import Dict, Any, Optional

from app.services.retriever import RetrieverService
from app.services.context_builder import ContextBuilder
from app.services.llm_orchestrator import LLMOrchestrator
from app.core.config import settings

# Dedicated debugger logger → logs/rag_debug.log
rag_logger = logging.getLogger("rag_debugger")
rag_logger.setLevel(logging.DEBUG)

if not rag_logger.handlers:
    fh = logging.FileHandler(settings.LOG_FILE, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    fh.setFormatter(formatter)
    rag_logger.addHandler(fh)


class QueryEngine:

    @classmethod
    def execute_rag_flow(
        cls,
        repo_id:  str,
        query:    str,
        top_k:    int = 7,
        filters:  Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes the full RAG pipeline:
          Query → RetrieverService → ContextBuilder → LLM → Output

        Returns:
            {
              "answer":              str,
              "confidence_score":    float,
              "sources":             List[SourceDict],
              "retrieved_files":     List[str],
              "time_taken_seconds":  float,
            }
        """
        start_time = time.time()

        # ── 1. Retrieve (embed + Chroma search) via RetrieverService ─────────
        # Using retrieve_raw() for backward-compat with ContextBuilder dict format
        chunks = RetrieverService.retrieve_raw(
            repo_id = repo_id,
            query   = query,
            top_k   = top_k,
            filters = filters,
        )

        # ── 2. Build structured sources + XML context + final prompt ─────────
        sources       = ContextBuilder.format_sources(chunks)
        xml_context   = ContextBuilder.assemble_repository_context(chunks)
        final_prompt  = ContextBuilder.build_prompt_context(query, chunks)

        # Collect unique retrieved file paths for the response
        retrieved_files = list(dict.fromkeys(
            c["metadata"].get("file_path", "") for c in chunks
            if c["metadata"].get("file_path")
        ))

        # ── 3. Debug logging ─────────────────────────────────────────────────
        rag_logger.info("=" * 80)
        rag_logger.info(f"USER QUERY: {query}")
        rag_logger.info(f"RETRIEVED CHUNKS COUNT: {len(chunks)}")
        rag_logger.info(f"RETRIEVED FILES: {retrieved_files}")
        for i, c in enumerate(chunks):
            rag_logger.debug(
                f"Chunk {i+1} (dist={c.get('distance'):.4f}) "
                f"file={c['metadata'].get('file_path')} "
                f"type={c['metadata'].get('chunk_type')}\n{c['document'][:300]}"
            )
        rag_logger.debug(f"XML CONTEXT:\n{xml_context}")
        rag_logger.debug(f"FINAL PROMPT:\n{final_prompt}")

        # ── 4. LLM Inference via LLMOrchestrator ────────────────────────────
        answer = LLMOrchestrator.generate_answer(final_prompt)

        rag_logger.info(f"LLM ANSWER:\n{answer}")
        rag_logger.info("=" * 80)

        # ── 5. Compute confidence from avg Chroma distance ───────────────────
        elapsed    = time.time() - start_time
        confidence = 0.90
        if chunks:
            avg_distance = sum(c.get("distance", 0.5) for c in chunks) / len(chunks)
            confidence   = max(0.1, min(0.99, round(1.0 - (avg_distance / 2.0), 2)))

        # ── 6. Assemble debug info if configured ─────────────────────────────
        debug_info = None
        if settings.DEBUG_RAG:
            from app.services.providers.factory import ProviderFactory
            try:
                model_info = ProviderFactory.get_llm().get_model_info()
            except Exception as e:
                model_info = {"error": f"Failed to get model info: {str(e)}"}

            debug_info = {
                "retrieved_chunks": [
                    {
                        "file_path": c["metadata"].get("file_path", "unknown"),
                        "start_line": c["metadata"].get("start_line", 0),
                        "end_line": c["metadata"].get("end_line", 0),
                        "distance": round(c.get("distance", 0.5), 4),
                        "preview": c["document"][:200] + "..." if len(c["document"]) > 200 else c["document"]
                    }
                    for c in chunks
                ],
                "context": xml_context,
                "vector_results": {
                    "total_retrieved": len(chunks),
                    "avg_distance": round(sum(c.get("distance", 0.5) for c in chunks) / len(chunks), 4) if chunks else 1.0,
                },
                "latency": {
                    "total_seconds": round(elapsed, 2),
                },
                "model_info": model_info
            }

        return {
            "answer":             answer,
            "confidence_score":   confidence,
            "sources":            sources,
            "retrieved_files":    retrieved_files,
            "time_taken_seconds": round(elapsed, 2),
            "debug_info":         debug_info,
        }
