import sys, os
os.chdir('backend')
sys.path.insert(0, '.')
from app.services.repository_processor import RepositoryProcessor
from app.models.repository import RepositoryModel
from app.core.config import settings
from pathlib import Path
import asyncio

# Run intelligence pipeline on the UUID repo that has 41 vectors
repo_id = '552836ea-bd8e-4959-bc1d-5f9f6d11976a'
workspace_path = settings.WORKSPACES_DIR / repo_id
print('Workspace exists:', workspace_path.exists())
files = list(workspace_path.rglob('*'))
print('Files in workspace:', len(files))

# Check what's in there
for f in sorted(files)[:20]:
    print(' ', f.relative_to(workspace_path))
