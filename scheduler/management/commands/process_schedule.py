"""
Запуск одного расписания немедленно.

Пример:
  python manage.py process_schedule 1
"""

import logging

from django.core.management.base import BaseCommand

from scheduler.models import Schedule

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Запуск одного расписания немедленно (однократно)"

    def add_arguments(self, parser):
        parser.add_argument("schedule_ids", nargs="+", type=int, help="ID расписания")

    def handle(self, *args, **options):
        ids = options["schedule_ids"]
        for sid in ids:
            sched = Schedule.objects.filter(id=sid).first()
            if not sched:
                self.stderr.write(self.style.ERROR(f"Расписание ID={sid} не найдено"))
                continue

            self.stdout.write(f"Запуск расписания: {sched.name} (ID={sid})")
            from scheduler.runner import run_schedule
            run_schedule(sid)
            self.stdout.write(self.style.SUCCESS(f"Расписание {sched.name}: завершено"))
