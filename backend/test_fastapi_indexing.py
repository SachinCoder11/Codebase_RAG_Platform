from pathlib import Path
from time import time

from app.services.providers.factory import ProviderFactory
from app.services.metadata_builder import MetadataBuilder
from app.services.repository_scanner import RepositoryScanner
from app.services.parser.analyzer import CodeParserAnalyzer
from app.services.chunker import Chunker
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStore

REPO_ID = "RAGDATA"

start_time = time()

print("=" * 60)
print("FASTAPI FULL REPOSITORY INGESTION")
print("=" * 60)

print(
    f"Vector Provider: "
    f"{type(ProviderFactory.get_vector_store()).__name__}"
)

workspace = Path("../Repos/langchain")

# ==================================================

# STEP 1: SCAN

# ==================================================

print("\n" + "=" * 60)
print("STEP 1: SCANNING REPOSITORY")
print("=" * 60)

scan_results = RepositoryScanner.scan_repository(workspace)

print(f"Files Found: {scan_results['file_count']}")

# ==================================================

# STEP 2: ANALYZE

# ==================================================

print("\n" + "=" * 60)
print("STEP 2: ANALYZING")
print("=" * 60)

entities = CodeParserAnalyzer.analyze_workspace(
workspace,
scan_results["indexed_files"]
)

print(f"Entities Parsed: {len(entities)}")

# ==================================================

# STEP 3: CHUNK

# ==================================================

print("\n" + "=" * 60)
print("STEP 3: CHUNKING")
print("=" * 60)

chunks = Chunker.chunk_entities(
workspace,
entities
)

total_chunks = len(chunks)

print(f"Chunks Generated: {total_chunks}")

# NO LIMIT

# uploads everything generated

# ==================================================

# ==================================================

# STEP 4: BUILD METADATA

# ==================================================

print("\n" + "=" * 60)
print("STEP 4: BUILDING METADATA")
print("=" * 60)

metadatas = []

for c in chunks:
    metadata = MetadataBuilder.build_metadata(
        repository_id=REPO_ID,
        file_path=c["file_path"],
        language=c["language"],
        chunk_type=c["chunk_type"],
        class_name=c.get("class_name"),
        function_name=c.get("function_name"),
        start_line=c["start_line"],
        end_line=c["end_line"],
        dependencies=c.get("dependencies", []),
        content=c["content"]
    )

    metadatas.append(metadata)

metadatas.append(metadata)

print(f"Metadata Created: {len(metadatas)}")

# ==================================================

# STEP 5: EMBEDDING

# ==================================================

print("\n" + "=" * 60)
print("STEP 5: GENERATING EMBEDDINGS")
print("=" * 60)

documents = [c["content"] for c in chunks]

print(f"Generating embeddings for {len(documents)} chunks...")

embedding_start = time()

embeddings = EmbeddingService.batch_embedding(
documents,
batch_size=100
)

embedding_end = time()

print(
f"Embeddings Generated: {len(embeddings)} "
f"in {round(embedding_end - embedding_start, 2)} sec"
)

# ==================================================

# STEP 6: STORE

# ==================================================

print("\n" + "=" * 60)
print("STEP 6: STORING IN CHROMA")
print("=" * 60)

VectorStore.create_collection(REPO_ID)

store_start = time()

VectorStore.insert_chunks(
repo_id=REPO_ID,
documents=documents,
embeddings=embeddings,
metadatas=metadatas
)

store_end = time()

print(
f"Uploaded {len(documents)} vectors "
f"in {round(store_end - store_start, 2)} sec"
)

# ==================================================

# COMPLETE

# ==================================================

total_time = round(time() - start_time, 2)

print("\n" + "=" * 60)
print("INGESTION COMPLETE")
print("=" * 60)

print(f"Repository: {REPO_ID}")
print(f"Files: {scan_results['file_count']}")
print(f"Entities: {len(entities)}")
print(f"Chunks: {len(chunks)}")
print(f"Embeddings: {len(embeddings)}")
print(f"Total Time: {total_time} sec")

print("=" * 60)
