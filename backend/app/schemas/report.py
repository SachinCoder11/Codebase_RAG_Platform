from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class ReportMetrics(BaseModel):
    total_files: int
    total_lines: int
    avg_complexity_index: float

class SecretFinding(BaseModel):
    file_path: str
    line: int
    issue: str
    match: str
    severity: str

class ReportResponse(BaseModel):
    repository_id: str
    architecture_score: int
    security_score: int
    maintainability_score: int
    complexity_score: int
    metrics: ReportMetrics
    secrets_leakages: List[SecretFinding]
    dependencies_count: int
    dependencies_list: List[str]
    architecture_analysis: str
    security_analysis: str
    suggestions: List[str]
