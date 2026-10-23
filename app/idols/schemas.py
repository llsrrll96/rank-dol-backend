from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class IdolResponse(BaseModel):
    id: int
    group_id: Optional[int] = None
    name: str
    image_url: Optional[str] = None
    is_preset: bool = True
    source_url: Optional[str] = None
    # 크롤링 등으로 얻은 부가 정보(컬러, 마크 등). 필드가 늘어도 컬럼 추가 없이 담는다.
    meta: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


class IdolPageResponse(BaseModel):
    items: List[IdolResponse]
    total: int
    page: int
    page_size: int
