"""Template: Pydantic request/response schemas for one resource."""

from datetime import datetime

from pydantic import BaseModel, Field


class ResourceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ResourceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)


class ResourceOut(BaseModel):
    id: int
    title: str
    created_at: datetime

    model_config = {"from_attributes": True}
