"""
test_chroma_connection.py
=========================
Isolated Chroma Cloud connectivity test.

- No embeddings
- No repository processing
- No Ollama
- Tests only the CloudChromaProvider against live credentials

Run from the backend/ directory:
    python test_chroma_connection.py

Expected: health_check prints {"status": "healthy", ...}
"""
import sys
import os

# Ensure backend/app is importable when run from backend/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services.providers.vector_store.cloud_chroma_provider import CloudChromaProvider
from app.core.config import settings

SEP = "=" * 60

# Print credential summary (masked)
print(SEP)
print("CHROMA CLOUD CREDENTIALS")
print(SEP)
print(f"  CHROMA_HOST     : {settings.CHROMA_HOST}")
print(f"  CHROMA_TENANT   : {settings.CHROMA_TENANT}")
print(f"  CHROMA_DATABASE : {settings.CHROMA_DATABASE}")
key = settings.CHROMA_API_KEY
masked_key = (key[:8] + "..." + key[-4:]) if len(key) > 12 else "[NOT SET]"
print(f"  CHROMA_API_KEY  : {masked_key}")
print(SEP)
print()

# --- Test 1: Health Check (heartbeat) ----------------------------------------
print("[TEST 1] CloudChromaProvider.health_check()")
try:
    provider = CloudChromaProvider()
    result = provider.health_check()
    print("  Result:", result)
    if result.get("status") == "healthy":
        print("  PASSED -- Chroma Cloud is reachable\n")
    else:
        print("  FAILED -- Connection unhealthy\n")
        sys.exit(1)
except Exception as e:
    print(f"  EXCEPTION: {e}\n")
    sys.exit(1)

# --- Test 2: Create a test collection ----------------------------------------
print("[TEST 2] create_collection('connection_test')")
try:
    col = provider.create_collection("connection_test")
    print(f"  Collection object: {col}")
    print("  PASSED -- Collection created/retrieved\n")
except Exception as e:
    print(f"  EXCEPTION: {e}\n")
    sys.exit(1)

# --- Test 3: List collections ------------------------------------------------
print("[TEST 3] List all collections in tenant/database")
try:
    client = provider._get_client()
    collections = client.list_collections()
    print(f"  Collections found: {len(collections)}")
    for c in collections:
        name = getattr(c, "name", str(c))
        print(f"    - {name}")
    print("  PASSED\n")
except Exception as e:
    print(f"  EXCEPTION: {e}\n")

print(SEP)
print("ALL TESTS COMPLETE")
print(SEP)
