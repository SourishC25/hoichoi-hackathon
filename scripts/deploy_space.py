"""Publish the static export (scripts/export_static.py) as a free *static* Hugging Face Space.

usage: python scripts/deploy_space.py <hf-username>/<space-name>
Requires `hf auth login` with a write token. Static Spaces are free; live processing runs locally."""
import subprocess
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
repo_id = sys.argv[1]
# build outside the repo (synced folders such as OneDrive can lock files and break re-exports)
dist = Path(tempfile.mkdtemp(prefix="birati_static_")) / "dist"
subprocess.run([sys.executable, str(ROOT / "scripts" / "export_static.py"), "--space", repo_id, "--out", str(dist)], check=True)

api = HfApi()
api.create_repo(repo_id, repo_type="space", space_sdk="static", exist_ok=True, private=False)
api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=str(dist), commit_message="Publish Birati static demo")
user, name = repo_id.split("/")
print(f"space: https://huggingface.co/spaces/{repo_id}")
print(f"app:   https://{user.lower()}-{name.lower().replace('_', '-')}.static.hf.space")
