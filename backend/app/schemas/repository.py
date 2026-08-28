from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Any, Optional

class GitCloneRequest(BaseModel):
    url: str
    branch: Optional[str] = "main"

class RepositoryResponse(BaseModel):
    id: str
    name: str
    status: str
    progress: int
    message: str
    languages: Optional[Dict[str, float]] = None
    frameworks: Optional[List[str]] = None
    file_count: Optional[int] = None
    total_lines: Optional[int] = None
    chunk_count: Optional[int] = None
