from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]

EXTRACT_MODEL = "llama-3.3-70b-versatile"
PLAN_MODEL = "llama-3.3-70b-versatile"

KB_DIR = str(ROOT_DIR / "kb")
INDEX_DIR = str(ROOT_DIR / "kb_index")
GENERATED_DIR = str(ROOT_DIR / "generated")
TEMPLATES_DIR = str(Path(__file__).resolve().parent / "templates")

# Ansible paths
ANSIBLE_TEMPLATES_DIR = str(Path(__file__).resolve().parent / "templates")
ANSIBLE_GENERATED_DIR = str(Path(GENERATED_DIR) / "ansible")

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

TOP_K = 6
MAX_CHARS_PER_CHUNK = 1800
