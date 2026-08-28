# backend/test_context_quality.py
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend root is in PYTHONPATH
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(backend_dir / ".env")

from app.core.config import settings
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStore
from app.services.context_builder import ContextBuilder
from app.services.llm_orchestrator import LLMOrchestrator

def test_context_quality():
    repo_id = "fastapi_test"
    queries = [
        "Explain project architecture",
        "Where is database configuration located?",
        "What authentication mechanism is used?",
        "Are there security vulnerabilities?",
        "List API routes"
    ]
    
    report_lines = []
    report_lines.append("# Context Quality Validation Report")
    report_lines.append(f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Target Repository ID: `{repo_id}`\n")
    
    for i, query in enumerate(queries, 1):
        report_lines.append(f"## {i}. Query: `{query}`\n")
        
        # Retrieval
        t_start = time.time()
        query_embedding = EmbeddingService.generate_query_embedding(query)
        chunks = VectorStore.similarity_search(
            repo_id=repo_id,
            query_embedding=query_embedding,
            top_k=7
        )
        t_retrieval = time.time() - t_start
        
        report_lines.append(f"**Retrieval Time:** `{t_retrieval:.4f}s`")
        report_lines.append(f"**Retrieved Chunks:** `{len(chunks)}`\n")
        
        if chunks:
            report_lines.append("### Retrieved Files & Symbols")
            for idx, chunk in enumerate(chunks, 1):
                meta = chunk.get("metadata", {})
                file_path = meta.get("file_path", "unknown")
                symbol = meta.get("symbol_name", "")
                distance = chunk.get("distance", 1.0)
                score = 1.0 - (distance / 2.0)
                symbol_text = f" (Symbol: `{symbol}`)" if symbol else ""
                report_lines.append(f"- {idx}. `{file_path}`{symbol_text} - Score: `{score:.4f}`")
            report_lines.append("\n")
        
        # Generation
        prompt = ContextBuilder.build_prompt_context(query, chunks)
        try:
            t_start = time.time()
            answer = LLMOrchestrator.generate_answer(prompt)
            t_gen = time.time() - t_start
            report_lines.append(f"**Generation Time:** `{t_gen:.4f}s`\n")
            report_lines.append("### Final Answer")
            report_lines.append(answer)
            report_lines.append("\n---\n")
        except Exception as e:
            report_lines.append(f"**Error generating answer:** `{str(e)}`\n---\n")
            
    # Write report
    report_path = backend_dir.parent / "CONTEXT_QUALITY_REPORT.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"Context quality validation complete. Report written to {report_path}")

if __name__ == "__main__":
    test_context_quality()
