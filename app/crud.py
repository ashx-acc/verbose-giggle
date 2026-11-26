"""SQLite CRUD operations for the community dimension table."""

from __future__ import annotations

import sqlite3
from typing import Any

from . import schemas

COMMUNITY_COLUMNS = (
    "community_code",
    "community_name",
    "population",
    "area_sqmile",
    "area_sqkm",
    "density_per_sqmi",
    "density_per_sqkm",
)

UPDATABLE_COLUMNS = (
    "community_name",
    "population",
    "area_sqmile",
    "area_sqkm",
    "density_per_sqmi",
    "density_per_sqkm",
)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def list_communities(
    connection: sqlite3.Connection,
    search: str | None = None,
) -> list[dict[str, Any]]:
    query = (
        "SELECT community_code, community_name, population, area_sqmile, "
        "area_sqkm, density_per_sqmi, density_per_sqkm "
        "FROM community"
    )
    parameters: list[Any] = []

    if search and search.strip():
        term = f"%{search.strip()}%"
        query += (
            " WHERE community_name LIKE ? COLLATE NOCASE "
            "OR CAST(community_code AS TEXT) LIKE ?"
        )
        parameters.extend([term, term])

    query += " ORDER BY community_code"
    rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def get_community(
    connection: sqlite3.Connection,
    community_code: int,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT community_code, community_name, population, area_sqmile, "
        "area_sqkm, density_per_sqmi, density_per_sqkm "
        "FROM community WHERE community_code = ?",
        (community_code,),
    ).fetchone()
    return _row_to_dict(row)


def find_by_name(
    connection: sqlite3.Connection,
    community_name: str,
    exclude_code: int | None = None,
) -> dict[str, Any] | None:
    query = (
        "SELECT community_code, community_name FROM community "
        "WHERE LOWER(community_name) = LOWER(?)"
    )
    parameters: list[Any] = [community_name.strip()]
    if exclude_code is not None:
        query += " AND community_code <> ?"
        parameters.append(exclude_code)
    row = connection.execute(query, parameters).fetchone()
    return _row_to_dict(row)


def create_community(
    connection: sqlite3.Connection,
    payload: schemas.CommunityCreate,
) -> dict[str, Any]:
    data = payload.model_dump()
    connection.execute(
        """
        INSERT INTO community (
            community_code,
            community_name,
            population,
            area_sqmile,
            area_sqkm,
            density_per_sqmi,
            density_per_sqkm
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        tuple(data[column] for column in COMMUNITY_COLUMNS),
    )
    connection.commit()
    created = get_community(connection, payload.community_code)
    if created is None:  # pragma: no cover - defensive guard
        raise sqlite3.DatabaseError("Inserted row could not be read back.")
    return created


def update_community(
    connection: sqlite3.Connection,
    community_code: int,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    fields = [field for field in UPDATABLE_COLUMNS if field in data]
    if not fields:
        return get_community(connection, community_code)

    assignments = ", ".join(f"{field} = ?" for field in fields)
    values = [data[field] for field in fields]
    values.append(community_code)

    connection.execute(
        f"UPDATE community SET {assignments} WHERE community_code = ?",
        values,
    )
    connection.commit()
    return get_community(connection, community_code)


def delete_community(
    connection: sqlite3.Connection,
    community_code: int,
) -> None:
    connection.execute(
        "DELETE FROM community WHERE community_code = ?",
        (community_code,),
    )
    connection.commit()
