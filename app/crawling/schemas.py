from pydantic import BaseModel
from typing import Optional

class CrawlResponse(BaseModel):
    success: bool
    message: str

class IdolGroupData(BaseModel):
    name: str
    original_image_url: Optional[str] = None
