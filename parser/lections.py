import hashlib
import logging
from pathlib import Path
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

LECTIONS_DIR = Path("media") / "lections"
CONTENTS_URL = "https://odin.study/api/Activity/Contents"
DOWNLOAD_CHUNK_SIZE = 8192


def _ensure_lections_dir():
    LECTIONS_DIR.mkdir(parents=True, exist_ok=True)


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
    """Скачивать файл, вычислить SHA-256, сохранить на диск.

    Возвращает (file_hash, local_path) или None при ошибке.
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
    for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
        if chunk:
            sha256.update(chunk)
    file_hash = sha256.hexdigest()

    ext = _extract_extension(url)
    _ensure_lections_dir()
    local_path = LECTIONS_DIR / f"{file_hash}{ext}"

    if not local_path.exists():
        resp2 = requests.get(
            url,
            headers={"Authorization": f"Bearer {bearer_token}"},
            stream=True,
            timeout=60,
        )
        resp2.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp2.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    f.write(chunk)

    return file_hash, str(local_path)
