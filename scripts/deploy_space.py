"""Deploy the app (code + cached sample results + web proxies) to a Hugging Face Docker Space.

usage: python scripts/deploy_space.py <hf-username>/<space-name>
Requires `hf auth login` (write token). Set GEMINI_API_KEY as a Space secret for live processing."""
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
repo_id = sys.argv[1]
api = HfApi()
api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True, private=False)

readme = """---
title: Birati - Contextual Ad Breaks
emoji: 🎬
colorFrom: pink
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: AI-native ad-break placement for Bengali drama (VMAP)
---
""" + (ROOT / "README.md").read_text(encoding="utf-8")

with tempfile.TemporaryDirectory() as td:
    rp = Path(td) / "README.md"
    rp.write_text(readme, encoding="utf-8")
    api.upload_folder(
        repo_id=repo_id, repo_type="space", folder_path=str(ROOT),
        allow_patterns=["app/**/*.py", "web/*.html", "web/*.js", "web/*.css", "scripts/*.py",
                        "data/brands.json", "data/brands_plus_unseen.json",
                        "data/work/*/*.json", "data/work/*/*.xml", "data/work/*/proxy.mp4",
                        "Dockerfile", ".dockerignore", "requirements.txt"],
        ignore_patterns=["**/__pycache__/**", "data/work/*/verify_*", "data/work/*/clip_*", "data/work/*/match_*.mp4"],
        commit_message="Deploy Birati",
    )
    api.upload_file(path_or_fileobj=str(rp), path_in_repo="README.md", repo_id=repo_id, repo_type="space")
print(f"https://huggingface.co/spaces/{repo_id}")
print(f"app: https://{repo_id.replace('/', '-').replace('_', '-').lower()}.hf.space")
