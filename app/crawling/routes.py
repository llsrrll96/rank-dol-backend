import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from .schemas import CrawlResponse
from .crawler import crawl_idol_groups
from .services import save_crawled_data

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

router = APIRouter(tags=["Crawling"])

async def run_crawling_task():
    try:
        logger.info("Starting background crawling task...")
        # 1. Crawl Data
        groups = await crawl_idol_groups()
        
        # 2. Save Data & Images to Supabase
        await save_crawled_data(groups)
        logger.info("Finished background crawling task.")
    except Exception as e:
        logger.error(f"Crawling failed: {e}")

@router.post("/api/crawl", response_model=CrawlResponse)
def trigger_crawl(background_tasks: BackgroundTasks):
    try:
        background_tasks.add_task(run_crawling_task)
        logger.info("Triggered crawl endpoint; tasks placed in background.")
        return CrawlResponse(
            success=True,
            message="Crawling task started in the background."
        )
    except Exception as e:
        logger.error(f"Error triggering crawl: {e}")
        raise HTTPException(status_code=500, detail=str(e))
