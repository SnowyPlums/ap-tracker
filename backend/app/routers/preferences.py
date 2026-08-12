from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_user
from ..db import get_db
from ..models import User, UserPreference
from ..schemas import PlayerBoxPreferences


router = APIRouter(prefix="/api/v1/preferences", tags=["preferences"])
BOX_KEYS = ["checks", "hints", "deaths", "completion", "actions"]
DEFAULT_PREFERENCES = {"order": BOX_KEYS, "visible": ["checks", "hints"]}


def clean_order(order: list[str]) -> list[str]:
    cleaned = [key for key in order if key in BOX_KEYS]
    cleaned.extend(key for key in BOX_KEYS if key not in cleaned)
    return cleaned


def clean_preferences(payload: PlayerBoxPreferences) -> dict:
    visible = [key for key in payload.visible if key in BOX_KEYS]
    return {"order": clean_order(payload.order), "visible": visible}


@router.get("/player-boxes", response_model=PlayerBoxPreferences)
async def get_player_boxes(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    preference = await db.get(UserPreference, user.id)
    if not preference:
        return DEFAULT_PREFERENCES
    payload = PlayerBoxPreferences.model_validate({**DEFAULT_PREFERENCES, **(preference.player_boxes or {})})
    return clean_preferences(payload)


@router.put("/player-boxes", response_model=PlayerBoxPreferences)
async def save_player_boxes(
    payload: PlayerBoxPreferences,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    clean = clean_preferences(payload)
    preference = await db.get(UserPreference, user.id)
    if preference:
        preference.player_boxes = clean
    else:
        db.add(UserPreference(user_id=user.id, player_boxes=clean))
    await db.commit()
    return clean
