import os
import httpx
from supabase import create_client, Client
from typing import List, Optional
from .schemas import IdolGroupData
from fastapi import UploadFile
def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        print("Warning: SUPABASE_URL or SUPABASE_KEY not found in environment.")
    return create_client(url, key)

async def upload_image_to_storage(client: Client, image_url: str, group_name: str) -> str:
    """
    Downloads an image from original URL and uploads to Supabase Storage.
    Returns the public URL of the uploaded image.
    """
    if not image_url:
        return None
        
    import hashlib
    
    bucket_name = os.environ.get("SUPABASE_BUCKET", "images")
    file_extension = image_url.split(".")[-1]
    # Remove query params from extension if they exist
    file_extension = file_extension.split("?")[0].split("#")[0]
    if len(file_extension) > 5 or not file_extension:
        file_extension = "jpg" # default fallback
        
    safe_group_name = hashlib.md5(group_name.encode('utf-8')).hexdigest()
    file_name = f"{safe_group_name}.{file_extension}"
    file_path = f"idol_groups/{file_name}"
    
    try:
        if image_url.startswith("//"):
            image_url = "https:" + image_url
        elif image_url.startswith("/"):
            image_url = "https://azito.kr" + image_url
            
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(image_url)
            response.raise_for_status()
            image_data = response.content
            
        # Uploading to Supabase
        # .upload() expects a byte block
        res = client.storage.from_(bucket_name).upload(
            file=image_data,
            path=file_path,
            file_options={"content-type": f"image/{file_extension}"}
        )
        
        # Get public url
        public_url = client.storage.from_(bucket_name).get_public_url(file_path)
        return public_url
    except Exception as e:
        print(f"Failed to upload image for {group_name}: {e}")
        return image_url # fallback to original

async def upload_file_to_storage(client: Client, file: UploadFile, group_name: str) -> Optional[str]:
    if not file or not file.filename:
        return None
        
    import hashlib
    bucket_name = os.environ.get("SUPABASE_BUCKET", "images")
    
    file_extension = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    safe_group_name = hashlib.md5(group_name.encode('utf-8')).hexdigest()
    file_name = f"{safe_group_name}.{file_extension}"
    file_path = f"idol_groups/{file_name}"
    
    try:
        content = await file.read()
        res = client.storage.from_(bucket_name).upload(
            file=content,
            path=file_path,
            file_options={"content-type": file.content_type, "x-upsert": "true"}
        )
        return client.storage.from_(bucket_name).get_public_url(file_path)
    except Exception as e:
        print(f"Failed to upload file for {group_name}: {e}")
        return None

async def delete_image_from_storage(client: Client, image_url: str):
    if not image_url:
        return
        
    bucket_name = os.environ.get("SUPABASE_BUCKET", "images")
    prefix = f"/object/public/{bucket_name}/"
    
    try:
        if prefix in image_url:
            file_path = image_url.split(prefix)[-1]
            client.storage.from_(bucket_name).remove([file_path])
            print(f"Deleted image from storage: {file_path}")
    except Exception as e:
        print(f"Failed to delete image {image_url}: {e}")

async def save_crawled_data(groups: List[IdolGroupData]):
    """
    Saves the data and uploaded new image URL to the database.
    """
    if not groups:
        print("No groups to save.")
        return
        
    client = get_supabase_client()
    
    try:
        existing_resp = client.table("idol_groups").select("name").execute()
        existing_names = {row["name"] for row in existing_resp.data}
    except Exception as e:
        print(f"Failed to fetch existing groups: {e}")
        existing_names = set()
    
    for group in groups:
        if group.name in existing_names:
            print(f"Skipping duplicate: {group.name}")
            continue
            
        # 1. Upload Image
        new_image_url = None
        if group.original_image_url:
            new_image_url = await upload_image_to_storage(client, group.original_image_url, group.name)
            
        # 2. Insert DB
        record = {
            "name": group.name,
            "image_url": new_image_url,
        }
        
        try:
            resp = client.table("idol_groups").insert(record).execute()
            print(f"Saved: {group.name}")
        except Exception as e:
            print(f"Database insertion failed for {group.name}: {e}")
