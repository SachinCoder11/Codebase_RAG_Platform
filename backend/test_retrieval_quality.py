import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend root is in PYTHONPATH
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.retriever import RetrieverService

def run_tests():
    load_dotenv(backend_dir / ".env")
    
    # We will assume a mock/test repo or an existing one. Let's use "fastapi" as a sample if it exists.
    # We'll just run it against whatever default or mock we can. If the user hasn't processed one, it might be empty.
    # Here we hardcode to use 'repo_RAGDATA' indirectly via the Provider.
    # For testing, we need a repo_id that might exist, or just use a generic query to see the system.
    # The user has likely indexed a repo or we can test against "test_repo".
    repo_id = "test_repo" 
    
    queries = [
        "Where are the routes registered?",
        "How does authentication work?",
        "Show me the database connection services."
    ]
    
    report_lines = [
        "# Retrieval Quality Diagnostic Report\n",
        "This report demonstrates the new retrieval diagnostics and context quality after the Universal Chunking Upgrade.\n"
    ]
    
    for query in queries:
        report_lines.append(f"## Query: `{query}`\n")
        try:
            result = RetrieverService.retrieve(repo_id=repo_id, query=query, top_k=3)
            report_lines.append(f"**Query Time:** {result.query_time_s}s\n")
            
            if not result.chunks:
                report_lines.append("> No chunks retrieved. (Database might be empty for this repo_id).\n")
            
            for i, chunk in enumerate(result.chunks, 1):
                report_lines.append(f"### Chunk {i}")
                report_lines.append(f"- **File:** `{chunk.file_path}`")
                report_lines.append(f"- **Type:** `{chunk.chunk_type}`")
                report_lines.append(f"- **Similarity Score:** `{chunk.relevance_score}` (Distance: `{chunk.distance}`)")
                report_lines.append(f"- **Framework:** `{chunk.framework}`")
                report_lines.append(f"- **Symbol:** `{chunk.symbol_name}`")
                report_lines.append("\n**Preview:**")
                report_lines.append("```")
                report_lines.append(chunk.content[:250] + "...")
                report_lines.append("```\n")
                
        except Exception as e:
            report_lines.append(f"**Error executing retrieval:** {str(e)}\n")
            
    # Write report
    report_path = backend_dir / "RETRIEVAL_QUALITY_REPORT.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    print(f"Report written to {report_path}")

if __name__ == "__main__":
    run_tests()
