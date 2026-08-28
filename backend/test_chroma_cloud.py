from app.services.providers.embedding.local_bge_provider import LocalBGEProvider
from app.services.providers.vector_store.cloud_chroma_provider import CloudChromaProvider

repo_id = "test_repo"

embedding_provider = LocalBGEProvider()
vector_provider = CloudChromaProvider()

text = "Authentication is handled using JWT tokens."

embedding = embedding_provider.embed_query(text)

metadata = [{
    "hash": "test001",
    "file_path": "auth.py",
    "language": "python"
}]

vector_provider.insert(
    repo_id=repo_id,
    documents=[text],
    embeddings=[embedding],
    metadatas=metadata
)

results = vector_provider.search(
    repo_id=repo_id,
    query_embedding=embedding,
    top_k=3
)

print("\nRESULTS\n")

for r in results:
    print(r)