import os
import json
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import FileResponse, Response
from app.core.config import settings
from app.services.report_generator import ReportGenerator
from app.services.repository_scanner import RepositoryScanner
from app.schemas.report import ReportResponse

router = APIRouter()

@router.get("/{id}/analysis", response_model=ReportResponse)
def get_report_analysis(id: str):
    """
    Retrieves or dynamically compiles the complete codebase analysis report.
    """
    report_json_path = settings.REPORTS_DIR / id / "report.json"
    
    # If the report is cached, return it
    if report_json_path.exists():
        try:
            with open(report_json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
            
    # Otherwise, check if workspace exists to trigger generation
    workspace_path = settings.WORKSPACES_DIR / id
    if not workspace_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository workspace files not found. Upload or clone the repo first."
        )

    try:
        # Scan workspace first to get languages/frameworks context
        scan_results = RepositoryScanner.scan_repository(workspace_path)
        
        # Compile full report
        report_data = ReportGenerator.generate_full_report(id, scan_results)
        return report_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate report audit: {str(e)}"
        )

@router.get("/{id}/export")
def export_report_file(id: str, format: str = Query("markdown", enum=["markdown", "json"])):
    """
    Downloads the compiled code audit report in Markdown or JSON format.
    """
    report_dir = settings.REPORTS_DIR / id
    
    # Check if analysis has run, trigger it if not
    report_json_path = report_dir / "report.json"
    if not report_json_path.exists():
        workspace_path = settings.WORKSPACES_DIR / id
        if not workspace_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace doesn't exist"
            )
        try:
            scan_results = RepositoryScanner.scan_repository(workspace_path)
            ReportGenerator.generate_full_report(id, scan_results)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error compiling report: {str(e)}"
            )

    if format == "json":
        file_path = report_dir / "report.json"
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="JSON report file not found")
        return FileResponse(
            path=file_path,
            media_type="application/json",
            filename=f"repository_report_{id[:8]}.json"
        )
    else:
        file_path = report_dir / "report.md"
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Markdown report file not found")
        return FileResponse(
            path=file_path,
            media_type="text/markdown",
            filename=f"repository_report_{id[:8]}.md"
        )
