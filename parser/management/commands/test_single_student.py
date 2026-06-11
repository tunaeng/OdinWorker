import logging
import os

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

from parser.solutions import TARGET_SVG_D

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Диагностика страницы решения одного студента"

    def add_arguments(self, parser):
        parser.add_argument("activity_id", type=int, help="ID активности")
        parser.add_argument("student_id", type=int, help="ID студента")

    def handle(self, *args, **options):
        token = os.getenv("ODIN_BEARER_TOKEN")
        if not token:
            self.stderr.write(self.style.ERROR(
                "Не задан токен. Укажите ODIN_BEARER_TOKEN в .env или переменных окружения."
            ))
            return

        activity_id = options["activity_id"]
        student_id = options["student_id"]

        url = (
            f"https://www.odin.study/ru/ActivitySolution/Index/{activity_id}"
            f"?studentId={student_id}&userName="
        )

        self.stdout.write(f"[*] URL: {url}")
        self.stdout.write("")

        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {token}"})

        try:
            resp = session.get(url, timeout=30, allow_redirects=True)
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f"[!] Ошибка запроса: {e}"))
            return

        # --- HTTP статус и редиректы ---
        self.stdout.write("=" * 60)
        self.stdout.write("1. HTTP ОТВЕТ")
        self.stdout.write("-" * 60)
        self.stdout.write(f"  Статус-код: {resp.status_code}")
        self.stdout.write(f"  Финальный URL: {resp.url}")
        if resp.history:
            self.stdout.write(f"  Редиректы ({len(resp.history)}):")
            for i, r in enumerate(resp.history, 1):
                self.stdout.write(f"    {i}. {r.status_code} -> {r.url}")

        # --- Заголовки ---
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write("2. ЗАГОЛОВКИ ОТВЕТА")
        self.stdout.write("-" * 60)
        for key, val in resp.headers.items():
            self.stdout.write(f"  {key}: {val}")

        # --- Размер и заголовок страницы ---
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write("3. СТРУКТУРА СТРАНИЦЫ")
        self.stdout.write("-" * 60)
        html_len = len(resp.text)
        self.stdout.write(f"  Длина HTML: {html_len} символов")
        if html_len < 5000:
            self.stdout.write(self.style.WARNING(
                "  ⚠ Длина меньше 5000 символов — возможна заглушка или страница логина"
            ))
        import time
        time.sleep(2)
        soup = BeautifulSoup(resp.text, "html.parser")
        title_tag = soup.find("title")
        title = title_tag.string.strip() if title_tag and title_tag.string else "(нет)"
        self.stdout.write(f"  <title>: {title}")

        # --- Проверка на редирект на логин ---
        if "login" in resp.url.lower() or "login" in title.lower():
            self.stdout.write(self.style.ERROR(
                "  ⚠ Похоже, произошёл редирект на страницу логина! "
                "Токен не работает для веб-страниц."
            ))

        # --- Все SVG + Path ---
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write("4. ВСЕ <svg> И <path> НА СТРАНИЦЕ")
        self.stdout.write("-" * 60)

        svg_tags = soup.find_all("svg")
        self.stdout.write(f"  Найдено <svg> тегов: {len(svg_tags)}")

        all_paths = soup.find_all("path")
        self.stdout.write(f"  Найдено <path> тегов: {len(all_paths)}")

        matched = False
        for i, path in enumerate(all_paths, 1):
            d_val = path.get("d", "")
            if not d_val:
                continue
            preview = d_val[:60] + "…" if len(d_val) > 60 else d_val
            marker = "  ← ЦЕЛЕВОЙ!" if d_val.strip() == TARGET_SVG_D.strip() else ""
            if marker:
                matched = True
            # Показываем только первые 20 path, чтобы не заспамить
            if i <= 20 or marker:
                self.stdout.write(f"  path #{i}: d=\"{preview}\"{marker}")

        if len(all_paths) > 20 and not matched:
            self.stdout.write(f"  ... и ещё {len(all_paths) - 20} <path> тегов (скрыто)")

        # --- SVG-контейнеры с их потомками ---
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write("5. ДЕТАЛИ ПО КАЖДОМУ <svg>")
        self.stdout.write("-" * 60)
        for i, svg in enumerate(svg_tags, 1):
            svg_classes = svg.get("class", [])
            svg_id = svg.get("id", "")
            nested_paths = svg.find_all("path")
            self.stdout.write(
                f"  <svg #{i}>: id=\"{svg_id}\", классов={svg_classes}, "
                f"вложенных <path>: {len(nested_paths)}"
            )

        # --- Финальный вердикт ---
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write("6. ФИНАЛЬНЫЙ ВЕРДИКТ")
        self.stdout.write("-" * 60)
        if matched:
            self.stdout.write(self.style.SUCCESS(
                "  ✅ Целевой path с d=\"M4 15.429...\" НАЙДЕН!"
            ))
        else:
            self.stdout.write(self.style.ERROR(
                "  ❌ Целевой path НЕ НАЙДЕН."
            ))
            self.stdout.write("  Возможные причины:")
            self.stdout.write("    - Страница требует дополнительных кук/сессии")
            self.stdout.write("    - Файл загружается через JavaScript")
            self.stdout.write("    - Другой атрибут d у кнопки скачивания")
