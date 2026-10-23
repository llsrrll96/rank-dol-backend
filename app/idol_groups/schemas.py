from pydantic import BaseModel
from typing import Optional


class IdolGroupResponse(BaseModel):
    id: int
    name: str
    image_url: Optional[str] = None
    source_url: Optional[str] = None
    members_crawled_at: Optional[str] = None
    created_at: Optional[str] = None
