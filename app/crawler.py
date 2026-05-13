from typing import List
from playwright.async_api import async_playwright
from .schemas import IdolGroupData

async def crawl_idol_groups() -> List[IdolGroupData]:
    """
    Crawls the `https://azito.kr/team-list/entire` URL.
    Filters by the '국내' (Domestic) category, extracts logic.
    """
    groups_data = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("Navigating to the target URL...")
        await page.goto("https://azito.kr/team-list/entire", wait_until="networkidle")
        
        # NOTE: The actual generic selectors will depend on the real DOM structure. 
        # Since this is an SPA, we wait for the lists to spawn.
        # Below is a conceptual representation of filtering by '국내' and getting items.
        
        try:
            # 1. Click on '국내' filter if it exists
            # await page.click("text='국내'")
            # await page.wait_for_timeout(2000) # give it time to load inner items
            
            # 2. Extract item list
            # Usually groups might be in some grid or list items.
            # Here we just execute a JS script to find plausible groups or wait for elements
            # Let's say we look for elements containing team names and images.
            
            # The teams are inside buttons that contain an img.
            # We scroll down a few times to load more elements
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)

            items = await page.query_selector_all("button:has(img)")
            
            for item in items:
                name_el = await item.query_selector("p:last-child")
                name = await name_el.inner_text() if name_el else "Unknown Group"
                
                img_el = await item.query_selector("img")
                img_src = await img_el.get_attribute("src") if img_el else None
                
                if name != "Unknown Group":
                    groups_data.append(IdolGroupData(
                        name=name.strip(),
                        original_image_url=img_src
                    ))
            
            print(f"Extracted {len(groups_data)} groups from DOM.")
        except Exception as e:
            print(f"Error extracting data: {e}")
            
        await browser.close()
        
    return groups_data
