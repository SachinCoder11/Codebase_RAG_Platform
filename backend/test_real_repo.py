from pathlib import Path

from app.services.repository_scanner import RepositoryScanner
from app.services.parser.analyzer import CodeParserAnalyzer
from app.services.chunker import Chunker

workspace = Path("../Repos/fastapi")

scan_results = RepositoryScanner.scan_repository(workspace)

entities = CodeParserAnalyzer.analyze_workspace(
    workspace,
    scan_results["indexed_files"]
)

chunks = Chunker.chunk_entities(
    workspace,
    entities
)

print("FILES:", scan_results["file_count"])
print("ENTITIES:", len(entities))
print("CHUNKS:", len(chunks))

print("\nFIRST CHUNK:\n")
print(chunks[0])