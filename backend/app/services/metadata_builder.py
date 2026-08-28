import hashlib
import json
from typing import List, Dict, Any

class MetadataBuilder:
    @staticmethod
    def generate_chunk_hash(content: str) -> str:
        """
        Generates a SHA-256 hash of the chunk content.
        """
        return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()

    @classmethod
    def build_metadata(
        cls,
        repo_id: str,
        repo_name: str,
        owner: str,
        source_type: str,
        file_path: str,
        language: str,
        chunk_type: str,
        framework: str = "",
        symbol_name: str = "",
        class_name: str = None,
        function_name: str = None,
        start_line: int = 0,
        end_line: int = 0,
        dependencies: List[str] = None,
        content: str = ""
    ) -> Dict[str, Any]:
        """
        Builds standardized metadata.
        Serializes complex structures like lists to primitives (comma-separated strings)
        for ChromaDB compatibility.
        """
        deps_list = dependencies or []
        
        if not symbol_name:
            if function_name and class_name:
                symbol_name = f"{class_name}.{function_name}"
            elif function_name:
                symbol_name = function_name
            elif class_name:
                symbol_name = class_name
            else:
                symbol_name = ""

        metadata = {
            "repo_id": repo_id,
            "repo_name": repo_name,
            "owner": owner,
            "source_type": source_type,
            "file_path": file_path,
            "file_name": file_path.split("/")[-1] if "/" in file_path else file_path.split("\\")[-1],
            "chunk_type": chunk_type,
            "language": language,
            "framework": framework,
            "symbol_name": symbol_name,
            
            # Legacy fields for backward compatibility
            "repository_id": repo_id,
            "class_name": class_name or "",
            "function_name": function_name or "",
            "start_line": start_line,
            "end_line": end_line,
            "dependencies": ",".join(deps_list),
            "hash": cls.generate_chunk_hash(content)
        }
        
        return metadata
        
    @staticmethod
    def normalize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Restores list types from serialized string format in metadata when reading back.
        """
        normalized = dict(metadata)
        if "dependencies" in normalized and isinstance(normalized["dependencies"], str):
            deps_str = normalized["dependencies"]
            normalized["dependencies"] = deps_str.split(",") if deps_str else []
        return normalized
