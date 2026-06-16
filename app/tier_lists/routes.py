from fastapi import APIRouter, HTTPException, Query, status
from typing import List
from passlib.context import CryptContext

from .schemas import (
    TierListCreate,
    TierListUpdate,
    TierListResponse,
    TierListPageResponse,
    TierItem,
    DEFAULT_TIERS,
)
from ..common.storage import get_supabase_client

router = APIRouter(prefix="/api/tier-lists", tags=["Tier Lists"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    if not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    if not password:
        return None
    return pwd_context.hash(password)


@router.get("", response_model=TierListPageResponse)
def get_tier_lists(
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: int = Query(50, ge=1, le=100, description="페이지 크기"),
):
    """티어 리스트 전체 목록 조회 (페이징, 생성일 내림차순)"""
    client = get_supabase_client()
    try:
        # 전체 개수 조회
        count_resp = (
            client.table("tier_lists")
            .select("id", count="exact")
            .execute()
        )
        total = count_resp.count if count_resp.count is not None else 0

        # 페이징 조회
        offset = (page - 1) * page_size
        resp = (
            client.table("tier_lists")
            .select("*")
            .order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )

        return TierListPageResponse(
            items=resp.data,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{id}", response_model=TierListResponse)
def get_tier_list(id: int):
    """특정 티어 리스트 상세 조회"""
    client = get_supabase_client()
    try:
        resp = client.table("tier_lists").select("*").eq("id", id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Tier list not found")
        return resp.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=TierListResponse, status_code=201)
def create_tier_list(body: TierListCreate):
    """티어 리스트 생성. tiers를 보내지 않으면 기본 S/A/B/C/D/E 세트가 적용됩니다."""
    client = get_supabase_client()

    # tiers가 없으면 기본 티어 세트 사용
    tiers_data = (
        [t.model_dump() for t in body.tiers]
        if body.tiers is not None
        else DEFAULT_TIERS
    )

    record = {
        "title": body.title,
        "tiers": tiers_data,
    }

    if body.password:
        record["password"] = get_password_hash(body.password)
    if body.creator_id:
        record["creator_id"] = body.creator_id

    try:
        resp = client.table("tier_lists").insert(record).execute()
        return resp.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{id}", response_model=TierListResponse)
def update_tier_list(id: int, body: TierListUpdate):
    """기존 티어 리스트 수정"""
    client = get_supabase_client()

    # 존재 여부 확인
    existing = client.table("tier_lists").select("*").eq("id", id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Tier list not found")
        
    db_record = existing.data[0]
    
    # 권한 검증 - 비밀번호가 설정된 표우
    if db_record.get("password"):
        if not body.password or not verify_password(body.password, db_record["password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="비밀번호가 일치하지 않거나 누락되었습니다."
            )

    updates = {}
    if body.title is not None:
        updates["title"] = body.title
    if body.tiers is not None:
        updates["tiers"] = [t.model_dump() for t in body.tiers]

    if not updates:
        # 삭제된 비밀번호 필드가 반환되지 않도록 필터링
        db_record.pop("password", None)
        return db_record

    try:
        resp = (
            client.table("tier_lists")
            .update(updates)
            .eq("id", id)
            .execute()
        )
        return resp.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{id}")
def delete_tier_list(id: int, password: str = Query(None, description="삭제를 위한 비밀번호")):
    """특정 티어 리스트 삭제"""
    client = get_supabase_client()

    existing = client.table("tier_lists").select("*").eq("id", id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Tier list not found")

    db_record = existing.data[0]
    
    # 권한 검증
    if db_record.get("password"):
        if not password or not verify_password(password, db_record["password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="비밀번호가 일치하지 않거나 누락되었습니다."
            )

    try:
        client.table("tier_lists").delete().eq("id", id).execute()
        return {"success": True, "message": "Tier list deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
