"""
Демон-планировщик. Бесконечно проверяет активные расписания
и запускает выгрузку по интервалу.

Пример:
  python manage.py run_scheduled_tasks
"""

import logging
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from scheduler.models import Schedule
from scheduler.runner import ensure_logs_dir, run_schedule

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5


class Command(BaseCommand):
    help = "Демон-планировщик выгрузки работ"

    def handle(self, *args, **options):
        self.stdout.write("Демон-планировщик запущен. Проверка расписаний...")
        ensure_logs_dir()

        while True:
            now = timezone.now()
            schedules = Schedule.objects.filter(is_active=True)

            for sched in schedules:
                last_log = sched.logs.order_by("-started_at").first()
                if last_log and last_log.started_at:
                    elapsed = (now - last_log.started_at).total_seconds()
                    if elapsed < sched.interval_seconds:
                        continue

                self.stdout.write(f"Запуск расписания: {sched.name} (ID={sched.id})")
                run_schedule(sched.id)
                self.stdout.write(f"Расписание {sched.name}: завершено")

            time.sleep(POLL_INTERVAL)
