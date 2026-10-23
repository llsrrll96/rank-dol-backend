"""그룹 상세 페이지(/team/{id})에서 멤버 목록을 가져온다.

페이지의 멤버 영역은 서버에서 HTML로 내려오므로 브라우저(Playwright) 없이
HTTP 요청 + HTML 파싱만으로 충분하다. 사이트에 부담을 주지 않도록 요청은 순차적으로,
요청 사이에 간격을 두고 보내며, 접근이 거절되면(403/429) 우회하지 않고 즉시 중단한다.
"""
import asyncio
import logging
import os
import random
import re
from typing import List

import httpx
from bs4 import BeautifulSoup

from .schemas import IdolData

logger = logging.getLogger(__name__)

BASE_URL = "https://azito.kr"
USER_AGENT = "mydol-idol-crawler/1.0"
# 요청 사이 간격은 매번 [최소, 최대] 범위에서 무작위로 정한다(환경변수로 조절 가능).
# 사이트에 주는 부담을 줄이려는 것이지, 접근 제한을 피하려는 용도가 아니다.
DEFAULT_GROUP_DELAY = (5.0, 15.0)   # 그룹 페이지 요청 사이(초)
DEFAULT_IMAGE_DELAY = (1.0, 3.0)    # 멤버 이미지 다운로드 사이(초)
REQUEST_TIMEOUT_SECONDS = 20
MAX_ATTEMPTS = 2              # 일시적 오류 재시도 (총 시도 횟수)
RETRY_WAIT_SECONDS = 3
TEAM_PATH_RE = re.compile(r"^/team/\d+$")


def _delay_range(prefix: str, default) -> tuple:
    try:
        lo = float(os.environ.get(f"{prefix}_MIN_SECONDS", default[0]))
        hi = float(os.environ.get(f"{prefix}_MAX_SECONDS", default[1]))
    except ValueError:
        lo, hi = default
    lo = max(0.0, lo)
    return lo, max(lo, hi)


def group_delay_seconds() -> float:
    """그룹 페이지 요청 사이에 쉬는 시간 (IDOL_CRAWL_DELAY_MIN/MAX_SECONDS, 기본 5~15초)."""
    return random.uniform(*_delay_range("IDOL_CRAWL_DELAY", DEFAULT_GROUP_DELAY))


def image_delay_seconds() -> float:
    """이미지 다운로드 사이에 쉬는 시간 (IDOL_CRAWL_IMAGE_DELAY_MIN/MAX_SECONDS, 기본 1~3초)."""
    return random.uniform(*_delay_range("IDOL_CRAWL_IMAGE_DELAY", DEFAULT_IMAGE_DELAY))


class CrawlBlockedError(Exception):
    """대상 사이트가 접근을 거절했다 (403/429). 재시도·우회하지 않고 크롤링을 중단한다."""


def make_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "ko,en;q=0.8"},
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )


def parse_group_members(html: str) -> List[IdolData]:
    """그룹 페이지 HTML에서 멤버 카드(a[href^='/artist/'])를 읽는다.

    카드 구조: <a href="/artist/115?team=222"> <img src=...> <p>이름</p> <span><span>컬러</span><span>마크</span></span> </a>
    """
    soup = BeautifulSoup(html, "html.parser")
    members: List[IdolData] = []
    seen = set()

    for a in soup.select("a[href^='/artist/']"):
        artist_path = (a.get("href") or "").split("?")[0]
        if not artist_path or artist_path in seen:
            continue

        name_el = a.find("p")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            continue
        seen.add(artist_path)

        img = a.find("img")
        src = img.get("src") if img else None

        badge = [s.get_text(strip=True) for s in a.select("span > span")]
        meta = {}
        if len(badge) >= 1 and badge[0]:
            meta["color"] = badge[0]
        if len(badge) >= 2 and badge[1]:
            meta["mark"] = badge[1]

        members.append(
            IdolData(name=name, original_image_url=src, source_url=artist_path, meta=meta)
        )
    return members


async def crawl_group_members(http: httpx.AsyncClient, source_url: str) -> List[IdolData]:
    """그룹 한 곳의 멤버를 가져온다. source_url 예: /team/222"""
    if not TEAM_PATH_RE.match(source_url or ""):
        raise ValueError(f"올바르지 않은 그룹 주소: {source_url!r}")

    last_error: Exception = RuntimeError("unknown")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await http.get(BASE_URL + source_url)
            if response.status_code in (403, 429):
                raise CrawlBlockedError(
                    f"azito.kr이 요청을 거절했습니다 (HTTP {response.status_code}). 크롤링을 중단했습니다."
                )
            response.raise_for_status()
            return parse_group_members(response.text)
        except CrawlBlockedError:
            raise
        except httpx.HTTPError as e:
            last_error = e
            logger.warning(f"{source_url}: attempt {attempt}/{MAX_ATTEMPTS} failed: {e}")
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(RETRY_WAIT_SECONDS)
    raise last_error
