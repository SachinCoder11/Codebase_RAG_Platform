import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.core.config import settings

# Global in-memory status dictionary to trace background job progress
processing_status: Dict[str, Dict[str, Any]] = {}

class RepositoryProcessor:
    @staticmethod
    def update_processing_status(repo_id: str, status: str, progress: int, message: str, details: Dict = None):
        """Updates the global status log for a specific repository process."""
        processing_status[repo_id] = {
            "status":     status,      # "pending", "processing", "completed", "failed"
            "progress":   progress,    # 0 to 100
            "message":    message,
            "updated_at": time.time(),
            "details":    details or {}
        }
        logging.info(f"[{repo_id}] Progress {progress}%: {message}")

    @classmethod
    def get_status(cls, repo_id: str) -> Dict[str, Any]:
        """Retrieves current processing status."""
        return processing_status.get(repo_id, {
            "status":     "unknown",
            "progress":   0,
            "message":    "Repository execution record not found",
            "updated_at": time.time(),
            "details":    {}
        })

    @classmethod
    async def process_repository(
        cls,
        repo_id: str,
        repo_name: str,
        workspace_path: Path,
        identity: Optional[Dict[str, Any]] = None,
    ):
        """
        Asynchronously runs the complete Repository Intelligence pipeline.

        Phase 1 (Indexing) — skipped if vectors already exist:
          10% Scan files
          25% AST extraction
          45% Chunking
          60% Metadata building
          75% Embedding
          85% Chroma storage

        Phase 2 (Intelligence) — always runs:
          87% Architecture analysis (expanded)
          89% Repository manifest
          91% Engineering quality evaluation
          93% Security analysis
          95% Git activity (GitHub repos only)
          97% Persist to SQLite + disk
          100% Complete
        """
        from app.services.repository_scanner import RepositoryScanner
        from app.services.parser.analyzer import CodeParserAnalyzer
        from app.services.architecture_analyzer import ArchitectureAnalyzer
        from app.services.universal_chunking import UniversalChunkingEngine
        from app.services.metadata_builder import MetadataBuilder
        from app.services.embedding import EmbeddingService
        from app.services.vector_store import VectorStore
        from app.services.repository_summary import RepositorySummaryService
        from app.services.repository_manifest import RepositoryManifest
        from app.services.engineering_quality import EngineeringQualityAnalyzer
        from app.services.security_analyzer import SecurityAnalyzer
        from app.services.git_activity import GitActivityService
        from app.models.repository import RepositoryModel

        try:
            # ── Resolve identity ───────────────────────────────────────────────
            if not identity:
                identity = {
                    "repo_id":    repo_id,
                    "repo_name":  repo_name,
                    "owner":      "local",
                    "source_type":"zip",
                    "source_url": ""
                }
            effective_repo_id   = identity.get("repo_id", repo_id)
            effective_repo_name = identity.get("repo_name", repo_name)
            effective_owner     = identity.get("owner", "local")
            effective_source    = identity.get("source_type", "zip")

            # ── Phase 1: Check if already indexed (skip re-embedding) ──────────
            existing_stats = VectorStore.repository_statistics(effective_repo_id)
            already_indexed = existing_stats.get("vector_count", 0) > 0

            if already_indexed:
                cls.update_processing_status(
                    repo_id, "processing", 20,
                    f"Repository already indexed ({existing_stats['vector_count']} vectors). "
                    "Skipping embedding. Regenerating intelligence reports..."
                )
                # Still need scan + entities for intelligence phase
                scan_results = RepositoryScanner.scan_repository(workspace_path)
                entities = CodeParserAnalyzer.analyze_workspace(workspace_path, scan_results["indexed_files"])
                chunks_with_metadata = []  # not needed for intelligence phase
            else:
                # ── Full indexing pipeline ─────────────────────────────────────
                cls.update_processing_status(repo_id, "processing", 10, "Scanning files in codebase...")
                scan_results = RepositoryScanner.scan_repository(workspace_path)
                file_count   = scan_results["file_count"]
                cls.update_processing_status(
                    repo_id, "processing", 25,
                    f"Discovered {file_count} files. Extracting AST entities...",
                    details=scan_results
                )

                entities = CodeParserAnalyzer.analyze_workspace(workspace_path, scan_results["indexed_files"])
                cls.update_processing_status(
                    repo_id, "processing", 45,
                    f"AST extraction complete: {len(entities)} structures. Chunking..."
                )

                chunks = UniversalChunkingEngine.chunk_entities(workspace_path, entities)
                cls.update_processing_status(
                    repo_id, "processing", 60,
                    f"Created {len(chunks)} chunks. Building metadata..."
                )

                framework_val = scan_results.get("frameworks", [""])[0] if scan_results.get("frameworks") else ""

                chunks_with_metadata = []
                for chunk in chunks:
                    metadata = MetadataBuilder.build_metadata(
                        repo_id       = effective_repo_id,
                        repo_name     = effective_repo_name,
                        owner         = effective_owner,
                        source_type   = effective_source,
                        file_path     = chunk["file_path"],
                        language      = chunk["language"],
                        chunk_type    = chunk["chunk_type"],
                        framework     = framework_val,
                        class_name    = chunk.get("class_name"),
                        function_name = chunk.get("function_name"),
                        start_line    = chunk["start_line"],
                        end_line      = chunk["end_line"],
                        dependencies  = chunk.get("dependencies", []),
                        content       = chunk["content"]
                    )
                    chunks_with_metadata.append({
                        "content":  chunk["content"],
                        "metadata": metadata
                    })

                cls.update_processing_status(
                    repo_id, "processing", 75,
                    "Metadata built. Generating embeddings..."
                )

                documents = [c["content"]  for c in chunks_with_metadata]
                metadatas = [c["metadata"] for c in chunks_with_metadata]

                if documents:
                    embeddings = EmbeddingService.generate_embeddings(documents)
                    cls.update_processing_status(repo_id, "processing", 85, "Storing vectors in Chroma Cloud...")
                    VectorStore.insert_chunks(
                        repo_id    = effective_repo_id,
                        documents  = documents,
                        embeddings = embeddings,
                        metadatas  = metadatas
                    )
                else:
                    cls.update_processing_status(repo_id, "processing", 85, "No code files found. Skipping Chroma.")

            # ── Phase 2: Intelligence Engine ────────────────────────────────────

            # 87% — Architecture analysis (expanded)
            cls.update_processing_status(repo_id, "processing", 87, "Analyzing repository architecture...")
            architecture_summary = ArchitectureAnalyzer.analyze(workspace_path, entities)

            # 89% — Repository manifest
            cls.update_processing_status(repo_id, "processing", 89, "Generating repository manifest...")
            manifest = RepositoryManifest.generate(
                repo_id       = effective_repo_id,
                repo_name     = effective_repo_name,
                owner         = effective_owner,
                source_type   = effective_source,
                scan_results  = scan_results,
                entities      = entities,
                workspace_path= workspace_path,
            )

            # 91% — Engineering quality
            cls.update_processing_status(repo_id, "processing", 91, "Evaluating engineering quality...")
            # Security must run first so quality can use the score
            security_findings = SecurityAnalyzer.scan(workspace_path)
            security_score    = SecurityAnalyzer.score(security_findings)
            SecurityAnalyzer.write_report(effective_repo_id, security_findings, security_score)

            quality_result = EngineeringQualityAnalyzer.evaluate(
                repo_id       = effective_repo_id,
                workspace_path= workspace_path,
                scan_results  = scan_results,
                entities      = entities,
                security_score= security_score,
            )

            # 93% — Git activity (only for GitHub-sourced repos)
            cls.update_processing_status(repo_id, "processing", 93, "Fetching repository activity...")
            if effective_source == "github":
                activity = GitActivityService.fetch(effective_owner, effective_repo_name)
                GitActivityService.write_report(effective_repo_id, activity)
            else:
                GitActivityService.write_report(effective_repo_id, {})
            # 94% — Dependencies & Licenses
            cls.update_processing_status(repo_id, "processing", 94, "Analyzing dependencies and licenses...")
            from app.services.dependency_analyzer import DependencyAnalyzer
            from app.services.license_analyzer import LicenseAnalyzer
            dependency_data = DependencyAnalyzer.analyze(workspace_path, effective_repo_id)
            license_data = LicenseAnalyzer.analyze(workspace_path, effective_repo_id)

            # 94.5% - Modern Codebase
            cls.update_processing_status(repo_id, "processing", 94, "Evaluating modern codebase compliance...")
            from app.services.modern_codebase_evaluator import ModernCodebaseEvaluator
            # We fetch activity manually here if not github to pass to evaluator
            git_data = activity if effective_source == "github" else {}
            security_summary = {"score": security_score, "findings": len(security_findings)}
            
            modern_result = ModernCodebaseEvaluator.evaluate(
                repo_id=effective_repo_id,
                workspace_path=workspace_path,
                summary_data={},
                security_data=security_summary,
                quality_data=quality_result,
                dependency_data=dependency_data,
                git_data=git_data,
                arch_data=architecture_summary
            )

            # 95% — Summary + save everything
            cls.update_processing_status(repo_id, "processing", 95, "Generating summary metrics...")
            summary = RepositorySummaryService.generate_summary(
                effective_repo_id, scan_results, entities,
                chunks_with_metadata if not already_indexed else []
            )
            summary["architecture"] = architecture_summary
            summary["manifest"]     = manifest
            summary["quality"]      = quality_result
            summary["modern"]       = modern_result

            summary_path = settings.REPORTS_DIR / effective_repo_id / "summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            import json
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)

            # 97% — Persist to SQLite
            cls.update_processing_status(repo_id, "processing", 97, "Updating registry...")
            RepositoryModel.upsert(
                repo_id     = effective_repo_id,
                repo_name   = effective_repo_name,
                owner       = effective_owner,
                source_type = effective_source,
                source_url  = identity.get("source_url", "")
            )
            if not already_indexed:
                RepositoryModel.update_counts(
                    repo_id     = effective_repo_id,
                    chunk_count = len(chunks_with_metadata),
                    vector_count= len(chunks_with_metadata) if not already_indexed else existing_stats.get("vector_count", 0)
                )
            RepositoryModel.update_manifest(effective_repo_id, manifest)
            RepositoryModel.update_quality_score(effective_repo_id, quality_result.get("overall", 0))

            # ── Complete ───────────────────────────────────────────────────────
            cls.update_processing_status(
                repo_id, "completed", 100,
                "Repository intelligence pipeline complete!",
                details={"summary": summary, "quality_score": quality_result.get("overall", 0)}
            )

        except Exception as e:
            cls.update_processing_status(repo_id, "failed", 100, f"Error: {str(e)}")
            logging.error(f"Repository processor error for '{repo_id}': {str(e)}", exc_info=True)
