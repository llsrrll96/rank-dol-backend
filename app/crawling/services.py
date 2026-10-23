import logging
from typing import Any, Dict, List
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

async def save_crawled_data(groups: List[IdolGroupData]) -> Dict[str, Any]:
    """
    새 그룹은 저장하고, 이미 있는 그룹은 건너뛴다.
    단, 기존 그룹에 원본 주소(source_url)가 비어 있으면 그 값만 채운다 (이름·이미지는 건드리지 않음).
    이미지 업로드에 실패한 새 그룹은 이미지 없이 저장하고 failed 목록에 기록한다
    (외부 사이트 원본 주소가 DB에 들어가는 것을 막기 위해 image_url 은 비워 둔다).
    다음 크롤링 때 이미지가 비어 있는 기존 그룹은 이미지를 다시 시도한다.

    Returns: {"added", "updated", "skipped": int, "failed": [{"name", "reason"}], "crawled_total": int,
              "added_items", "updated_items", "skipped_items": [str]}  (items 는 화면에 자세히 보여주기 위한 목록)
    """
    result: Dict[str, Any] = {
        "added": 0, "updated": 0, "skipped": 0, "failed": [], "crawled_total": len(groups),
        "added_items": [], "updated_items": [], "skipped_items": [],
    }

    if not groups:
        logger.info("No groups to save.")
        return result

    client = get_supabase_client()

    # 기존 그룹 조회에 실패했는데 그대로 진행하면 전부 새 그룹으로 보고 중복 저장하므로 중단한다.
    try:
        existing_resp = client.table("idol_groups").select("id, name, source_url").execute()
        existing = {row["name"]: row for row in existing_resp.data}
    except Exception as e:
        logger.error(f"Failed to fetch existing groups: {e}")
        raise RuntimeError(f"기존 그룹 목록을 불러오지 못해 크롤링을 중단했습니다: {e}")

    for group in groups:
        row = existing.get(group.name)
        if row is not None:
            # 이미 있는 그룹: 비어 있는 값(원본 주소, 이미지)만 보완하고 이름·기존 값은 건드리지 않는다
            updates: Dict[str, Any] = {}
            if group.source_url and not row.get("source_url"):
                updates["source_url"] = group.source_url
            if group.original_image_url and not row.get("image_url"):
                filled_image = await upload_image_to_storage(client, group.original_image_url, group.name)
                if filled_image:
                    updates["image_url"] = filled_image
                else:
                    result["failed"].append({
                        "name": group.name,
                        "reason": f"이미지 업로드 실패 (원본 이미지: {group.original_image_url})",
                    })
            if updates:
                try:
                    client.table("idol_groups").update(updates).eq("id", row["id"]).execute()
                    row.update(updates)
                    result["updated"] += 1
                    filled = []
                    if "source_url" in updates:
                        filled.append(f"원본 주소 {updates['source_url']}")
                    if "image_url" in updates:
                        filled.append("이미지")
                    result["updated_items"].append(f"{group.name} → 채움: {', '.join(filled)}")
                    logger.info(f"Filled {list(updates)}: {group.name}")
                except Exception as e:
                    logger.error(f"Failed to fill {list(updates)} for {group.name}: {e}")
                    result["failed"].append({"name": group.name, "reason": f"보완 값 저장 실패: {str(e)[:150]}"})
                continue
            logger.info(f"Skipping duplicate: {group.name}")
            result["skipped"] += 1
            result["skipped_items"].append(group.name)
            continue

        # 1. Upload Image (소스에 이미지가 없는 그룹은 이미지 없이 저장).
        #    업로드에 실패해도 그룹 자체는 이미지 없이 저장한다(외부 사이트 주소는 넣지 않는다).
        new_image_url = None
        if group.original_image_url:
            new_image_url = await upload_image_to_storage(client, group.original_image_url, group.name)
            if not new_image_url:
                logger.error(f"Image upload failed, saving group without image: {group.name}")
                result["failed"].append({
                    "name": group.name,
                    "reason": f"이미지 업로드 실패 — 이미지 없이 저장됨 (원본 이미지: {group.original_image_url})",
                })

        # 2. Insert DB
        record = {
            "name": group.name,
            "image_url": new_image_url,
            "source_url": group.source_url,
        }

        try:
            resp = client.table("idol_groups").insert(record).execute()
            existing[group.name] = resp.data[0] if resp.data else record  # 같은 이름이 또 나와도 중복 저장 방지
            result["added"] += 1
            result["added_items"].append(
                f"{group.name} (원본 주소 {group.source_url or '없음'}, 이미지 {'있음' if new_image_url else '없음'})"
            )
            logger.info(f"Saved: {group.name}")
        except Exception as e:
            logger.error(f"Database insertion failed for {group.name}: {e}")
            result["failed"].append({"name": group.name, "reason": f"DB 저장 실패: {str(e)[:150]}"})

    return result
