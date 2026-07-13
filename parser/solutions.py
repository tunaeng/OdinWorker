import hashlib
import logging
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from parser.models import Activity, StudentWork
from parser.storage import upload_with_hash

logger = logging.getLogger(__name__)

TARGET_SVG_D = (
    "M4 15.429V19a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3.571"
    "M12 4v10.286m0 0L7.429 9.714M12 14.286l4.571-4.572"
)

SOLUTIONS_URL_TPL = "https://www.odin.study/ru/ActivitySolution/Index/{activity_id}"


def _extract_extension(response, url):
    ct = response.headers.get("Content-Disposition", "")
    match = re.search(r'filename[^;=\n]*=(["\']?)([^"\';\n]+)\1', ct)
    if match:
        filename = match.group(2).strip()
        if "." in filename:
            return Path(filename).suffix
    path = Path(urlparse(url).path)
    if path.suffix:
        return path.suffix
    return ".bin"


def download_student_work(session, activity_id, student_id):
    act = Activity.objects.filter(id=activity_id).first()
    if not act:
        return "skip", f"Активность {activity_id} не найдена в БД"

    if StudentWork.objects.filter(student_id=student_id, activity=act).exists():
        return "cache", "Уже есть в БД"

    solution_url = (
        f"{SOLUTIONS_URL_TPL.format(activity_id=activity_id)}"
        f"?studentId={student_id}&userName="
    )
    logger.info("Загрузка страницы решения: %s", solution_url)

    try:
        resp = session.get(solution_url, timeout=30)
        if resp.status_code == 404:
            return "skip", "Нет решения (404)"
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Ошибка запроса страницы решения %s: %s", solution_url, e)
        return "skip", f"Ошибка запроса: {e}"

    soup = BeautifulSoup(resp.text, "html.parser")
    path_tag = soup.select_one(f'svg path[d="{TARGET_SVG_D}"]')
    if not path_tag:
        logger.info("Кнопка скачивания не найдена на странице %s", solution_url)
        return "skip", "Кнопка скачивания не найдена"

    a_tag = path_tag.find_parent("a")
    if not a_tag or not a_tag.get("href"):
        logger.info("Ссылка скачивания не найдена на странице %s", solution_url)
        return "skip", "Ссылка скачивания не найдена"

    href = a_tag["href"]
    file_url = urljoin(solution_url, href)

    logger.info("Скачивание файла: %s", file_url)
    try:
        file_resp = session.get(file_url, timeout=60, stream=True)
        file_resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Ошибка скачивания файла %s: %s", file_url, e)
        return "skip", f"Ошибка скачивания: {e}"

    sha256 = hashlib.sha256()
    chunks = []
    for chunk in file_resp.iter_content(chunk_size=8192):
        if chunk:
            sha256.update(chunk)
            chunks.append(chunk)
    file_hash = sha256.hexdigest()

    ext = _extract_extension(file_resp, file_url)
    content = b"".join(chunks)

    existing = StudentWork.objects.filter(file_hash=file_hash).first()
    if existing:
        local_path = existing.local_path
        status = "cache"
        msg = "Из кэша"
    else:
        _, key = upload_with_hash("solutions", ext, content)
        local_path = key
        status = "ok"
        msg = "Новый файл"

    StudentWork.objects.update_or_create(
        student_id=student_id,
        activity=act,
        defaults={
            "file_hash": file_hash,
            "local_path": local_path,
        },
    )
    return status, msg
