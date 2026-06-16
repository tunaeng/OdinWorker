"""
Команда извлечения текста задания с последнего слайда .pptx презентаций.
Читает записи LecturePresentation, парсит .pptx через zipfile+re,
сохраняет текст в поле task.
"""

import logging

from django.core.management.base import BaseCommand

from parser.models import LecturePresentation
from parser.pptx_utils import extract_last_slide_text

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Извлечение текста с последнего слайда .pptx презентаций. "
        "Берёт записи LecturePresentation, парсит файлы, сохраняет текст в task. "
        "Пример: python manage.py extract_pptx_tasks"
    )

    def handle(self, *args, **options):
        presentations = list(LecturePresentation.objects.all())
        if not presentations:
            self.stdout.write(self.style.WARNING("Нет записей LecturePresentation для обработки."))
            return

        self.stdout.write(f"[+] Найдено презентаций: {len(presentations)}")

        ok_count = 0
        skip_count = 0
        error_count = 0

        for pres in presentations:
            self.stdout.write(
                f"\n[{pres.id}] Activity={pres.activity_id} | "
                f"Файл: {pres.local_path.split('/')[-1]}"
            )

            if pres.task:
                self.stdout.write(f"  -> [Кэш] task уже заполнен ({len(pres.task)} символов)")
                ok_count += 1
                continue

            try:
                text = extract_last_slide_text(pres.local_path)
            except Exception as e:
                self.stdout.write(f"  -> [Ошибка] Парсинг не удался: {e}")
                logger.exception("Ошибка парсинга %s", pres.local_path)
                error_count += 1
                continue

            if not text:
                self.stdout.write("  -> [Пусто] Текст не найден (файл повреждён или нет слайдов)")
                skip_count += 1
                continue

            pres.task = text
            pres.save(update_fields=["task"])
            preview = text[:100] + "…" if len(text) > 100 else text
            self.stdout.write(f"  -> [OK] Сохранено ({len(text)} символов): {preview}")
            ok_count += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"[✔] Обработано: {len(presentations)} "
                f"(ok: {ok_count}, пропущено: {skip_count}, ошибки: {error_count})"
            )
        )
