from pydantic import BaseModel
from typing import Any, Dict, Optional

class CrawlResponse(BaseModel):
    success: bool
    message: str

class IdolGroupData(BaseModel):
    name: str
    original_image_url: Optional[str] = None
    source_url: Optional[str] = None  # 원본 그룹 페이지 경로 (예: /team/222)

class IdolData(BaseModel):
    name: str
    original_image_url: Optional[str] = None
    source_url: Optional[str] = None  # 원본 아티스트 페이지 경로 (예: /artist/115)
    meta: Dict[str, Any] = {}         # 부가 정보 (컬러, 마크 등). 확장 시 키만 추가하면 된다.
