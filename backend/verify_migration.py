# backend/verify_migration.py
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend root is in PYTHONPATH
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(backend_dir / ".env")

from app.core.config import settings
from app.services.providers.factory import ProviderFactory
from app.database import db

def verify():
    v_store = ProviderFactory.get_vector_store()
    client = v_store._get_client()
    
    # 1. Fetch all collections
    collections = client.list_collections()
    legacy_col_names = [
        col.name for col in collections
        if col.name.startswith("repo_") and col.name != "repo_RAGDATA"
    ]
    
    print("\n" + "="*80)
    print("MIGRATION VERIFICATION MATRIX")
    print("="*80)
    
    # Header
    print(f"{'Repository ID':<40} | {'Legacy Count':<12} | {'RAGDATA Count':<13} | {'Migration Status':<16}")
    print("-" * 90)
    
    total_legacy = 0
    total_ragdata = 0
    failures = 0
    
    results_summary = []
    
    # Ensure target collection exists
    try:
        target_col = client.get_collection("repo_RAGDATA")
    except Exception as e:
        print(f"Error fetching repo_RAGDATA collection: {e}")
        return
        
    for name in legacy_col_names:
        repo_id = name[5:]
        try:
            legacy_col = client.get_collection(name)
            legacy_count = legacy_col.count()
        except Exception as e:
            print(f"Error reading legacy collection {name}: {e}")
            continue
            
        # Count in target collection filtered by repo_id using paginated get loops (max 300 per call)
        try:
            ragdata_count = 0
            offset = 0
            get_limit = 300
            while True:
                target_results = target_col.get(
                    where={"repo_id": repo_id},
                    limit=get_limit,
                    offset=offset,
                    include=[]
                )
                fetched_ids = target_results.get("ids", [])
                ragdata_count += len(fetched_ids)
                if len(fetched_ids) < get_limit:
                    break
                offset += get_limit
        except Exception as e:
            ragdata_count = 0
            print(f"Error querying repo_RAGDATA for {repo_id}: {e}")
            
        status = "SUCCESS" if legacy_count == ragdata_count and legacy_count > 0 else "FAILED"
        if status == "FAILED":
            failures += 1
            
        total_legacy += legacy_count
        total_ragdata += ragdata_count
        
        print(f"{repo_id:<40} | {legacy_count:<12d} | {ragdata_count:<13d} | {status:<16}")
        results_summary.append({
            "repo_id": repo_id,
            "legacy_count": legacy_count,
            "ragdata_count": ragdata_count,
            "status": status
        })
        
    print("-" * 90)
    print(f"{'TOTAL':<40} | {total_legacy:<12d} | {total_ragdata:<13d} | {'SUCCESS' if failures == 0 else 'FAILED'}")
    print("="*80 + "\n")
    
    # 2. Verify SQLite registry
    print("SQLITE REGISTRY VERIFICATION")
    print("="*80)
    print(f"{'Repository ID':<40} | {'Reg Chunk Count':<15} | {'Reg Vector Count':<16} | {'Status':<10}")
    print("-" * 90)
    
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT * FROM repositories").fetchall()
        for row in rows:
            r = dict(row)
            rid = r["repo_id"]
            ccount = r["chunk_count"]
            vcount = r["vector_count"]
            
            # Find in results_summary
            matched = next((item for item in results_summary if item["repo_id"] == rid), None)
            if matched:
                db_status = "MATCH" if matched["ragdata_count"] == vcount else "MISMATCH"
            else:
                db_status = "ORPHAN"
                
            print(f"{rid:<40} | {ccount:<15d} | {vcount:<16d} | {db_status:<10}")
    except Exception as e:
        print(f"Error reading SQLite repositories table: {e}")
    finally:
        conn.close()
    print("="*80 + "\n")

if __name__ == "__main__":
    verify()
