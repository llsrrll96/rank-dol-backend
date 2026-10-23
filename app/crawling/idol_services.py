import asyncio
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from .idol_crawler import (
    CrawlBlockedError,
    crawl_group_members,
    group_delay_seconds,
    image_delay_seconds,
    make_http_client,
)
from ..common.storage import get_supabase_client, upload_image_to_storage

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

ProgressCallback = Callable[[int, int, str], None]

KST = timezone(timedelta(hours=9))   # "하루"의 기준은 한국 시간
DEFAULT_DAILY_LIMIT = 30
GROUP_COLUMNS = "id, name, source_url, members_crawled_at"


def _image_folder(group_id: int) -> str:
    return f"idols/{group_id}"


def daily_limit() -> int:
    """하루에 멤버를 수집할 그룹 수 (IDOL_CRAWL_DAILY_LIMIT, 기본 30)."""
    try:
        return max(1, int(os.environ.get("IDOL_CRAWL_DAILY_LIMIT", DEFAULT_DAILY_LIMIT)))
    except ValueError:
        return DEFAULT_DAILY_LIMIT


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _kst_date(value: Optional[str]):
    dt = _parse_ts(value)
    return dt.astimezone(KST).date() if dt else None


def _load_groups(client) -> List[Dict[str, Any]]:
    """원본 주소(source_url)가 있는 그룹들을 id 순으로 가져온다."""
    try:
        resp = (
            client.table("idol_groups").select(GROUP_COLUMNS)
            .not_.is_("source_url", "null").order("id").execute()
        )
    except Exception as e:
        raise RuntimeError(
            f"그룹 목록을 불러오지 못했습니다(idol_groups.members_crawled_at 컬럼이 있는지 확인하세요): {e}"
        )
    return resp.data or []


def _summarize(groups: List[Dict[str, Any]]) -> Dict[str, Any]:
    limit = daily_limit()
    today = datetime.now(KST).date()
    done = [g for g in groups if g.get("members_crawled_at")]
    pending = [g for g in groups if not g.get("members_crawled_at")]
    today_done = sum(1 for g in done if _kst_date(g["members_crawled_at"]) == today)
    remaining_today = max(0, limit - today_done)
    return {
        "total": len(groups),
        "done": len(done),
        "pending": len(pending),
        "today_done": today_done,
        "daily_limit": limit,
        "remaining_today": remaining_today,
        "days_left": math.ceil(len(pending) / limit) if pending else 0,
        "next_groups": [g["name"] for g in pending[:5]],
    }


def get_idol_crawl_progress() -> Dict[str, Any]:
    """아이돌 크롤링 현황: 어디까지 했는지, 오늘 몇 개 했는지, 앞으로 며칠 남았는지."""
    return _summarize(_load_groups(get_supabase_client()))


async def save_crawled_idols(
    group_id: Optional[int] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """원본 주소(source_url)가 있는 그룹들의 멤버를 크롤링해 idols 테이블에 저장한다.

    - 전체 실행: 아직 수집하지 않은 그룹(members_crawled_at 이 비어 있는 그룹)만, 하루 상한까지
      id 순서로 처리한다. 다음 실행은 이어서 남은 그룹부터 처리한다.
    - group_id 지정: 상한과 무관하게 그 그룹 하나만 다시 수집한다(오늘 처리량에는 포함된다).
    - 새 멤버(같은 그룹 안에서 이름이 없는 멤버)만 추가한다. 이미 있는 멤버는 건드리지 않되,
      비어 있는 값(source_url, meta, image)만 채운다.
    - 그룹 하나가 실패해도 나머지는 계속한다. 사이트가 접근을 거절하면 즉시 중단하고
      그때까지의 결과를 돌려준다.
    - 요청 사이에는 무작위 간격으로 쉰다.

    Returns: {"added", "updated", "skipped", "failed": [{"name","reason"}],
              "groups_total"(이번 실행 대상), "groups_done", "groups_without_members",
              "progress"(전체 현황), "notice"?, "error"?}
    """
    client = get_supabase_client()
    all_groups = _load_groups(client)

    if group_id is not None:
        targets = [g for g in all_groups if g["id"] == group_id]
        if not targets:
            raise ValueError("해당 그룹에는 원본 주소(source_url)가 없습니다. 먼저 '그룹 크롤링'을 실행해 주세요.")
    else:
        if not all_groups:
            raise RuntimeError("원본 주소(source_url)가 있는 그룹이 없습니다. 먼저 '그룹 크롤링'을 실행해 주세요.")
        summary = _summarize(all_groups)
        pending = [g for g in all_groups if not g.get("members_crawled_at")]
        targets = pending[: summary["remaining_today"]]

    result: Dict[str, Any] = {
        "added": 0, "updated": 0, "skipped": 0, "failed": [],
        "added_items": [], "updated_items": [],
        "groups_total": len(targets), "groups_done": 0, "groups_without_members": 0,
    }

    if not targets:
        summary = _summarize(all_groups)
        result["progress"] = summary
        if summary["pending"] == 0:
            result["notice"] = "모든 그룹의 멤버 수집이 끝났습니다."
        else:
            result["notice"] = (
                f"오늘 처리량({summary['daily_limit']}개 그룹)을 모두 사용했습니다. "
                f"남은 그룹 {summary['pending']}개는 내일 이어서 진행해 주세요."
            )
        return result

    async with make_http_client() as http:
        for index, group in enumerate(targets):
            if on_progress:
                on_progress(index, len(targets), group["name"])

            try:
                members = await crawl_group_members(http, group["source_url"])
            except CrawlBlockedError as e:
                logger.error(str(e))
                result["error"] = str(e)
                result["progress"] = _summarize(_load_groups_safe(client, all_groups))
                return result
            except Exception as e:
                logger.error(f"Failed to crawl group {group['name']}: {e}")
                result["failed"].append({"name": group["name"], "reason": f"페이지 수집 실패: {e}"})
                result["groups_done"] += 1
                await asyncio.sleep(group_delay_seconds())
                continue   # 수집 시각을 남기지 않으므로 다음 실행 때 다시 시도한다

            saved_ok = True
            if not members:
                result["groups_without_members"] += 1
            else:
                saved_ok = await _save_group_members(client, group, members, result)

            if saved_ok:
                _mark_crawled(client, group, all_groups)
            result["groups_done"] += 1
            if index < len(targets) - 1:
                await asyncio.sleep(group_delay_seconds())

    if on_progress:
        on_progress(len(targets), len(targets), "")
    summary = _summarize(all_groups)
    result["progress"] = summary
    if group_id is None and summary["pending"] > 0:
        result["notice"] = (
            f"오늘 {len(targets)}개 그룹을 처리했습니다. 남은 그룹 {summary['pending']}개 "
            f"(약 {summary['days_left']}일). 내일 이어서 진행해 주세요."
        )
    return result


def _load_groups_safe(client, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    try:
        return _load_groups(client)
    except Exception:
        return fallback


def _mark_crawled(client, group: Dict[str, Any], all_groups: List[Dict[str, Any]]) -> None:
    """그룹의 멤버 수집을 마쳤다고 현재 시각을 기록한다. 기록에 실패하면 다음 실행 때 다시 처리된다."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        client.table("idol_groups").update({"members_crawled_at": now}).eq("id", group["id"]).execute()
        for g in all_groups:
            if g["id"] == group["id"]:
                g["members_crawled_at"] = now
    except Exception as e:
        logger.error(f"Failed to record crawl time for {group['name']}: {e}")


async def _save_group_members(client, group: Dict[str, Any], members, result: Dict[str, Any]) -> bool:
    """멤버를 저장한다. 기존 멤버 조회 자체가 실패해 처리하지 못했으면 False(수집 완료로 기록하지 않음)."""
    gid = group["id"]
    try:
        rows = (
            client.table("idols")
            .select("id, name, image_url, source_url, meta")
            .eq("group_id", gid).eq("is_preset", True)
            .execute().data or []
        )
    except Exception as e:
        logger.error(f"Failed to load existing idols for {group['name']}: {e}")
        result["failed"].append({"name": group["name"], "reason": f"기존 멤버 조회 실패: {e}"})
        return False
    by_name = {r["name"]: r for r in rows}

    for member in members:
        label = f"{group['name']} / {member.name}"
        row = by_name.get(member.name)

        if row is None:
            # 새 멤버: 이미지(있으면) 저장 → 행 추가. 이미지 업로드에 실패해도 이미지 없이 추가하고 실패로 기록한다.
            image_url = None
            if member.original_image_url:
                await asyncio.sleep(image_delay_seconds())
                image_url = await upload_image_to_storage(
                    client, member.original_image_url, member.name, folder=_image_folder(gid)
                )
                if not image_url:
                    # 이미지 없이라도 멤버는 저장한다. 다음에 이 그룹을 다시 크롤링하면 이미지를 채운다.
                    result["failed"].append({
                        "name": label,
                        "reason": f"이미지 업로드 실패 — 이미지 없이 저장됨 (원본 이미지: {member.original_image_url})",
                    })
            record = {
                "group_id": gid,
                "name": member.name,
                "image_url": image_url,
                "is_preset": True,
                "source_url": member.source_url,
                "meta": member.meta or {},
            }
            try:
                resp = client.table("idols").insert(record).execute()
                by_name[member.name] = resp.data[0] if resp.data else record
                result["added"] += 1
                result["added_items"].append(f"{label} (이미지 {'있음' if image_url else '없음'})")
            except Exception as e:
                logger.error(f"Insert failed for {label}: {e}")
                result["failed"].append({"name": label, "reason": f"DB 저장 실패: {str(e)[:150]}"})
            continue

        # 기존 멤버: 비어 있는 값만 채운다
        updates: Dict[str, Any] = {}
        if not row.get("source_url") and member.source_url:
            updates["source_url"] = member.source_url
        if not row.get("meta") and member.meta:
            updates["meta"] = member.meta
        if not row.get("image_url") and member.original_image_url:
            await asyncio.sleep(image_delay_seconds())
            image_url = await upload_image_to_storage(
                client, member.original_image_url, member.name, folder=_image_folder(gid)
            )
            if image_url:
                updates["image_url"] = image_url
            else:
                result["failed"].append({"name": label, "reason": "이미지 업로드 실패"})

        if not updates:
            result["skipped"] += 1
            continue
        try:
            client.table("idols").update(updates).eq("id", row["id"]).execute()
            row.update(updates)
            result["updated"] += 1
            names = {"source_url": "주소", "meta": "컬러/마크", "image_url": "이미지"}
            result["updated_items"].append(f"{label} → 채움: {', '.join(names.get(k, k) for k in updates)}")
        except Exception as e:
            logger.error(f"Update failed for {label}: {e}")
            result["failed"].append({"name": label, "reason": f"DB 갱신 실패: {str(e)[:150]}"})
    return True
