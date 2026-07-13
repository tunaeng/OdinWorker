import hashlib
import logging
from pathlib import Path
from urllib.parse import urlparse

import requests

from parser.storage import upload_with_hash

logger = logging.getLogger(__name__)

CONTENTS_URL = "https://odin.study/api/Activity/Contents"


def _extract_extension(url: str) -> str:
    path = Path(urlparse(url).path)
    return path.suffix if path.suffix else ".bin"


def _fetch_lecture_paths(bearer_token: str, activity_id: int) -> list[str]:
    """GET-запрос к API Contents. Возвращает список URL файлов."""
    try:
        resp = requests.get(
            CONTENTS_URL,
            params={"activityId": activity_id},
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Ошибка запроса Activity/Contents для %d: %s", activity_id, e)
        return []

    data = resp.json()
    page_items = data.get("entity", {}).get("pageItems")
    if not page_items:
        logger.info("pageItems пуст для activity %d", activity_id)
        return []

    if not isinstance(page_items, list):
        page_items = [page_items]

    paths = []
    for item in page_items:
        file_view = item.get("fileView") or {}
        file_path = file_view.get("path")
        if file_path:
            paths.append(file_path)

    logger.info("Найдено %d файл(ов) для activity %d", len(paths), activity_id)
    return paths


def _download_and_save(bearer_token: str, url: str) -> tuple[str, str] | None:
    """Скачать файл, вычислить SHA-256, загрузить в S3.

    Возвращает (file_hash, s3_key) или None при ошибке.
    """
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {bearer_token}"},
            stream=True,
            timeout=60,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Ошибка скачивания %s: %s", url, e)
        return None

    sha256 = hashlib.sha256()
    chunks = []
    for chunk in resp.iter_content(chunk_size=8192):
        if chunk:
            sha256.update(chunk)
            chunks.append(chunk)
    file_hash = sha256.hexdigest()
    content = b"".join(chunks)

    ext = _extract_extension(url)
    _, key = upload_with_hash("lections", ext, content)

    return file_hash, key
