import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from ..common.deps import require_admin
from ..common.storage import get_supabase_client
from .schemas import CrawlResponse
from .crawler import crawl_idol_groups
from .services import save_crawled_data
from .idol_services import get_idol_crawl_progress, save_crawled_idols

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

router = APIRouter(tags=["Crawling"])

# 크롤링이 멈춰서 잠금이 영영 안 풀리는 일을 막기 위한 작업별 제한 시간
CRAWL_TIMEOUT_SECONDS = {
    "groups": 30 * 60,
    "idols": 3 * 60 * 60,   # 하루 처리 그룹 수 x (무작위 요청 간격 + 이미지 업로드)
}

# 동시 실행 방지용 상태 (프로세스 메모리). 그룹 크롤링과 아이돌 크롤링은 하나의 잠금을 공유한다
# (같은 DB·사이트를 동시에 건드리지 않도록).
# uvicorn 워커를 여러 개 띄우거나 서버를 여러 대 운영하면 워커마다 따로 가진다.
_state = {
    "running": False,
    "job": None,            # "groups" | "idols"
    "started_at": None,
    "progress": None,       # {"done", "total", "current"}
    "last_result": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_progress(done: int, total: int, current: str) -> None:
    _state["progress"] = {"done": done, "total": total, "current": current}


async def _crawl_groups_job():
    groups = await crawl_idol_groups()
    return await save_crawled_data(groups)


async def _run_job(job: str, work: Callable[[], Awaitable[dict]]):
    empty = {"added": 0, "updated": 0, "skipped": 0, "failed": []}
    try:
        logger.info(f"Starting crawl job: {job}")
        result = await asyncio.wait_for(work(), timeout=CRAWL_TIMEOUT_SECONDS[job])
        _state["last_result"] = {"job": job, "error": None, **result, "finished_at": _now()}
        logger.info(
            f"Finished crawl job {job}. added={result.get('added')} updated={result.get('updated')} "
            f"skipped={result.get('skipped')} failed={len(result.get('failed', []))}"
        )
    except asyncio.TimeoutError:
        logger.error(f"Crawl job {job} timed out.")
        minutes = CRAWL_TIMEOUT_SECONDS[job] // 60
        _state["last_result"] = {
            "job": job, **empty, "error": f"크롤링 제한 시간({minutes}분)을 초과했습니다.", "finished_at": _now(),
        }
    except Exception as e:
        logger.error(f"Crawl job {job} failed: {e}")
        _state["last_result"] = {"job": job, **empty, "error": str(e), "finished_at": _now()}
    finally:
        # 성공/실패/예외와 상관없이 반드시 잠금 해제
        _state["running"] = False
        _state["job"] = None
        _state["progress"] = None


def _try_start(job: str) -> None:
    """실행 중이면 409. 호출부는 await 없이 이어서 상태를 바꾸므로(async def 엔드포인트) 동시 요청이 끼어들 수 없다."""
    if _state["running"]:
        running_job = "그룹" if _state["job"] == "groups" else "아이돌"
        raise HTTPException(
            status_code=409,
            detail=f"이미 {running_job} 크롤링이 진행 중입니다. (시작: {_state['started_at']})",
        )
    _state["running"] = True
    _state["job"] = job
    _state["started_at"] = _now()
    _state["progress"] = None


@router.post("/api/crawl", response_model=CrawlResponse, dependencies=[Depends(require_admin)])
async def trigger_crawl(background_tasks: BackgroundTasks):
    """그룹 크롤링: 새 그룹 추가 + 기존 그룹의 원본 주소(source_url) 보완."""
    _try_start("groups")
    background_tasks.add_task(_run_job, "groups", _crawl_groups_job)
    logger.info("Triggered group crawl; task placed in background.")
    return CrawlResponse(success=True, message="Crawling task started in the background.")


@router.get("/api/crawl/idols/progress", dependencies=[Depends(require_admin)])
async def idol_crawl_progress():
    """아이돌 크롤링 현황: 전체/완료/남은 그룹 수, 오늘 처리량과 남은 처리량, 다음 대상 그룹."""
    try:
        return get_idol_crawl_progress()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/crawl/idols", response_model=CrawlResponse, dependencies=[Depends(require_admin)])
async def trigger_idol_crawl(
    background_tasks: BackgroundTasks,
    group_id: Optional[int] = Query(None, description="지정하면 해당 그룹만, 생략하면 전체 그룹"),
):
    """아이돌(멤버) 크롤링. 원본 주소(source_url)가 있고 아직 수집하지 않은 그룹을 하루 상한까지 처리한다.

    group_id 를 주면 상한과 관계없이 그 그룹 하나만 (다시) 수집한다."""
    if group_id is not None:
        try:
            resp = (
                get_supabase_client().table("idol_groups")
                .select("id, source_url").eq("id", group_id).execute()
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        if not resp.data:
            raise HTTPException(status_code=404, detail="Idol group not found")
        if not resp.data[0].get("source_url"):
            raise HTTPException(
                status_code=400,
                detail="해당 그룹에는 원본 주소(source_url)가 없습니다. 먼저 '그룹 크롤링'을 실행해 주소를 채워 주세요.",
            )

    _try_start("idols")
    background_tasks.add_task(
        _run_job, "idols", lambda: save_crawled_idols(group_id=group_id, on_progress=_set_progress)
    )
    logger.info(f"Triggered idol crawl (group_id={group_id}); task placed in background.")
    return CrawlResponse(success=True, message="Idol crawling task started in the background.")


@router.get("/api/crawl/status", dependencies=[Depends(require_admin)])
async def crawl_status():
    """진행 여부, 진행률, 마지막 크롤링 결과 (추가/갱신/건너뜀/실패 목록)."""
    return {
        "running": _state["running"],
        "job": _state["job"],
        "started_at": _state["started_at"],
        "progress": _state["progress"],
        "last_result": _state["last_result"],
    }
