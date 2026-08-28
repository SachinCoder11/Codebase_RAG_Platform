from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class QueryRequest(BaseModel):
    # Accept both field names: "repository_id" (legacy) and "repo_id" (spec)
    repository_id: Optional[str] = Field(None, description="Repository ID (legacy field name)")
    repo_id:       Optional[str] = Field(None, description="Repository ID (spec field name)")
    query:         str
    model:         Optional[str] = None          # reserved for future model switching
    top_k:         Optional[int] = 7
    filters:       Optional[Dict[str, Any]] = None

    @property
    def resolved_repo_id(self) -> str:
        """Returns whichever of repo_id / repository_id was provided."""
        return self.repo_id or self.repository_id or ""


class SourceResponse(BaseModel):
    file_path:     str
    language:      str = ""
    chunk_type:    str = ""
    start_line:    int
    end_line:      int
    score:         float = 0.0      # 0–1 relevance score (1 = perfect match)
    preview:       str


class QueryResponse(BaseModel):
    answer:             str
    confidence_score:   float
    sources:            List[SourceResponse]
    retrieved_files:    List[str] = Field(default_factory=list)
    time_taken_seconds: Optional[float] = 0.0
    debug_info:         Optional[Dict[str, Any]] = None

