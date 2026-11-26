-- Use Case 4 — reporting queries
-- Run with:  sqlite3 chicago_crime.db < sql/queries.sql

-- 1. Crime count per year
SELECT
    Year,
    COUNT(*) AS crime_count
FROM crime
GROUP BY Year
ORDER BY Year;

-- 2. Top 5 crime types and their percentages
SELECT
    primary_type,
    COUNT(*) AS crime_count,
    ROUND(
        COUNT(*) * 100.0 / (SELECT COUNT(*) FROM crime),
        2
    ) AS percentage
FROM crime
GROUP BY primary_type
ORDER BY crime_count DESC
LIMIT 5;

-- 3. Arrest count per year
SELECT
    Year,
    SUM(CASE WHEN arrest = 1 THEN 1 ELSE 0 END) AS arrest_count,
    ROUND(
        SUM(CASE WHEN arrest = 1 THEN 1.0 ELSE 0.0 END)
        * 100.0 / COUNT(*),
        2
    ) AS arrest_rate
FROM crime
GROUP BY Year
ORDER BY Year;

-- 4. Read the stored views
SELECT * FROM vw_crime_yearly ORDER BY Year;
SELECT * FROM vw_crime_by_category ORDER BY crime_count DESC;

-- 5. Top 10 community areas
SELECT
    c.community_code,
    c.community_name,
    COUNT(*) AS crime_count
FROM crime AS f
LEFT JOIN community AS c
    ON c.community_code = f.community_code
GROUP BY c.community_code, c.community_name
ORDER BY crime_count DESC
LIMIT 10;

-- 6. Monthly / weekday frequency for the heatmap
SELECT
    Month,
    DayOfWeek,
    COUNT(*) AS crime_count
FROM crime
GROUP BY Month, DayOfWeek
ORDER BY Month, DayOfWeek;
