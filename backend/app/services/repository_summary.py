from pathlib import Path
from typing import Dict, List, Any
from app.services.parser.dependency_extractor import DependencyExtractor
from app.core.config import settings

class RepositorySummaryService:
    @classmethod
    def generate_summary(
        cls,
        repo_id: str,
        scan_results: Dict[str, Any],
        entities: List[Dict[str, Any]],
        chunks_with_metadata: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Creates repository-level analytics immediately after vector indexing completes.
        """
        # Count classes and functions
        class_count = sum(1 for e in entities if e["type"] == "class")
        function_count = sum(1 for e in entities if e["type"] in ["function", "method"])
        
        # Load workspace path to extract project dependencies
        workspace_path = settings.WORKSPACES_DIR / repo_id
        dependencies = []
        if workspace_path.exists():
            dependencies = DependencyExtractor.extract_all(workspace_path)

        # Assemble summary
        summary = {
            "repository_id": repo_id,
            "languages": scan_results.get("languages", {}),
            "frameworks": scan_results.get("frameworks", []),
            "file_count": scan_results.get("file_count", 0),
            "total_lines": scan_results.get("total_lines", 0),
            "class_count": class_count,
            "function_count": function_count,
            "dependency_count": len(dependencies),
            "dependencies": dependencies,
            "chunk_count": len(chunks_with_metadata)
        }
        
        return summary
