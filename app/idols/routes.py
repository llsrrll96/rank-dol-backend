from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import List, Optional
from .schemas import IdolGroupResponse
from ..common.storage import get_supabase_client, upload_file_to_storage, delete_image_from_storage

router = APIRouter(prefix="/api/idols", tags=["Idols"])

@router.get("", response_model=List[IdolGroupResponse])
def get_idols():
    client = get_supabase_client()
    try:
        resp = client.table("idol_groups").select("*").execute()
        return resp.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{id}", response_model=IdolGroupResponse)
def get_idol(id: int):
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

@router.post("", response_model=IdolGroupResponse)
async def create_idol(name: str = Form(...), image: Optional[UploadFile] = File(None)):
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

@router.put("/{id}", response_model=IdolGroupResponse)
async def update_idol(id: int, name: Optional[str] = Form(None), image: Optional[UploadFile] = File(None)):
    client = get_supabase_client()
    
    # Fetch existing
    existing = client.table("idol_groups").select("*").eq("id", id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Idol group not found")
    
    idol = existing.data[0]
    
    updates = {}
    if name is not None and name != idol["name"]:
        # Check duplicate
        dup = client.table("idol_groups").select("id").eq("name", name).execute()
        if dup.data:
            raise HTTPException(status_code=400, detail="Idol group with this name already exists")
        updates["name"] = name
        
    group_name_for_image = name if name else idol["name"]
        
    if image and image.filename:
        # Upload new image
        new_image_url = await upload_file_to_storage(client, image, group_name_for_image)
        if new_image_url:
            updates["image_url"] = new_image_url
            
            # Optionally delete old image if it exists and is from our storage
            if idol.get("image_url"):
                await delete_image_from_storage(client, idol["image_url"])
                
    if not updates:
        return idol
        
    try:
        resp = client.table("idol_groups").update(updates).eq("id", id).execute()
        return resp.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{id}")
async def delete_idol(id: int):
    client = get_supabase_client()
    
    existing = client.table("idol_groups").select("*").eq("id", id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Idol group not found")
        
    idol = existing.data[0]
    
    try:
        client.table("idol_groups").delete().eq("id", id).execute()
        
        # Delete image from storage
        if idol.get("image_url"):
            await delete_image_from_storage(client, idol["image_url"])
            
        return {"success": True, "message": "Idol group deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
