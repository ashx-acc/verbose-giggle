"""Project paths and shared configuration."""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

EXPORTS_DIR = PROJECT_ROOT / "exports"
CHARTS_DIR = EXPORTS_DIR / "charts"
SCREENSHOTS_DIR = EXPORTS_DIR / "screenshots"

DB_PATH = PROJECT_ROOT / "chicago_crime.db"

for _directory in (CHARTS_DIR, SCREENSHOTS_DIR):
    _directory.mkdir(parents=True, exist_ok=True)
