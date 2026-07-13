import hashlib
import logging
import os

import requests
from django.core.management import call_command
from django.utils import timezone

from parser.models import Activity, Group
from parser.storage import s3_upload
from scheduler.models import Schedule, ScheduleLog

logger = logging.getLogger(__name__)

ACTIVITY_INFO_URL = "https://odin.study/api/ActivitySolution/ActivityInfo"


def check_activity(bearer_token: str, activity_id: int) -> bool:
    try:
        resp = requests.get(
            ACTIVITY_INFO_URL,
            params={"activityId": activity_id},
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=15,
        )
        return resp.json().get("httpStatusCode") == 200
    except Exception:
        return False


class _LineWriter:
    def __init__(self, lines: list[str]):
        self._lines = lines

    def write(self, msg: str) -> None:
        self._lines.append(msg)

    def flush(self) -> None:
        pass


def write_log(lines: list[str], schedule: Schedule) -> None:
    writer = _LineWriter(lines)
    token = os.getenv("ODIN_BEARER_TOKEN")

    if not token:
        lines.append("ODIN_BEARER_TOKEN не задан\n")
        return

    lines.append(f"Расписание: {schedule.name} (ID={schedule.id})\n")
    lines.append(f"Запуск: {timezone.now():%Y-%m-%d %H:%M:%S}\n\n")

    all_activities = list(Activity.objects.values_list("id", flat=True))
    lines.append(f"Всего активностей в БД: {len(all_activities)}\n")

    active_ids = []
    for aid in all_activities:
        lines.append(f"  Проверяю activity {aid}... ")
        if check_activity(token, aid):
            lines.append("доступна\n")
            active_ids.append(aid)
        else:
            lines.append("пропущена\n")

    lines.append(f"\nАктивных активностей: {len(active_ids)}\n\n")

    if not active_ids:
        lines.append("Нет активных активностей для выгрузки.\n")
        return

    for aid in active_ids:
        act = Activity.objects.filter(id=aid).first()
        if not act:
            continue
        cohort = act.discipline.cohort
        groups = Group.objects.filter(cohort=cohort).values_list("id", flat=True)
        lines.append(f"\nАктивность ID={aid}, поток ID={cohort.id}, групп: {len(groups)}\n")
        for gid in groups:
            lines.append(f"  Группа ID={gid}: запуск download_activity_works...\n")
            try:
                call_command("download_activity_works", str(aid), str(gid), stdout=writer)
                lines.append(f"  Группа ID={gid}: завершено\n")
            except Exception as e:
                lines.append(f"  Группа ID={gid}: ошибка {e}\n")
                logger.exception("Ошибка выгрузки activity=%s group=%s", aid, gid)

    lines.append(f"\nЗавершено: {timezone.now():%Y-%m-%d %H:%M:%S}\n")


def _s3_key_for_log(sha256: str) -> str:
    return f"schedule_logs/{sha256}.log"


def run_schedule(schedule_id: int) -> None:
    sched = Schedule.objects.filter(id=schedule_id).first()
    if not sched:
        return

    from parser.run_tracker import ParserRunTracker

    log_entry = ScheduleLog.objects.create(schedule=sched, status="in_progress")
    tracker = ParserRunTracker(
        "scheduled_run", schedule=sched, schedule_log=log_entry
    )

    try:
        lines: list[str] = []
        write_log(lines, sched)
        content = "".join(lines).encode("utf-8")
        sha256 = hashlib.sha256(content).hexdigest()
        key = _s3_key_for_log(sha256)
        s3_upload(key, content)

        log_entry.log_hash = sha256
        log_entry.log_path = key
        log_entry.status = "done"

        tracker.finish()
    except Exception as e:
        log_entry.log_path = None
        log_entry.log_hash = None
        log_entry.status = "done"
        logger.exception("Ошибка выполнения расписания %s", sched.name)
        tracker.finish(error=str(e))
    finally:
        log_entry.finished_at = timezone.now()
        log_entry.save(update_fields=["status", "log_hash", "log_path", "finished_at"])
