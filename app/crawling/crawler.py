import logging
from typing import List
from playwright.async_api import async_playwright
from .schemas import IdolGroupData

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

async def crawl_idol_groups() -> List[IdolGroupData]:
    """
    Crawls the `https://azito.kr/team-list/entire` URL.
    Filters by the '국내' (Domestic) category, extracts logic.
    """
    groups_data = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        logger.info("Navigating to the target URL...")
        await page.goto("https://azito.kr/team-list/entire", wait_until="networkidle")
        
        try:
            content = await page.content()
            logger.info(f"Page loaded. Content length: {len(content)} characters.")
            
            for i in range(5):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)
                logger.info(f"Scrolled {i+1}/5 times.")

            # 카드 컨테이너 선택: 팀 링크(a[href^="/team/"]) 를 직접 자식으로 가진 div
            items = await page.query_selector_all("div:has(> a[href^='/team/'].shrink-0)")
            logger.info(f"Found {len(items)} matching items initially.")
            
            for item in items:
                # 그룹명: a.min-w-0 > p > span
                name_el = await item.query_selector("a.min-w-0 p > span")
                name = await name_el.inner_text() if name_el else "Unknown Group"
                
                # 이미지: a.shrink-0 img
                img_el = await item.query_selector("a.shrink-0 img")
                img_src = await img_el.get_attribute("src") if img_el else None
                
                logger.info(f"Item found - name: '{name}', img_src: '{img_src}'")
                
                if name and name != "Unknown Group":
                    groups_data.append(IdolGroupData(
                        name=name.strip(),
                        original_image_url=img_src
                    ))
            
            logger.info(f"Extracted {len(groups_data)} groups from DOM.")
        except Exception as e:
            logger.error(f"Error extracting data: {e}")
            
        await browser.close()
        
    return groups_data
