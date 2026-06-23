"""
Команда массового выставления оценок из CSV-файла через REST API Odin.

Пример:
  python manage.py set_marks_from_csv 2191122 /tmp/marks.csv
"""

import csv
import logging
import os

import requests
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

API_URL = "https://odin.study/api/Mark/SetMarkForTask"


class Command(BaseCommand):
    help = "Выставление оценок студентам из CSV-файла через REST API"

    def add_arguments(self, parser):
        parser.add_argument("activity_id", type=int, help="ID активности")
        parser.add_argument("csv_path", type=str, help="Путь к CSV-файлу")

    def handle(self, *args, **options):
        activity_id = options["activity_id"]
        csv_path = options["csv_path"]
        token = os.getenv("ODIN_BEARER_TOKEN")

        if not token:
            self.stderr.write("(!) ODIN_BEARER_TOKEN не задан в .env")
            return

        if not os.path.exists(csv_path):
            self.stderr.write(f"(!) Файл не найден: {csv_path}")
            return

        self.stdout.write("Запускаю выставление....")

        rows = []
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if not row or len(row) < 2:
                    continue
                student_id_str, mark_value_str = row[0].strip(), row[1].strip()
                if i == 0 and not student_id_str.isdigit():
                    continue
                rows.append((int(student_id_str), int(mark_value_str)))

        if not rows:
            self.stdout.write("[!] Нет валидных строк в CSV.")
            return

        self.stdout.write("Читаю csv файл...")
        self.stdout.write("Вижу:")
        self.stdout.write("---------------------")
        self.stdout.write("Айди студента, Оценка")
        self.stdout.write("---------------------")
        for student_id, mark_value in rows:
            self.stdout.write(f"{student_id}, {mark_value}")
            self.stdout.write(f"...")
            break   
        self.stdout.write("---------------------")

        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {token}"})

        ok_count = 0
        error_count = 0
        self.stdout.write(
            f"\n Начинаю выставлять оценки..."
        )
        for student_id, mark_value in rows:
            payload = {
                "studentId": student_id,
                "activityId": activity_id,
                "markValue": mark_value,
            }
            try:
                resp = session.post(API_URL, json=payload, timeout=30)
                self.stdout.write(
                    f"Выставляю оценку студенту {student_id}: ответ {resp.status_code}"
                )
                if resp.status_code < 400:
                    ok_count += 1
                else:
                    error_count += 1
            except requests.RequestException as e:
                self.stdout.write(
                    f"\n(!)Выставляю оценку студенту {student_id}: ошибка {e}\n"
                )
                error_count += 1

        self.stdout.write(f"\n Выставлять оценки завершил (выставил: {ok_count}, ошибки: {error_count})")
