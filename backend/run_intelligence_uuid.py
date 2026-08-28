import sys, os
os.chdir('backend')
sys.path.insert(0, '.')
from app.services.repository_processor import RepositoryProcessor
from app.models.repository import RepositoryModel
from app.core.config import settings
from pathlib import Path
import asyncio

repo_id = '552836ea-bd8e-4959-bc1d-5f9f6d11976a'
workspace_path = settings.WORKSPACES_DIR / repo_id

# Peek at the repo structure to derive a good name
ts_files = list(workspace_path.rglob('*.ts'))[:5]
print('TypeScript files found:', len(list(workspace_path.rglob('*.ts'))))

# Check package.json
pkg = workspace_path / 'apps' / 'api' / 'package.json'
if pkg.exists():
    import json
    with open(pkg) as f:
        data = json.load(f)
    print('Package name:', data.get('name', 'unknown'))

identity = {
    'repo_id': repo_id,
    'repo_name': 'RAG Analysis API',
    'owner': 'local',
    'source_type': 'zip',
    'source_url': ''
}

print('Starting intelligence pipeline...')
asyncio.run(RepositoryProcessor.process_repository(repo_id, 'RAG Analysis API', workspace_path, identity))
status = RepositoryProcessor.get_status(repo_id)
print('Status:', status['status'], '-', status['message'][:100])
print('Quality:', status.get('details', {}).get('quality_score', 'N/A'))
