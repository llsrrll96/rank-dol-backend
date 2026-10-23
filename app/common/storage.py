import os
import re
import hashlib
import uuid
import httpx
from urllib.parse import urlparse, parse_qs
from supabase import create_client, Client
from typing import List, Optional
from fastapi import UploadFile

SOURCE_ORIGIN = "https://azito.kr"
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "avif"}
CONTENT_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "gif": "image/gif", "avif": "image/avif",
}


def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        print("Warning: SUPABASE_URL or SUPABASE_KEY not found in environment.")
    return create_client(url, key)


def _bucket() -> str:
    return os.environ.get("SUPABASE_BUCKET", "images")


def resolve_source_image_url(src: str) -> str:
    """소스 사이트의 이미지 주소를 받아올 수 있는 절대 주소(원본)로 바꾼다.

    - "//host/x.jpg", "/x.jpg" 같은 주소는 절대 주소로 만든다.
    - Next.js 이미지 프록시(/_next/image?url=<원본>&w=..)는 원본 주소(url 파라미터)로 바꾼다.
    """
    if not src:
        return src

    def absolutize(u: str) -> str:
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return SOURCE_ORIGIN + u
        return u

    src = absolutize(src)
    parsed = urlparse(src)
    if parsed.path == "/_next/image":
        original = parse_qs(parsed.query).get("url", [None])[0]
        if original:
            return absolutize(original)
    return src


def _extension_from_url(url: str) -> str:
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    return ext if ext in ALLOWED_IMAGE_EXTENSIONS else "jpg"


async def upload_image_to_storage(
    client: Client, image_url: str, name: str, folder: str = "idol_groups"
) -> Optional[str]:
    """외부 이미지 주소를 받아 Storage의 `folder` 아래에 올리고 공개 URL을 돌려준다. 실패하면 None.

    파일명은 이름의 해시로 고정(같은 이름이면 같은 경로)이라 재시도·재크롤링 시 덮어쓴다.
    """
    if not image_url:
        return None

    bucket_name = _bucket()
    source_url = resolve_source_image_url(image_url)
    file_extension = _extension_from_url(source_url)
    safe_name = hashlib.md5(name.encode("utf-8")).hexdigest()
    file_path = f"{folder}/{safe_name}.{file_extension}"

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http_client:
            response = await http_client.get(source_url)
            response.raise_for_status()
            image_data = response.content
            content_type = response.headers.get("content-type", "")

        if not content_type.startswith("image/"):
            content_type = CONTENT_TYPES.get(file_extension, "image/jpeg")

        client.storage.from_(bucket_name).upload(
            file=image_data,
            path=file_path,
            # x-upsert: 이전 크롤링에서 DB 저장만 실패해 남은 파일이 있어도 덮어쓴다
            file_options={"content-type": content_type, "x-upsert": "true"},
        )
        return client.storage.from_(bucket_name).get_public_url(file_path)
    except Exception as e:
        print(f"Failed to upload image for {name}: {e}")
        # 외부 사이트 원본 주소를 대신 반환하면 DB가 남의 서버를 가리키게 되므로 None으로 실패를 알린다
        return None


async def upload_file_to_storage(
    client: Client, file: UploadFile, name: str, folder: str = "idol_groups"
) -> Optional[str]:
    if not file or not file.filename:
        return None

    bucket_name = _bucket()
    raw_ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    file_extension = re.sub(r"[^a-z0-9]", "", raw_ext)[:5] or "jpg"
    safe_name = hashlib.md5(name.encode("utf-8")).hexdigest()
    # 업로드마다 고유한 파일명을 써서, 같은 확장자로 이미지를 교체해도
    # 이전 파일 삭제가 새 파일을 지우지 않고 캐시된 옛 이미지도 보이지 않게 한다.
    file_path = f"{folder}/{safe_name}-{uuid.uuid4().hex[:8]}.{file_extension}"

    try:
        content = await file.read()
        client.storage.from_(bucket_name).upload(
            file=content,
            path=file_path,
            file_options={"content-type": file.content_type, "x-upsert": "true"},
        )
        return client.storage.from_(bucket_name).get_public_url(file_path)
    except Exception as e:
        print(f"Failed to upload file for {name}: {e}")
        return None


def _storage_path(image_url: str) -> Optional[str]:
    prefix = f"/object/public/{_bucket()}/"
    if image_url and prefix in image_url:
        return image_url.split(prefix)[-1].split("?")[0]
    return None


async def delete_image_from_storage(client: Client, image_url: str):
    path = _storage_path(image_url)
    if not path:
        return
    try:
        client.storage.from_(_bucket()).remove([path])
        print(f"Deleted image from storage: {path}")
    except Exception as e:
        print(f"Failed to delete image {image_url}: {e}")


async def delete_images_from_storage(client: Client, image_urls: List[Optional[str]]):
    """여러 이미지를 한 번에 삭제한다 (우리 버킷 경로가 아닌 주소는 무시)."""
    paths = [p for p in (_storage_path(u) for u in image_urls if u) if p]
    if not paths:
        return
    try:
        client.storage.from_(_bucket()).remove(paths)
        print(f"Deleted {len(paths)} images from storage")
    except Exception as e:
        print(f"Failed to delete {len(paths)} images: {e}")
