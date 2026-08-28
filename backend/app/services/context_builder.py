import logging
import json
from typing import List, Dict, Any

from app.core.config import settings


class ContextBuilder:
    MAX_CONTEXT_CHARS = 24000  # Approx 6000 tokens context limit to avoid LLM context spillover

    @classmethod
    def assemble_repository_context(cls, retrieved_chunks: List[Dict[str, Any]]) -> str:
        """
        Aggregates chunks and formats them inside XML tags.

        Example Output:
        <repository_context>
          <file path="backend/auth.py">
            ...chunk content...
          </file>
        </repository_context>
        """
        # Group chunks by file to make it cleaner for the LLM
        file_chunks: Dict[str, List[str]] = {}
        for chunk in retrieved_chunks:
            meta = chunk["metadata"]
            file_path = meta.get("file_path", "unknown_file")
            doc_content = chunk["document"]

            symbol_name = meta.get("symbol_name", "")
            chunk_type = meta.get("chunk_type", "")
            distance = chunk.get("distance", 1.0)

            if file_path not in file_chunks:
                file_chunks[file_path] = []

            chunk_header = f"<!-- type: {chunk_type} | symbol: {symbol_name} | dist: {round(distance, 3)} -->\n"
            file_chunks[file_path].append(chunk_header + doc_content)

        # Assemble XML
        xml_parts = ["<repository_context>"]
        curr_chars = len(xml_parts[0])

        for path, contents in file_chunks.items():
            file_header = f'\n  <file path="{path}">'
            file_footer = '\n  </file>'

            combined_content = "\n\n  <!-- Chunk Boundary -->\n".join(contents)
            file_block = f"{file_header}\n{combined_content}{file_footer}"

            if curr_chars + len(file_block) > cls.MAX_CONTEXT_CHARS:
                remaining_space = cls.MAX_CONTEXT_CHARS - curr_chars - len(file_header) - len(file_footer) - 50
                if remaining_space > 100:
                    truncated_content = combined_content[:remaining_space] + "\n... [Context truncated due to size limits] ..."
                    file_block = f"{file_header}\n{truncated_content}{file_footer}"
                    xml_parts.append(file_block)
                    curr_chars += len(file_block)
                logging.warning("Context truncated to avoid context window overflow.")
                break
            else:
                xml_parts.append(file_block)
                curr_chars += len(file_block)

        xml_parts.append("\n</repository_context>")
        return "".join(xml_parts)

    @classmethod
    def format_sources(cls, retrieved_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Formats source anchors for API outputs.
        Includes language, chunk_type, and relevance score.
        """
        sources = []
        seen = set()
        for chunk in retrieved_chunks:
            meta      = chunk["metadata"]
            file_path = meta.get("file_path",  "unknown")
            start     = meta.get("start_line",  0)
            end       = meta.get("end_line",    0)
            distance  = float(chunk.get("distance", 1.0))
            score     = round(max(0.0, min(1.0, 1.0 - (distance / 2.0))), 4)

            key = (file_path, start, end)
            if key not in seen:
                seen.add(key)
                sources.append({
                    "file_path":  file_path,
                    "language":   meta.get("language",   ""),
                    "chunk_type": meta.get("chunk_type", ""),
                    "start_line": start,
                    "end_line":   end,
                    "score":      score,
                    "preview":    chunk["document"][:200] + "...",
                })
        return sources

    @classmethod
    def rank_chunks(cls, retrieved_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Legacy method — kept for backward compatibility.
        Delegates to RetrievalRanker.apply_weights() + diversify().
        """
        from app.services.retrieval_ranker import RetrievalRanker
        weighted  = RetrievalRanker.apply_weights(retrieved_chunks)
        diversified = RetrievalRanker.diversify(weighted, budget=len(retrieved_chunks))
        return diversified

    @classmethod
    def build_prompt_context(cls, query: str, retrieved_chunks: List[Dict[str, Any]]) -> str:
        """
        Builds the full LLM prompt with layered intelligence context:

          1. Repository Manifest (metadata header)
          2. Architecture Summary
          3. Engineering Quality Summary
          4. Security Findings Summary
          5. Retrieved Code Chunks (diversified & weighted)
          6. User Query
        """
        from app.services.retrieval_ranker import RetrievalRanker
        from app.services.repository_manifest import RepositoryManifest
        from app.services.architecture_analyzer import ArchitectureAnalyzer
        from app.services.engineering_quality import EngineeringQualityAnalyzer
        from app.services.security_analyzer import SecurityAnalyzer

        # ── Step 1: Apply retrieval diversity + weighting ─────────────────
        weighted    = RetrievalRanker.apply_weights(retrieved_chunks)
        diverse     = RetrievalRanker.diversify(weighted, budget=7)
        xml_context = cls.assemble_repository_context(diverse)

        # ── Step 2: Determine repo_id from chunks ─────────────────────────
        repo_id = None
        if diverse:
            repo_id = diverse[0].get("metadata", {}).get("repo_id") or \
                      diverse[0].get("metadata", {}).get("repository_id")
        if not repo_id and retrieved_chunks:
            repo_id = retrieved_chunks[0].get("metadata", {}).get("repo_id") or \
                      retrieved_chunks[0].get("metadata", {}).get("repository_id")

        # ── Step 3: Load intelligence context blocks ──────────────────────
        manifest_block  = ""
        arch_block      = ""
        quality_block   = ""
        security_block  = ""

        if repo_id:
            try:
                manifest = RepositoryManifest.load(repo_id)
                manifest_block = RepositoryManifest.format_for_prompt(manifest)
            except Exception as e:
                logging.debug(f"[ContextBuilder] Manifest load failed: {e}")

            try:
                arch_block = ArchitectureAnalyzer.format_for_prompt(repo_id)
            except Exception as e:
                logging.debug(f"[ContextBuilder] Architecture format failed: {e}")

            try:
                quality_block = EngineeringQualityAnalyzer.format_for_prompt(repo_id)
            except Exception as e:
                logging.debug(f"[ContextBuilder] Quality format failed: {e}")

            try:
                security_block = SecurityAnalyzer.format_for_prompt(repo_id)
            except Exception as e:
                logging.debug(f"[ContextBuilder] Security format failed: {e}")

        # ── Step 4: Assemble intelligence preamble ────────────────────────
        intelligence_blocks = []
        if manifest_block:
            intelligence_blocks.append(manifest_block)
        if arch_block:
            intelligence_blocks.append(arch_block)
        if quality_block:
            intelligence_blocks.append(quality_block)
        if security_block:
            intelligence_blocks.append(security_block)

        intelligence_preamble = "\n\n".join(intelligence_blocks)

        # ── Step 5: Build system prompt ───────────────────────────────────
        system_prompt = (
            "You are an expert repository analysis assistant and software engineering evaluator. "
            "You are given:\n"
            "  1. A repository intelligence summary (manifest, architecture, quality, security)\n"
            "  2. Retrieved code chunks from the repository\n"
            "  3. A user query\n\n"
            "Your task is to answer the query accurately and with technical precision.\n"
            "Guidelines:\n"
            "1. Be direct, technical, and precise. Avoid generalities.\n"
            "2. Cite specific files, class names, and function names when answering.\n"
            "3. Use the repository manifest and architecture summary to provide grounded answers.\n"
            "4. If the code context does not contain enough information, state it clearly.\n"
            "5. Do NOT make up or hallucinate code paths or configuration files.\n"
            "6. Always reference file paths as Markdown links, e.g., [auth.py](file:///src/auth.py#L1-L10).\n"
        )

        # ── Step 6: Assemble final prompt ─────────────────────────────────
        parts = [system_prompt]
        if intelligence_preamble:
            parts.append(
                "Here is the repository intelligence context:\n"
                f"{intelligence_preamble}"
            )
        parts.append(
            "Here is the context retrieved from the codebase:\n"
            f"{xml_context}"
        )
        parts.append(f"User Query: {query}\nAnswer:")

        final_prompt = "\n\n".join(parts)
        return final_prompt
