"""Pydantic v2 request and response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CommunityFields(BaseModel):
    """Fields shared by create and replace operations."""

    community_name: str = Field(..., min_length=2, max_length=120)
    population: int | None = Field(default=None, ge=0)
    area_sqmile: float | None = Field(default=None, ge=0)
    area_sqkm: float | None = Field(default=None, ge=0)
    density_per_sqmi: float | None = Field(default=None, ge=0)
    density_per_sqkm: float | None = Field(default=None, ge=0)


class CommunityCreate(CommunityFields):
    community_code: int = Field(..., gt=0, description="Unique community-area code")


class CommunityReplace(CommunityFields):
    """Full update payload for PUT. The code comes from the URL."""


class CommunityPatch(BaseModel):
    """Partial update payload for PATCH. Every field is optional."""

    community_name: str | None = Field(default=None, min_length=2, max_length=120)
    population: int | None = Field(default=None, ge=0)
    area_sqmile: float | None = Field(default=None, ge=0)
    area_sqkm: float | None = Field(default=None, ge=0)
    density_per_sqmi: float | None = Field(default=None, ge=0)
    density_per_sqkm: float | None = Field(default=None, ge=0)


class CommunityRead(CommunityFields):
    community_code: int

    model_config = ConfigDict(from_attributes=True)
