from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import List, Optional
from .schemas import IdolGroupResponse
from ..common.storage import (
    get_supabase_client,
    upload_file_to_storage,
    delete_image_from_storage,
    delete_images_from_storage,
)
from ..common.deps import require_admin

router = APIRouter(prefix="/api/idol-groups", tags=["Idol Groups"])


@router.get("", response_model=List[IdolGroupResponse])
def get_idol_groups():
    client = get_supabase_client()
    try:
        resp = client.table("idol_groups").select("*").execute()
        return resp.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{id}", response_model=IdolGroupResponse)
def get_idol_group(id: int):
    client = get_supabase_client()
    try:
        resp = client.table("idol_groups").select("*").eq("id", id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Idol group not found")
        return resp.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=IdolGroupResponse, dependencies=[Depends(require_admin)])
async def create_idol_group(name: str = Form(...), image: Optional[UploadFile] = File(None)):
    client = get_supabase_client()

    # Check if duplicate name physically
    existing = client.table("idol_groups").select("id").eq("name", name).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Idol group with this name already exists")

    image_url = None
    if image and image.filename:
        image_url = await upload_file_to_storage(client, image, name)

    record = {
        "name": name,
        "image_url": image_url,
    }

    try:
        resp = client.table("idol_groups").insert(record).execute()
        return resp.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{id}", response_model=IdolGroupResponse, dependencies=[Depends(require_admin)])
async def update_idol_group(id: int, name: Optional[str] = Form(None), image: Optional[UploadFile] = File(None)):
    client = get_supabase_client()

    # Fetch existing
    existing = client.table("idol_groups").select("*").eq("id", id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Idol group not found")

    group = existing.data[0]

    updates = {}
    if name is not None and name != group["name"]:
        # Check duplicate
        dup = client.table("idol_groups").select("id").eq("name", name).execute()
        if dup.data:
            raise HTTPException(status_code=400, detail="Idol group with this name already exists")
        updates["name"] = name

    group_name_for_image = name if name else group["name"]

    if image and image.filename:
        # Upload new image
        new_image_url = await upload_file_to_storage(client, image, group_name_for_image)
        if new_image_url:
            updates["image_url"] = new_image_url

            # Optionally delete old image if it exists and is from our storage
            if group.get("image_url"):
                await delete_image_from_storage(client, group["image_url"])

    if not updates:
        return group

    try:
        resp = client.table("idol_groups").update(updates).eq("id", id).execute()
        return resp.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{id}", dependencies=[Depends(require_admin)])
async def delete_idol_group(id: int):
    client = get_supabase_client()

    existing = client.table("idol_groups").select("*").eq("id", id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Idol group not found")

    group = existing.data[0]

    try:
        # 기본 제공(is_preset) 아이돌은 그룹과 함께 지운다.
        # 사용자가 직접 만든 아이돌은 FK(on delete set null)에 따라 그룹만 해제된다.
        members = (
            client.table("idols").select("id, image_url")
            .eq("group_id", id).eq("is_preset", True).execute()
        )
        member_images = [m.get("image_url") for m in (members.data or [])]
        if members.data:
            client.table("idols").delete().eq("group_id", id).eq("is_preset", True).execute()

        client.table("idol_groups").delete().eq("id", id).execute()

        # Storage 정리는 DB 삭제가 끝난 뒤에 한다 (실패해도 데이터는 일관되게 유지)
        await delete_images_from_storage(client, member_images + [group.get("image_url")])

        return {"success": True, "message": "Idol group deleted", "deleted_idols": len(member_images)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
