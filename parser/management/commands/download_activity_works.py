"""
Команда скачивания работ студентов через headless-браузер (Playwright).
Открывает одну страницу со списком студентов, прокручивает контейнер со студентами
(q-scrollarea students-list-block-component) для загрузки всех (виртуальная прокрутка),
затем кликает по каждой строке, ищет кнопку скачивания и сохраняет файл.
"""

import hashlib
import logging
import os
import tempfile
from pathlib import Path
import concurrent.futures
import json
import re
import time

from django.core.management.base import BaseCommand
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

from parser.models import Activity, Group, LecturePresentation, Student, StudentWork
from parser.lections import _fetch_lecture_paths, _download_and_save
from parser.storage import upload_with_hash

logger = logging.getLogger(__name__)

ACTIVITY_URL_TPL = (
    "https://www.odin.study/ru/ActivitySolution/Index/{activity_id}?userName="
)

MAX_RETRIES = 1
WAIT_TIMEOUT_MS = 500


class Command(BaseCommand):
    help = (
        "Скачивание работ студентов группы для одной активности (через Playwright). "
        "Открывает одну страницу, перебирает строки студентов и скачивает файлы. "
        "Пример: python manage.py download_activity_works 2191122 60435"
    )

    def add_arguments(self, parser):
        parser.add_argument("activity_id", type=int, help="ID активности")
        parser.add_argument("group_id", type=int, help="ID группы")
        parser.add_argument("--headed", action="store_true", help="Показать браузер (не headless)")

    def handle(self, *args, **options):
        auth_store_json = os.getenv("ODIN_AUTHORIZATIONSTORE")
        bearer_token = os.getenv("ODIN_BEARER_TOKEN")
        if not auth_store_json and not bearer_token:
            self.stderr.write(self.style.ERROR(
                "Не заданы авторизационные данные. Укажите ODIN_AUTHORIZATIONSTORE или ODIN_BEARER_TOKEN в .env"
            ))
            return
        if auth_store_json:
            self.stdout.write("Использую ODIN_AUTHORIZATIONSTORE (localStorage)")
        else:
            self.stdout.write("Использую ODIN_BEARER_TOKEN (HTTP header)")

        activity_id = options["activity_id"]
        group_id = options["group_id"]
        headed = options.get("headed", True)

        act = Activity.objects.filter(id=activity_id).first()
        if not act:
            self.stderr.write(self.style.ERROR(f"Активность с ID={activity_id} не найдена в БД."))
            return

        group = Group.objects.filter(id=group_id).first()
        if not group:
            self.stderr.write(self.style.ERROR(f"Группа с ID={group_id} не найдена в БД."))
            return

        students_info = list(Student.objects.filter(group=group).order_by('last_name', 'first_name'))
        if not students_info:
            self.stderr.write(self.style.ERROR("В группе нет студентов. Сначала запустите parse_odin_structure."))
            return

        self.stdout.write(
            f'[+] Активность ID={activity_id} ("{act.name or "—"}") | '
            f'Группа ID={group_id} ("{group.title or "—"}") | '
            f'Студентов в БД: {len(students_info)}'
        )

        # --- Скачивание презентаций лекций ---
        self.stdout.write("\n[*] Проверяю лекции для скачивания презентаций...")
        lectures = Activity.objects.filter(
            name=act.name,
            discipline__cohort=act.discipline.cohort,
            type="Лекция",
            type_id=1,
        )
        lec_ok = 0
        lec_cache = 0
        lec_skip = 0
        for lecture in lectures:
            if LecturePresentation.objects.filter(activity=lecture).exists():
                self.stdout.write(f"  -> [Кэш] Лекция ID={lecture.id} — уже скачана")
                lec_cache += 1
                continue
            self.stdout.write(f"  -> [Лекция] ID={lecture.id} ({lecture.name or '—'}) — запрашиваю контент...")
            try:
                paths = _fetch_lecture_paths(bearer_token, lecture.id)
            except Exception as e:
                self.stdout.write(f"  -> [Ошибка] Не удалось получить контент лекции {lecture.id}: {e}")
                lec_skip += 1
                continue
            if not paths:
                self.stdout.write(f"  -> [Пусто] У лекции {lecture.id} нет файлов")
                lec_skip += 1
                continue
            for url in paths:
                try:
                    result = _download_and_save(bearer_token, url)
                except Exception as e:
                    self.stdout.write(f"  -> [Ошибка] Скачивание {url}: {e}")
                    lec_skip += 1
                    continue
                if not result:
                    lec_skip += 1
                    continue
                file_hash, local_path = result
                LecturePresentation.objects.update_or_create(
                    activity=lecture,
                    file_hash=file_hash,
                    defaults={"file_path": url, "local_path": local_path},
                )
                self.stdout.write(f"  -> [OK] {Path(local_path).name} (хэш: {file_hash[:16]}…)")
                lec_ok += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"[*] Презентации: скачано {lec_ok}, из кэша {lec_cache}, ошибки {lec_skip}"
            )
        )

        ok_count = 0
        cache_count = 0
        skip_count = 0
        pw_error = None

        selector = (
            'path[d="M4 15.429V19a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3.571M12 4v10.286m0 0L7.429 9.714M12 14.286l4.571-4.572"]'
        )

        def get_student_id_from_url():
            match = re.search(r'[?&]studentId=(\d+)', page.url)
            return int(match.group(1)) if match else None

        with sync_playwright() as pw:
            try:
                self.stdout.write("[1/6] Запускаю браузер Playwright (Chromium)...")
                browser = pw.chromium.launch(headless=not headed)
                executor = concurrent.futures.ThreadPoolExecutor()

                self.stdout.write("[2/6] Создаю контекст браузера...")
                context = browser.new_context()
                if auth_store_json:
                    context.add_init_script(f"""
                        localStorage.setItem('authorizationStore', {json.dumps(auth_store_json)});
                    """)
                else:
                    context.set_extra_http_headers({"Authorization": f"Bearer {bearer_token}"})

                page = context.new_page()

                url = ACTIVITY_URL_TPL.format(activity_id=activity_id)
                self.stdout.write(f"[3/6] Открываю страницу: {url}")
                try:
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    self.stdout.write(self.style.SUCCESS("  [OK] Страница загружена (networkidle)"))
                except Exception as e:
                    raise Exception(f"Не удалось загрузить страницу: {e}")

                self.stdout.write("[4/6] Ожидаю появления родительского контейнера со списком студентов...")
                try:
                    page.wait_for_selector(
                        ".students-list-block-component .q-scrollarea__container, .q-page-container",
                        timeout=15000,
                    )
                    self.stdout.write(self.style.SUCCESS("  [OK] Контейнер найден"))
                except Exception as e:
                    raise Exception(f"Не дождался родительского контейнера: {e}")

                page.wait_for_timeout(5000)
                self.stdout.write("[5/6] Ищу скроллируемый контейнер .students-list-block-component .q-scrollarea__container...")
                scrollable = page.query_selector(".students-list-block-component .q-scrollarea__container")
                if not scrollable:
                    raise Exception("Не найден контейнер .students-list-block-component .q-scrollarea__container")

                self.stdout.write("[6/6] Прокручиваю список студентов до стабилизации scrollHeight...")

                for iteration in range(1, 31):
                    prev_height = scrollable.evaluate("el => el.scrollHeight")
                    page.evaluate("""
                        document.querySelector('.students-list-block-component .q-scrollarea__container')
                            .scrollTop = document.querySelector('.students-list-block-component .q-scrollarea__container')
                            .scrollHeight
                    """)
                    page.wait_for_timeout(800)
                    new_height = scrollable.evaluate("el => el.scrollHeight")
                    self.stdout.write(
                        f"  Итерация {iteration}: scrollHeight {prev_height} → {new_height}"
                    )
                    if new_height == prev_height:
                        self.stdout.write(self.style.SUCCESS(f"  scrollHeight стабилен ({new_height}px) — все строки загружены"))
                        break
                else:
                    self.stdout.write(self.style.WARNING("  Достигнут лимит итераций (30), но scrollHeight всё ещё растёт."))

                self.stdout.write("[6/6] Ищу карточки студентов (.q-card)...")
                container = page.wait_for_selector(
                    ".q-card.no-shadow.no-border.no-border-radius",
                    timeout=10000,
                )

                student_rows = container.query_selector_all(
                    "div[class='q-card__section q-card__section--vert student-list-item-component cursor-pointer']"
                )
                if not student_rows:
                    student_rows = container.query_selector_all(".student-list-item-component")
                if not student_rows:
                    raise Exception("Не найдены строки студентов внутри контейнера.")

                self.stdout.write(f"Найдено строк студентов на странице: {len(student_rows)}")

                if len(student_rows) != len(students_info):
                    self.stdout.write(self.style.WARNING(
                        f"Количество строк на странице ({len(student_rows)}) "
                        f"не совпадает с количеством студентов в БД ({len(students_info)}). "
                        "Будем ориентироваться на studentId из URL."
                    ))

                current_student_id = get_student_id_from_url()
                start_index = 0
                if current_student_id is not None:
                    for i, row in enumerate(student_rows):
                        if i < len(students_info) and students_info[i].id == current_student_id:
                            start_index = i
                            break
                    else:
                        start_index = 0
                        current_student_id = None

                if current_student_id is None:
                    self.stdout.write("Ни один студент не открыт, кликаю по первому...")
                    try:
                        student_rows[0].click()
                        page.wait_for_function(
                            "url => window.location.href.includes('studentId=')",
                            timeout=5000,
                        )
                        page.wait_for_timeout(1000)
                        current_student_id = get_student_id_from_url()
                        if current_student_id is None:
                            raise Exception("Не удалось получить studentId после клика")
                        start_index = 0
                    except Exception as e:
                        raise Exception(f"Не удалось открыть первого студента: {e}")

                for idx in range(start_index, len(student_rows)):
                    row = student_rows[idx]
                    if idx != start_index:
                        try:
                            row.click()
                            page.wait_for_function(
                                "url => window.location.href.includes('studentId=')",
                                timeout=5000,
                            )
                            page.wait_for_timeout(1000)
                            current_student_id = get_student_id_from_url()
                            if current_student_id is None:
                                raise Exception("studentId не появился")
                        except Exception as e:
                            self.stdout.write(f"  -> [Ошибка] Не удалось кликнуть по строке {idx+1}: {e}")
                            skip_count += 1
                            continue

                    current_student = executor.submit(
                        lambda sid=current_student_id: Student.objects.filter(id=sid, group=group).first()
                    ).result()
                    if not current_student:
                        self.stdout.write(f"  -> [Ошибка] Студент с ID={current_student_id} не найден в группе {group_id}")
                        skip_count += 1
                        continue

                    self.stdout.write(f"\n[{idx+1}/{len(student_rows)}] Студент: {current_student.last_name} {current_student.first_name} (ID={current_student.id})")

                    existing = executor.submit(
                        lambda sid=current_student.id: StudentWork.objects.filter(student_id=sid, activity=act).first()
                    ).result()
                    if existing:
                        self.stdout.write(f"  -> [Кэш] Уже есть в БД (хэш: {existing.file_hash[:16]}…)")
                        cache_count += 1
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
                                f"  -> [Ожидание] Кнопка не найдена, попытка {attempt}/{MAX_RETRIES}..."
                            )
                            if attempt < MAX_RETRIES:
                                page.wait_for_timeout(1000)

                    if not found:
                        self.stdout.write(f"  -> [Пусто] Студент {current_student.last_name} {current_student.first_name} не прикрепил работу.")
                        skip_count += 1
                        continue

                    self.stdout.write("  -> [Клик] Кнопка найдена! Перехват скачивания из Yandex Cloud...")
                    try:
                        with page.expect_download(timeout=30000) as download_info:
                            page.locator(selector).click()
                        download = download_info.value
                    except Exception as e:
                        self.stdout.write(f"  -> [Ошибка] Не удалось скачать файл: {e}")
                        skip_count += 1
                        continue

                    tmp = tempfile.NamedTemporaryFile(delete=False)
                    tmp_path = tmp.name
                    tmp.close()
                    try:
                        download.save_as(tmp_path)
                    except Exception as e:
                        self.stdout.write(f"  -> [Ошибка] Сохранение файла не удалось: {e}")
                        Path(tmp_path).unlink(missing_ok=True)
                        skip_count += 1
                        continue

                    sha256 = hashlib.sha256()
                    with open(tmp_path, "rb") as f:
                        for chunk in iter(lambda: f.read(8192), b""):
                            sha256.update(chunk)
                    file_hash = sha256.hexdigest()

                    suggested = download.suggested_filename or ""
                    ext = Path(suggested).suffix if "." in suggested else ".bin"

                    existing_file = executor.submit(
                        lambda h=file_hash: StudentWork.objects.filter(file_hash=h).first()
                    ).result()
                    if existing_file:
                        Path(tmp_path).unlink(missing_ok=True)
                        local_path = existing_file.local_path
                        msg = "Взято из кэша (файл уже существует на диске)"
                        cache_count += 1
                    else:
                        with open(tmp_path, "rb") as f:
                            content = f.read()
                        _, key = upload_with_hash("solutions", ext, content)
                        Path(tmp_path).unlink(missing_ok=True)
                        local_path = key
                        msg = "Сохранено как новый файл"
                        ok_count += 1

                    solution_url = (
                        f"https://www.odin.study/ru/ActivitySolution/Index/{activity_id}"
                        f"?studentId={current_student.id}&userName="
                    )
                    executor.submit(
                        lambda sid=current_student.id, act=act, fhash=file_hash, lpath=local_path, surl=solution_url:
                        StudentWork.objects.update_or_create(
                            student_id=sid,
                            activity=act,
                            defaults={"file_hash": fhash, "local_path": lpath, "solution_url": surl},
                        )
                    ).result()
                    self.stdout.write(f"  -> [Успех] {msg}. Хэш: {file_hash[:16]}…")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  [ОШИБКА] {e}"))
                pw_error = str(e)
                skip_count += 1
            finally:
                try:
                    executor.shutdown()
                except Exception:
                    pass
                try:
                    context.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass

        self.stdout.write("")
        if pw_error:
            self.stderr.write(self.style.ERROR(f"[ОШИБКА] Инициализация Playwright: {pw_error}\n"))
        total = ok_count + cache_count + skip_count
        self.stdout.write(
            self.style.SUCCESS(
                f"[✔] Обработано студентов: {total} "
                f"(скачано: {ok_count}, из кэша: {cache_count}, "
                f"пропущено: {skip_count})"
            )
        )
