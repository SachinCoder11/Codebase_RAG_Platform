import logging
import json
import time
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from app.schemas.query import QueryRequest, QueryResponse, SourceResponse
from app.services.query_engine import QueryEngine
from app.services.llm_orchestrator import LLMOrchestrator

router = APIRouter()
logger = logging.getLogger("query_endpoint")


@router.post("", response_model=QueryResponse)
def execute_query(request: QueryRequest):
    """
    Executes a semantic similarity search and queries the local LLM
    with retrieved repository context.

    Accepts both ``repo_id`` (spec) and ``repository_id`` (legacy) field names.
    """
    repo_id = request.resolved_repo_id
    question = (request.query or "").strip()

    if not repo_id or not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both 'repo_id' (or 'repository_id') and 'query' are required."
        )

    try:
        logger.info(f"Query request — repo={repo_id}: '{question[:80]}'")

        result = QueryEngine.execute_rag_flow(
            repo_id = repo_id,
            query   = question,
            top_k   = request.top_k or 7,
            filters = request.filters,
        )

        # Map raw sources → SourceResponse (add language, chunk_type, score)
        enriched_sources = []
        for src in result.get("sources", []):
            enriched_sources.append(SourceResponse(
                file_path  = src.get("file_path", ""),
                language   = src.get("language",  ""),
                chunk_type = src.get("chunk_type", ""),
                start_line = src.get("start_line", 0),
                end_line   = src.get("end_line",   0),
                score      = src.get("score",      0.0),
                preview    = src.get("preview",    ""),
            ))

        return QueryResponse(
            answer             = result["answer"],
            confidence_score   = result["confidence_score"],
            sources            = enriched_sources,
            retrieved_files    = result.get("retrieved_files", []),
            time_taken_seconds = result.get("time_taken_seconds", 0.0),
            debug_info         = result.get("debug_info"),
        )

    except Exception as e:
        logger.error(f"Query failed for repo={repo_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {str(e)}"
        )


@router.post("/stream")
def execute_query_stream(request: QueryRequest):
    """
    Stream response token-by-token.
    Falls back gracefully if streaming is not fully consumed or supported.
    """
    repo_id = request.resolved_repo_id
    question = (request.query or "").strip()

    if not repo_id or not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both 'repo_id' (or 'repository_id') and 'query' are required."
        )

    try:
        t0 = time.time()
        # Retrieve chunks (no LLM yet)
        from app.services.retriever import RetrieverService
        from app.services.context_builder import ContextBuilder
        
        chunks = RetrieverService.retrieve_raw(
            repo_id = repo_id,
            query   = question,
            top_k   = request.top_k or 7,
            filters = request.filters,
        )
        
        sources = ContextBuilder.format_sources(chunks)
        xml_context   = ContextBuilder.assemble_repository_context(chunks)
        final_prompt  = ContextBuilder.build_prompt_context(question, chunks)
        
        retrieved_files = list(dict.fromkeys(
            c["metadata"].get("file_path", "") for c in chunks
            if c["metadata"].get("file_path")
        ))
        
        avg_distance = sum(c.get("distance", 0.5) for c in chunks) / len(chunks) if chunks else 1.0
        confidence = max(0.1, min(0.99, round(1.0 - (avg_distance / 2.0), 2)))
        
        # Build initial packet with sources, files, confidence, debug_info
        from app.core.config import settings
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
                    "avg_distance": round(avg_distance, 4),
                },
                "latency": {
                    "total_seconds": 0.0 # Will update at completion
                },
                "model_info": model_info
            }

        meta_payload = {
            "type": "meta",
            "sources": sources,
            "retrieved_files": retrieved_files,
            "confidence_score": confidence,
            "debug_info": debug_info
        }
        
        # Stream generator
        def event_generator():
            # 1. Send meta information first
            yield f"data: {json.dumps(meta_payload)}\n\n"
            
            # 2. Start LLM stream
            stream = LLMOrchestrator.generate_answer_stream(final_prompt)
            for token in stream:
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            
            # 3. Send final done signal with final elapsed time
            elapsed = round(time.time() - t0, 2)
            yield f"data: {json.dumps({'type': 'done', 'time_taken_seconds': elapsed})}\n\n"
            
        return StreamingResponse(event_generator(), media_type="text/event-stream")
        
    except Exception as e:
        logger.error(f"Stream Query failed for repo={repo_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Streaming query failed: {str(e)}"
        )
