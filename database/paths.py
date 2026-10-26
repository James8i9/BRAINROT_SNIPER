"""
database/paths.py
=================
Single source of truth for the SQLite file location.

On Railway: mount a volume at /data and set:
  DATABASE_PATH=/data/brainrot.db

Without that, the DB lives in the container filesystem and is wiped on every deploy.
"""

import os
from pathlib import Path


def get_db_path() -> str:
    path = (os.getenv("DATABASE_PATH") or "brainrot.db").strip() or "brainrot.db"
    p = Path(path)
    # Ensure parent exists (e.g. /data on a Railway volume)
    if p.parent and str(p.parent) not in (".", ""):
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    return str(p)
