"""
Команда скачивания работ студентов через headless-браузер (Playwright).

Установка зависимостей (Ubuntu / Windows 10):
    pip install playwright
    playwright install chromium
"""

import hashlib
import logging
import os
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

from parser.models import Activity, Group, Student, StudentWork
from parser.solutions import SOLUTIONS_DIR, _ensure_solutions_dir

logger = logging.getLogger(__name__)

SOLUTION_URL_TPL = (
    "https://www.odin.study/ru/ActivitySolution/Index/{activity_id}"
    "?studentId={student_id}&userName="
)
MAX_RETRIES = 5
WAIT_TIMEOUT_MS = 2000


class Command(BaseCommand):
    help = (
        "Скачивание работ студентов группы для одной активности (через Playwright). "
        "Пример: python manage.py download_activity_works 2191122 60435"
    )

    def add_arguments(self, parser):
        parser.add_argument("activity_id", type=int, help="ID активности")
        parser.add_argument("group_id", type=int, help="ID группы")

    def handle(self, *args, **options):
        token = os.getenv("ODIN_BEARER_TOKEN")
        if not token:
            self.stderr.write(self.style.ERROR(
                "Не задан токен. Укажите ODIN_BEARER_TOKEN в .env или переменных окружения."
            ))
            return

        activity_id = options["activity_id"]
        group_id = options["group_id"]

        act = Activity.objects.filter(id=activity_id).first()
        if not act:
            self.stderr.write(self.style.ERROR(
                f"Активность с ID={activity_id} не найдена в БД."
            ))
            return

        group = Group.objects.filter(id=group_id).first()
        if not group:
            self.stderr.write(self.style.ERROR(
                f"Группа с ID={group_id} не найдена в БД."
            ))
            return

        students = list(Student.objects.filter(group=group))
        if not students:
            self.stderr.write(self.style.ERROR(
                "В группе нет студентов. Сначала запустите parse_odin_structure."
            ))
            return

        self.stdout.write(
            f'[+] Активность ID={activity_id} ("{act.name or "—"}") | '
            f'Группа ID={group_id} ("{group.title or "—"}") | '
            f'Студентов: {len(students)}'
        )

        _ensure_solutions_dir()
        ok_count = 0
        cache_count = 0
        skip_count = 0

        selector = (
            'path[d="M4 15.429V19a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3.571'
            'M12 4v10.286m0 0L7.429 9.714M12 14.286l4.571-4.572"]'
        )

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)

            for student in students:
                self.stdout.write(f"  [Браузер] Открываю страницу студента ID={student.id}...")

                existing = StudentWork.objects.filter(
                    student_id=student.id, activity=act,
                ).first()
                if existing:
                    self.stdout.write(
                        f"    -> [Кэш] Уже есть в БД (хэш: {existing.file_hash[:16]}…)"
                    )
                    cache_count += 1
                    continue

                url = SOLUTION_URL_TPL.format(
                    activity_id=activity_id, student_id=student.id,
                )
                context = browser.new_context(
                    extra_http_headers={"Authorization": f"Bearer {token}"},
                )
                page = context.new_page()

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    self.stdout.write(f"    -> [Ошибка] Не удалось загрузить страницу: {e}")
                    context.close()
                    skip_count += 1
                    continue

                found = False
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        locator = page.locator(selector)
                        locator.wait_for(state="attached", timeout=WAIT_TIMEOUT_MS)
                        found = True
                        break
                    except PwTimeout:
                        self.stdout.write(
                            f"    -> [Ожидание] Кнопка не найдена, "
                            f"попытка {attempt}/{MAX_RETRIES}..."
                        )

                if not found:
                    self.stdout.write(
                        f"    -> [Пусто] Студент ID={student.id} не прикрепил работу "
                        f"после {MAX_RETRIES} проверок."
                    )
                    context.close()
                    skip_count += 1
                    continue

                # Клик и перехват скачивания
                self.stdout.write(
                    "    -> [Клик] Кнопка найдена! Перехват скачивания из Yandex Cloud..."
                )
                try:
                    with page.expect_download(timeout=30000) as download_info:
                        page.locator(selector).click()
                    download = download_info.value
                except Exception as e:
                    self.stdout.write(f"    -> [Ошибка] Не удалось скачать файл: {e}")
                    context.close()
                    skip_count += 1
                    continue

                # Сохраняем во временный файл
                tmp = tempfile.NamedTemporaryFile(delete=False)
                tmp_path = tmp.name
                tmp.close()
                try:
                    download.save_as(tmp_path)
                except Exception as e:
                    self.stdout.write(f"    -> [Ошибка] Сохранение файла не удалось: {e}")
                    Path(tmp_path).unlink(missing_ok=True)
                    context.close()
                    skip_count += 1
                    continue

                # SHA-256
                sha256 = hashlib.sha256()
                with open(tmp_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        sha256.update(chunk)
                file_hash = sha256.hexdigest()

                suggested = download.suggested_filename or ""
                ext = Path(suggested).suffix if "." in suggested else ".bin"
                final_path = SOLUTIONS_DIR / f"{file_hash}{ext}"

                existing_file = StudentWork.objects.filter(file_hash=file_hash).first()
                if existing_file:
                    Path(tmp_path).unlink(missing_ok=True)
                    local_path = existing_file.local_path
                    msg = "Взято из кэша (файл уже существует на диске)"
                    cache_count += 1
                else:
                    Path(tmp_path).rename(final_path)
                    local_path = str(final_path)
                    msg = "Сохранено как новый файл"
                    ok_count += 1

                StudentWork.objects.update_or_create(
                    student_id=student.id,
                    activity=act,
                    defaults={
                        "file_hash": file_hash,
                        "local_path": local_path,
                    },
                )

                self.stdout.write(f"    -> [Успех] {msg}. Хэш: {file_hash[:16]}…")
                context.close()

            browser.close()

        self.stdout.write("")
        total = ok_count + cache_count + skip_count
        self.stdout.write(
            self.style.SUCCESS(
                f"[✔] Обработано студентов: {total} "
                f"(скачано: {ok_count}, из кэша: {cache_count}, "
                f"пропущено: {skip_count})"
            )
        )
