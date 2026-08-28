from app.services.providers.embedding.local_bge_provider import LocalBGEProvider

provider = LocalBGEProvider()

vector = provider.embed_query(
    "How authentication works?"
)

print("Vector Length:", len(vector))
print("First 5 values:", vector[:5])