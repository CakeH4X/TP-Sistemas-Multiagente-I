"""GET/PUT /preferences/{user_id} — user preference CRUD."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from memory.persistent import DEFAULT_PREFERENCES, PersistentMemory

logger = logging.getLogger(__name__)
router = APIRouter(tags=["preferences"])


class PreferencesUpdate(BaseModel):
    """Partial update payload — any subset of preference keys may be supplied."""

    preferences: dict[str, Any] = Field(
        default_factory=dict,
        description="Mapping of preference key to value. Unknown keys are accepted.",
    )


class PreferencesResponse(BaseModel):
    user_id: str
    preferences: dict[str, Any]


@router.get("/preferences/{user_id}", response_model=PreferencesResponse)
async def get_preferences(user_id: str) -> PreferencesResponse:
    """Return merged preferences (defaults + persisted overrides)."""
    store = PersistentMemory()
    return PreferencesResponse(
        user_id=user_id,
        preferences=store.get_user_preferences(user_id),
    )


@router.put("/preferences/{user_id}", response_model=PreferencesResponse)
async def update_preferences(
    user_id: str, payload: PreferencesUpdate
) -> PreferencesResponse:
    """Upsert one or more preferences. Returns the resulting merged set."""
    if not payload.preferences:
        raise HTTPException(
            status_code=400, detail="At least one preference must be supplied."
        )

    store = PersistentMemory()
    for key, value in payload.preferences.items():
        store.set_user_preference(user_id, key, value)

    return PreferencesResponse(
        user_id=user_id,
        preferences=store.get_user_preferences(user_id),
    )


@router.get("/preferences/{user_id}/defaults")
async def get_default_preferences(user_id: str) -> dict[str, Any]:
    """Return the default preferences (useful for the UI to render reset options)."""
    return dict(DEFAULT_PREFERENCES)
