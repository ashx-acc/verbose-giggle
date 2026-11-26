"""Create the SQLite warehouse and seed it from the cleaned CSV files.

No ORM is used: tables are created with plain SQL and rows are inserted with
``sqlite3.executemany``.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

import numpy as np
import pandas as pd

from .config import PROCESSED_DIR, RAW_DIR
from .database import connect

logger = logging.getLogger(__name__)

COMMUNITY_COLUMNS = [
    "community_code",
    "community_name",
    "population",
    "area_sqmile",
    "area_sqkm",
    "density_per_sqmi",
    "density_per_sqkm",
]

CRIME_COLUMNS = [
    "id",
    "case_number",
    "date",
    "block",
    "iucr_code",
    "primary_type",
    "description",
    "location_desc",
    "arrest",
    "domestic",
    "beat_num",
    "district_code",
    "ward_no",
    "community_code",
    "fbi_code",
    "x_coordinate",
    "y_coordinate",
    "Year",
    "Month",
    "DayOfWeek",
    "date_of_update",
    "latitude",
    "longitude",
    "location",
]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS community (
    community_code     INTEGER PRIMARY KEY,
    community_name     TEXT NOT NULL,
    population         INTEGER,
    area_sqmile        REAL,
    area_sqkm          REAL,
    density_per_sqmi   REAL,
    density_per_sqkm   REAL
);

CREATE TABLE IF NOT EXISTS crime (
    id                 INTEGER PRIMARY KEY,
    case_number        TEXT,
    date               TEXT,
    block              TEXT,
    iucr_code          TEXT,
    primary_type       TEXT,
    description        TEXT,
    location_desc      TEXT,
    arrest             INTEGER,
    domestic           INTEGER,
    beat_num           INTEGER,
    district_code      INTEGER,
    ward_no            INTEGER,
    community_code     INTEGER,
    fbi_code           TEXT,
    x_coordinate       REAL,
    y_coordinate       REAL,
    Year               INTEGER,
    Month              INTEGER,
    DayOfWeek          TEXT,
    date_of_update     TEXT,
    latitude           REAL,
    longitude          REAL,
    location           TEXT
);

CREATE INDEX IF NOT EXISTS idx_crime_year ON crime (Year);
CREATE INDEX IF NOT EXISTS idx_crime_primary_type ON crime (primary_type);
CREATE INDEX IF NOT EXISTS idx_crime_community ON crime (community_code);
CREATE INDEX IF NOT EXISTS idx_crime_district ON crime (district_code);
CREATE INDEX IF NOT EXISTS idx_crime_arrest ON crime (arrest);
CREATE INDEX IF NOT EXISTS idx_community_name ON community (community_name);
"""

VIEWS_SQL = """
DROP VIEW IF EXISTS vw_crime_yearly;
DROP VIEW IF EXISTS vw_crime_by_category;

CREATE VIEW vw_crime_yearly AS
SELECT
    Year AS Year,
    COUNT(*) AS crime_count,
    SUM(CASE WHEN arrest = 1 THEN 1 ELSE 0 END) AS arrest_count,
    ROUND(
        SUM(CASE WHEN arrest = 1 THEN 1.0 ELSE 0.0 END)
        * 100.0 / COUNT(*),
        2
    ) AS arrest_rate
FROM crime
GROUP BY Year;

CREATE VIEW vw_crime_by_category AS
SELECT
    primary_type,
    COUNT(*) AS crime_count,
    ROUND(
        COUNT(*) * 100.0 / (SELECT COUNT(*) FROM crime),
        2
    ) AS percentage
FROM crime
WHERE primary_type IS NOT NULL
GROUP BY primary_type;
"""


def _to_db(value: Any) -> Any:
    """Convert pandas/NumPy scalars to values sqlite3 can bind."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _rows(frame: pd.DataFrame, columns: list[str]) -> list[tuple[Any, ...]]:
    return [
        tuple(_to_db(row.get(column)) for column in columns)
        for row in frame.to_dict(orient="records")
    ]


def _read_community_csv() -> pd.DataFrame | None:
    processed = PROCESSED_DIR / "chicago_city_community_cleaned.csv"
    raw = RAW_DIR / "chicago_city_community.csv"

    if processed.exists():
        frame = pd.read_csv(processed)
    elif raw.exists():
        frame = pd.read_csv(raw)
        for column in ("population", "density_per_sqmi", "density_per_sqkm"):
            if column in frame.columns:
                frame[column] = pd.to_numeric(
                    frame[column].astype(str).str.replace(",", "", regex=False),
                    errors="coerce",
                )
    else:
        return None

    missing = [column for column in COMMUNITY_COLUMNS if column not in frame.columns]
    if missing:
        logger.warning("Community CSV is missing columns: %s", missing)
        return None

    frame = frame[COMMUNITY_COLUMNS].copy()
    frame["community_name"] = frame["community_name"].astype(str).str.strip()
    frame = frame.dropna(subset=["community_code", "community_name"])
    frame["community_code"] = frame["community_code"].astype(int)
    frame["population"] = pd.to_numeric(frame["population"], errors="coerce").astype("Int64")
    return frame


def _read_crime_csv() -> pd.DataFrame | None:
    for filename in (
        "chicago_crime_analysis_ready.csv",
        "chicago_crime_cleaned.csv",
    ):
        path = PROCESSED_DIR / filename
        if not path.exists():
            continue

        frame = pd.read_csv(path, low_memory=False)
        missing = [column for column in CRIME_COLUMNS if column not in frame.columns]
        if missing:
            logger.warning("%s is missing columns: %s", filename, missing)
            continue

        frame = frame[CRIME_COLUMNS].copy()
        for column in ("arrest", "domestic"):
            frame[column] = frame[column].fillna(False).astype(bool).astype(int)
        return frame

    return None


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    connection.commit()


def _create_views(connection: sqlite3.Connection) -> None:
    connection.executescript(VIEWS_SQL)
    connection.commit()


def _count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def seed_database(force: bool = False) -> None:
    """Create tables and seed them if they are empty.

    Args:
        force: Delete existing community/crime rows and reload the CSVs.
    """

    connection = connect()
    try:
        _create_schema(connection)

        if force or _count(connection, "community") == 0:
            community_frame = _read_community_csv()
            if community_frame is not None and not community_frame.empty:
                if force:
                    connection.execute("DELETE FROM community")
                placeholders = ", ".join("?" for _ in COMMUNITY_COLUMNS)
                connection.executemany(
                    f"INSERT INTO community ({', '.join(COMMUNITY_COLUMNS)}) "
                    f"VALUES ({placeholders})",
                    _rows(community_frame, COMMUNITY_COLUMNS),
                )
                connection.commit()
                logger.info("Seeded %s community rows.", len(community_frame))
            else:
                logger.warning("Community CSV not found; CRUD table will be empty.")

        if force or _count(connection, "crime") == 0:
            crime_frame = _read_crime_csv()
            if crime_frame is not None and not crime_frame.empty:
                if force:
                    connection.execute("DELETE FROM crime")
                placeholders = ", ".join("?" for _ in CRIME_COLUMNS)
                connection.executemany(
                    f"INSERT INTO crime ({', '.join(CRIME_COLUMNS)}) "
                    f"VALUES ({placeholders})",
                    _rows(crime_frame, CRIME_COLUMNS),
                )
                connection.commit()
                logger.info("Seeded %s crime rows.", len(crime_frame))
            else:
                logger.warning("Crime CSV not found; dashboard will show no data.")

        _create_views(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    seed_database(force=True)
    print("Database rebuilt from data/processed.")
