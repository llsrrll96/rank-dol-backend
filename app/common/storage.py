import os
import httpx
from supabase import create_client, Client
from typing import Optional
from fastapi import UploadFile

def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        print("Warning: SUPABASE_URL or SUPABASE_KEY not found in environment.")
    return create_client(url, key)

async def upload_image_to_storage(client: Client, image_url: str, group_name: str) -> str:
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
        return image_url

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
