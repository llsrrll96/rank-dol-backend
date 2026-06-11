import logging
from typing import List
from .schemas import IdolGroupData
from ..common.storage import get_supabase_client, upload_image_to_storage

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

async def save_crawled_data(groups: List[IdolGroupData]):
    """
    Saves the data and uploaded new image URL to the database.
    """
    if not groups:
        logger.info("No groups to save.")
        return
        
    client = get_supabase_client()
    
    try:
        existing_resp = client.table("idol_groups").select("name").execute()
        existing_names = {row["name"] for row in existing_resp.data}
    except Exception as e:
        logger.error(f"Failed to fetch existing groups: {e}")
        existing_names = set()
    
    for group in groups:
        if group.name in existing_names:
            logger.info(f"Skipping duplicate: {group.name}")
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
            logger.info(f"Saved: {group.name}")
        except Exception as e:
            logger.error(f"Database insertion failed for {group.name}: {e}")
