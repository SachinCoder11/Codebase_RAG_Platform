# backend/migrate_legacy_collections.py
import os
import sys
import logging
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
from app.services.metadata_builder import MetadataBuilder
from app.database import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration")

# Mapping of known repo IDs to their clean metadata
KNOWN_METADATA = {
    "fastapi_test": {
        "repo_name": "FastAPI",
        "owner": "tiangolo",
        "source_type": "github"
    },
    "chroma_test": {
        "repo_name": "Chroma",
        "owner": "chroma-core",
        "source_type": "github"
    },
    "langchain_test": {
        "repo_name": "LangChain",
        "owner": "langchain-ai",
        "source_type": "github"
    }
}

def migrate():
    logger.info("Initializing vector store provider...")
    v_store = ProviderFactory.get_vector_store()
    client = v_store._get_client()
    
    # 1. List all collections in the tenant/database
    logger.info("Listing all collections in Chroma Cloud...")
    collections = client.list_collections()
    
    legacy_collections = []
    for col in collections:
        name = getattr(col, "name", str(col))
        if name.startswith("repo_") and name != "repo_RAGDATA":
            legacy_collections.append(col)
            
    logger.info(f"Found {len(legacy_collections)} legacy collection(s) to migrate: {[c.name for c in legacy_collections]}")
    
    # Ensure target collection exists
    target_col = v_store.create_collection("RAGDATA")
    logger.info(f"Target collection 'repo_RAGDATA' initialized. Current count: {target_col.count()}")
    
    db_conn = db.get_connection()
    
    for legacy_col in legacy_collections:
        c_name = legacy_col.name
        repo_id = c_name[5:] # strip "repo_" prefix
        logger.info(f"Processing collection '{c_name}' (repo_id='{repo_id}')...")
        
        # Determine metadata defaults
        meta_defaults = KNOWN_METADATA.get(repo_id, {
            "repo_name": repo_id,
            "owner": "local",
            "source_type": "zip"
        })
        
        # Read all documents, embeddings, and metadatas from legacy collection in batches
        logger.info(f"Retrieving vectors from '{c_name}'...")
        total_vectors = legacy_col.count()
        logger.info(f"Collection '{c_name}' has {total_vectors} vectors.")
        
        if total_vectors == 0:
            logger.warning(f"Collection '{c_name}' is empty. Skipping.")
            continue
            
        migrated_count = 0
        get_batch_size = 300
        
        for offset in range(0, total_vectors, get_batch_size):
            logger.info(f"Retrieving batch offset={offset}, limit={get_batch_size} from '{c_name}'...")
            results = legacy_col.get(
                include=["documents", "embeddings", "metadatas"],
                limit=get_batch_size,
                offset=offset
            )
            
            documents = results.get("documents", [])
            embeddings = results.get("embeddings", [])
            metadatas = results.get("metadatas", [])
            ids = results.get("ids", [])
            
            if not documents:
                break
                
            logger.info(f"Successfully retrieved {len(documents)} vectors at offset {offset}.")
            
            # Process metadatas
            processed_metadatas = []
            for i, meta in enumerate(metadatas):
                if meta is None:
                    meta = {}
                meta["repo_id"] = meta.get("repo_id") or meta.get("repository_id") or repo_id
                meta["repo_name"] = meta.get("repo_name") or meta.get("repository_name") or meta_defaults["repo_name"]
                meta["owner"] = meta.get("owner") or meta_defaults["owner"]
                meta["source_type"] = meta.get("source_type") or meta_defaults["source_type"]
                
                if "start_line" in meta:
                    meta["start_line"] = int(meta["start_line"])
                if "end_line" in meta:
                    meta["end_line"] = int(meta["end_line"])
                processed_metadatas.append(meta)
                
            new_ids = [f"{repo_id}_{cid}" if not cid.startswith(repo_id) else cid for cid in ids]
            
            # Insert in batches of 100 (safe size for Cloud Chroma)
            add_batch_size = 100
            for add_start in range(0, len(documents), add_batch_size):
                add_end = min(add_start + add_batch_size, len(documents))
                target_col.add(
                    ids=new_ids[add_start:add_end],
                    embeddings=embeddings[add_start:add_end],
                    metadatas=processed_metadatas[add_start:add_end],
                    documents=documents[add_start:add_end]
                )
                logger.info(f"  Migrated batch {add_start//add_batch_size + 1}/{(len(documents)+add_batch_size-1)//add_batch_size} of offset {offset}")
                
            migrated_count += len(documents)
            
        # Populate SQLite Registry
        logger.info(f"Registering repository '{repo_id}' in SQLite with {migrated_count} chunks...")
        db_conn.execute("""
            INSERT INTO repositories (repo_id, repo_name, owner, source_type, chunk_count, vector_count)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_id) DO UPDATE SET
                repo_name = excluded.repo_name,
                owner = excluded.owner,
                source_type = excluded.source_type,
                chunk_count = excluded.chunk_count,
                vector_count = excluded.vector_count
        """, (
            repo_id,
            meta_defaults["repo_name"],
            meta_defaults["owner"],
            meta_defaults["source_type"],
            migrated_count,
            migrated_count
        ))
        db_conn.commit()
        logger.info(f"Repository '{repo_id}' successfully registered with count {migrated_count}.")
        
    db_conn.close()
    logger.info("Migration finished successfully!")

if __name__ == "__main__":
    migrate()
