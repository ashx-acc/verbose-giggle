"""FastAPI application: dashboard, community CRUD API, and report export.

Database layer: Python's built-in ``sqlite3`` module only.
"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import crud, schemas
from .analytics import (
    build_dashboard_context,
    build_report_image,
    get_insights_payload,
)
from .config import BASE_DIR, DB_PATH, EXPORTS_DIR
from .database import get_db
from .seed import seed_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create tables, seed from CSV when empty, and build the SQL views."""
    seed_database()
    yield


app = FastAPI(
    title="Chicago Crime Analytics API",
    version="1.0.0",
    description=(
        "FastAPI + sqlite3 demo for the Accenture / Chicago Police Department "
        "crime analytics case study. Includes a dashboard, a full CRUD API for "
        "the community dimension table, and PNG report export."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/exports", StaticFiles(directory=str(EXPORTS_DIR)), name="exports")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["comma"] = (
    lambda value: f"{value:,}" if isinstance(value, (int, float)) else "—"
)
templates.env.filters["pct"] = (
    lambda value: f"{float(value):.1f}%" if value is not None else "—"
)
templates.env.filters["num"] = (
    lambda value: f"{float(value):,.1f}" if value is not None else "—"
)


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, tags=["pages"])
def dashboard_page(request: Request):
    context = build_dashboard_context()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "active_page": "dashboard",
            **context,
        },
    )


@app.get("/community", response_class=HTMLResponse, tags=["pages"])
def community_page(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    communities = crud.list_communities(db)
    total_population = sum(community["population"] or 0 for community in communities)
    average_density = (
        sum(community["density_per_sqmi"] or 0 for community in communities)
        / len(communities)
        if communities
        else 0
    )
    return templates.TemplateResponse(
        request=request,
        name="community.html",
        context={
            "request": request,
            "active_page": "community",
            "communities": communities,
            "community_count": len(communities),
            "total_population": total_population,
            "average_density": average_density,
        },
    )


# ---------------------------------------------------------------------------
# Community CRUD API
# ---------------------------------------------------------------------------


def _ensure_unique_name(
    db: sqlite3.Connection,
    community_name: str,
    exclude_code: int | None = None,
) -> None:
    duplicate = crud.find_by_name(db, community_name, exclude_code=exclude_code)
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Community name '{community_name}' already belongs to code "
                f"{duplicate['community_code']}."
            ),
        )


@app.get(
    "/api/community",
    response_model=list[schemas.CommunityRead],
    tags=["community CRUD"],
)
def list_communities(
    search: str | None = Query(default=None, max_length=120),
    db: sqlite3.Connection = Depends(get_db),
):
    """List community areas, optionally filtered by name or numeric code."""
    return crud.list_communities(db, search=search)


@app.post(
    "/api/community",
    response_model=schemas.CommunityRead,
    status_code=status.HTTP_201_CREATED,
    tags=["community CRUD"],
)
def create_community(
    payload: schemas.CommunityCreate,
    db: sqlite3.Connection = Depends(get_db),
):
    """Create a new community-area dimension row."""
    if crud.get_community(db, payload.community_code) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Community code {payload.community_code} already exists.",
        )
    _ensure_unique_name(db, payload.community_name)

    try:
        return crud.create_community(db, payload)
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Community code or name violates a database constraint.",
        ) from error


@app.get(
    "/api/community/{community_code}",
    response_model=schemas.CommunityRead,
    tags=["community CRUD"],
)
def get_community(
    community_code: int,
    db: sqlite3.Connection = Depends(get_db),
):
    community = crud.get_community(db, community_code)
    if community is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community code {community_code} was not found.",
        )
    return community


@app.put(
    "/api/community/{community_code}",
    response_model=schemas.CommunityRead,
    tags=["community CRUD"],
)
def replace_community(
    community_code: int,
    payload: schemas.CommunityReplace,
    db: sqlite3.Connection = Depends(get_db),
):
    """Full update (PUT). The community code comes from the URL."""
    community = crud.get_community(db, community_code)
    if community is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community code {community_code} was not found.",
        )
    _ensure_unique_name(db, payload.community_name, exclude_code=community_code)

    try:
        updated = crud.update_community(db, community_code, payload.model_dump())
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Community name violates a database constraint.",
        ) from error

    if updated is None:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community code {community_code} was not found.",
        )
    return updated


@app.patch(
    "/api/community/{community_code}",
    response_model=schemas.CommunityRead,
    tags=["community CRUD"],
)
def patch_community(
    community_code: int,
    payload: schemas.CommunityPatch,
    db: sqlite3.Connection = Depends(get_db),
):
    """Partial update (PATCH). Only the fields sent in the body are changed."""
    community = crud.get_community(db, community_code)
    if community is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community code {community_code} was not found.",
        )

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields were provided for the PATCH request.",
        )
    if "community_name" in data:
        if data["community_name"] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="community_name cannot be null.",
            )
        _ensure_unique_name(
            db,
            data["community_name"],
            exclude_code=community_code,
        )

    try:
        updated = crud.update_community(db, community_code, data)
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Community name violates a database constraint.",
        ) from error

    if updated is None:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community code {community_code} was not found.",
        )
    return updated


@app.delete(
    "/api/community/{community_code}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["community CRUD"],
)
def delete_community(
    community_code: int,
    db: sqlite3.Connection = Depends(get_db),
):
    community = crud.get_community(db, community_code)
    if community is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community code {community_code} was not found.",
        )
    crud.delete_community(db, community_code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/community/{community_code}/crime-summary", tags=["community CRUD"])
def community_crime_summary(
    community_code: int,
    db: sqlite3.Connection = Depends(get_db),
):
    community = crud.get_community(db, community_code)
    if community is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community code {community_code} was not found.",
        )

    crime_count = int(
        db.execute(
            "SELECT COUNT(*) FROM crime WHERE community_code = ?",
            (community_code,),
        ).fetchone()[0]
    )
    arrest_count = int(
        db.execute(
            "SELECT COUNT(*) FROM crime "
            "WHERE community_code = ? AND arrest = 1",
            (community_code,),
        ).fetchone()[0]
    )

    return {
        "community_code": community["community_code"],
        "community_name": community["community_name"],
        "crime_count": crime_count,
        "arrest_count": arrest_count,
        "arrest_rate": round(arrest_count / crime_count * 100, 2)
        if crime_count
        else 0.0,
    }


# ---------------------------------------------------------------------------
# Dashboard JSON and report export
# ---------------------------------------------------------------------------


@app.get("/api/dashboard/insights", tags=["dashboard"])
def dashboard_insights():
    """Return KPIs, insights, and summary tables as JSON."""
    return get_insights_payload()


@app.get("/dashboard/export", tags=["dashboard"])
def export_dashboard():
    """Download a PNG report containing charts and executive insights."""
    context = build_dashboard_context()
    report_path = build_report_image(context)
    return FileResponse(
        path=report_path,
        media_type="image/png",
        filename=Path(report_path).name,
    )


@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",
        "database": str(DB_PATH),
        "database_exists": DB_PATH.exists(),
    }
