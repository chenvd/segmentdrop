from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EmbySettingsInput(BaseModel):
    server_url: str = ""
    api_key: str | None = None


class TheIntroDBSettingsInput(BaseModel):
    api_key: str | None = None


class SettingsInput(BaseModel):
    emby: EmbySettingsInput | None = None
    theintrodb: TheIntroDBSettingsInput | None = None


class SegmentInput(BaseModel):
    type: Literal["intro", "recap", "credits", "preview"]
    start_ms: int | None = Field(default=None, ge=0, le=21_600_000)
    end_ms: int | None = Field(default=None, ge=0, le=21_600_000)


class SubmitMedia(BaseModel):
    type: Literal["movie", "episode"]
    tmdb_id: int = Field(gt=0)
    season: int | None = Field(default=None, ge=0)
    episode: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)


class SubmitInput(BaseModel):
    session_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    media: SubmitMedia
    segment: SegmentInput
