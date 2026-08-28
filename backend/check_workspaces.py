import sys, os
os.chdir('backend')
sys.path.insert(0, '.')
from app.core.config import settings
from pathlib import Path

ws_root = settings.WORKSPACES_DIR
for d in sorted(ws_root.iterdir()):
    if not d.is_dir():
        continue
    py_files = list(d.rglob('*.py'))
    all_files = list(d.rglob('*'))
    sample = py_files[0].name if py_files else 'N/A'
    print(f"{d.name[:40]:<42}  {len(all_files):>5} files  py:{len(py_files):>3}  sample:{sample}")
