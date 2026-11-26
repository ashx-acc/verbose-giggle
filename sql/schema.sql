-- Chicago Crime Analytics — SQLite schema
-- Run with:  sqlite3 chicago_crime.db < sql/schema.sql
-- The FastAPI app also creates these objects automatically on startup.

PRAGMA foreign_keys = ON;

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

DROP VIEW IF EXISTS vw_crime_yearly;
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

DROP VIEW IF EXISTS vw_crime_by_category;
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
