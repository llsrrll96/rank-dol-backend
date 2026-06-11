import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends

from ..auth.schemas import UserResponse
from ..common.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """내 정보 조회 (JWT 인증 필요)"""
    return UserResponse(
        id=str(current_user["id"]),
        email=current_user.get("email", ""),
        username=current_user["username"],
        role=current_user.get("role", "USER"),
    )
