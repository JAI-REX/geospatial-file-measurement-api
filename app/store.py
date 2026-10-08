from __future__ import annotations

from pathlib import Path
from threading import Lock

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

FILES: dict[str, dict] = {}
LOCK = Lock()
