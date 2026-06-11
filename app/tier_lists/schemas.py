from pydantic import BaseModel
from typing import Optional, List

# ── Default Tier Set ──

DEFAULT_TIERS = [
    {"label": "S", "color": "#FF7F7F", "idol_group_ids": []},
    {"label": "A", "color": "#FFBF7F", "idol_group_ids": []},
    {"label": "B", "color": "#FFDF7F", "idol_group_ids": []},
    {"label": "C", "color": "#FFFF7F", "idol_group_ids": []},
    {"label": "D", "color": "#BFFF7F", "idol_group_ids": []},
    {"label": "E", "color": "#7FFFFF", "idol_group_ids": []},
]


class TierItem(BaseModel):
    label: str
    color: str
    idol_group_ids: List[int] = []


class TierListCreate(BaseModel):
    title: str
    tiers: Optional[List[TierItem]] = None  # None이면 기본 티어 세트 사용


class TierListUpdate(BaseModel):
    title: Optional[str] = None
    tiers: Optional[List[TierItem]] = None


class TierListResponse(BaseModel):
    id: int
    title: str
    tiers: List[TierItem]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TierListPageResponse(BaseModel):
    items: List[TierListResponse]
    total: int
    page: int
    page_size: int
