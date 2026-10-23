from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from typing import Optional
from .schemas import IdolResponse, IdolPageResponse
from ..common.storage import (
    get_supabase_client,
    upload_file_to_storage,
    delete_image_from_storage,
)
from ..common.deps import require_admin

router = APIRouter(prefix="/api/idols", tags=["Idols"])

NAME_MAX_LENGTH = 100


def _escape_like(value: str) -> str:
    """LIKE 패턴에서 특수 의미를 갖는 문자를 이스케이프한다."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name or len(name) > NAME_MAX_LENGTH:
        raise HTTPException(status_code=400, detail=f"이름은 1자 이상 {NAME_MAX_LENGTH}자 이하여야 합니다.")
    return name


def _image_folder(group_id: Optional[int]) -> str:
    return f"idols/{group_id}" if group_id is not None else "idols/ungrouped"


def _ensure_group_exists(client, group_id: int):
    resp = client.table("idol_groups").select("id").eq("id", group_id).execute()
    if not resp.data:
        raise HTTPException(status_code=400, detail="Idol group not found")


def _name_taken(client, group_id: Optional[int], name: str, exclude_id: Optional[int] = None) -> bool:
    q = client.table("idols").select("id").eq("name", name).eq("is_preset", True)
    q = q.eq("group_id", group_id) if group_id is not None else q.is_("group_id", "null")
    rows = q.execute().data or []
    return any(r["id"] != exclude_id for r in rows)


@router.get("", response_model=IdolPageResponse)
def get_idols(
    group_id: Optional[int] = Query(None, description="특정 그룹의 아이돌만 조회"),
    q: Optional[str] = Query(None, max_length=100, description="이름 검색 (부분 일치)"),
    is_preset: bool = Query(True, description="기본 제공 아이돌만(true) / 사용자 생성만(false)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    client = get_supabase_client()
    try:
        query = client.table("idols").select("*", count="exact").eq("is_preset", is_preset)
        if group_id is not None:
            query = query.eq("group_id", group_id)
        if q and q.strip():
            query = query.ilike("name", f"%{_escape_like(q.strip())}%")

        offset = (page - 1) * page_size
        resp = query.order("id").range(offset, offset + page_size - 1).execute()
        return IdolPageResponse(
            items=resp.data,
            total=resp.count if resp.count is not None else len(resp.data),
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{id}", response_model=IdolResponse)
def get_idol(id: int):
    client = get_supabase_client()
    try:
        resp = client.table("idols").select("*").eq("id", id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not resp.data:
        raise HTTPException(status_code=404, detail="Idol not found")
    return resp.data[0]


@router.post("", response_model=IdolResponse, dependencies=[Depends(require_admin)])
async def create_idol(
    name: str = Form(...),
    group_id: Optional[int] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    client = get_supabase_client()
    name = _clean_name(name)

    if group_id is not None:
        _ensure_group_exists(client, group_id)
    if _name_taken(client, group_id, name):
        raise HTTPException(status_code=409, detail="같은 그룹에 같은 이름의 아이돌이 이미 있습니다.")

    image_url = None
    if image and image.filename:
        image_url = await upload_file_to_storage(client, image, name, folder=_image_folder(group_id))
        if not image_url:
            raise HTTPException(status_code=500, detail="이미지 업로드에 실패했습니다.")

    record = {"name": name, "group_id": group_id, "image_url": image_url, "is_preset": True}
    try:
        resp = client.table("idols").insert(record).execute()
        return resp.data[0]
    except Exception as e:
        # DB 저장이 실패하면 방금 올린 이미지가 고아 파일이 되지 않게 지운다
        if image_url:
            await delete_image_from_storage(client, image_url)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{id}", response_model=IdolResponse, dependencies=[Depends(require_admin)])
async def update_idol(
    id: int,
    name: Optional[str] = Form(None),
    group_id: Optional[int] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    client = get_supabase_client()

    existing = client.table("idols").select("*").eq("id", id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Idol not found")
    idol = existing.data[0]

    new_name = _clean_name(name) if name is not None else idol["name"]
    new_group_id = group_id if group_id is not None else idol.get("group_id")

    updates = {}
    if new_name != idol["name"]:
        updates["name"] = new_name
    if new_group_id != idol.get("group_id"):
        _ensure_group_exists(client, new_group_id)
        updates["group_id"] = new_group_id
    if updates and _name_taken(client, new_group_id, new_name, exclude_id=id):
        raise HTTPException(status_code=409, detail="같은 그룹에 같은 이름의 아이돌이 이미 있습니다.")

    old_image_url = idol.get("image_url")
    new_image_url = None
    if image and image.filename:
        new_image_url = await upload_file_to_storage(
            client, image, new_name, folder=_image_folder(new_group_id)
        )
        if not new_image_url:
            raise HTTPException(status_code=500, detail="이미지 업로드에 실패했습니다.")
        updates["image_url"] = new_image_url

    if not updates:
        return idol

    try:
        resp = client.table("idols").update(updates).eq("id", id).execute()
    except Exception as e:
        if new_image_url:
            await delete_image_from_storage(client, new_image_url)
        raise HTTPException(status_code=500, detail=str(e))

    # DB 갱신이 성공한 뒤에 이전 이미지를 지운다
    if new_image_url and old_image_url:
        await delete_image_from_storage(client, old_image_url)
    return resp.data[0]


@router.delete("/{id}", dependencies=[Depends(require_admin)])
async def delete_idol(id: int):
    client = get_supabase_client()

    existing = client.table("idols").select("*").eq("id", id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Idol not found")
    idol = existing.data[0]

    try:
        client.table("idols").delete().eq("id", id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if idol.get("image_url"):
        await delete_image_from_storage(client, idol["image_url"])
    return {"success": True, "message": "Idol deleted"}
