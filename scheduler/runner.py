import hashlib
import logging
import os
from pathlib import Path

import requests
from django.core.management import call_command
from django.utils import timezone

from parser.models import Activity, Group
from scheduler.models import Schedule, ScheduleLog

logger = logging.getLogger(__name__)

LOGS_DIR = Path("media") / "schedule_logs"
ACTIVITY_INFO_URL = "https://odin.study/api/ActivitySolution/ActivityInfo"


def ensure_logs_dir():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def finalize_log(tmp_path: Path) -> tuple[str, str]:
    content = tmp_path.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()
    final_path = LOGS_DIR / f"{sha256}.log"
    if not final_path.exists():
        tmp_path.rename(final_path)
    else:
        tmp_path.unlink(missing_ok=True)
    return sha256, str(final_path)


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


def write_log(log_path: Path, schedule: Schedule) -> None:
    token = os.getenv("ODIN_BEARER_TOKEN")
    f = log_path.open("w", encoding="utf-8")

    def w(s: str):
        f.write(s)
        f.flush()

    if not token:
        w("ODIN_BEARER_TOKEN не задан\n")
        f.close()
        return

    w(f"Расписание: {schedule.name} (ID={schedule.id})\n")
    w(f"Запуск: {timezone.now():%Y-%m-%d %H:%M:%S}\n\n")

    all_activities = list(Activity.objects.values_list("id", flat=True))
    w(f"Всего активностей в БД: {len(all_activities)}\n")

    active_ids = []
    for aid in all_activities:
        w(f"  Проверяю activity {aid}... ")
        if check_activity(token, aid):
            w("доступна\n")
            active_ids.append(aid)
        else:
            w("пропущена\n")

    w(f"\nАктивных активностей: {len(active_ids)}\n\n")

    if not active_ids:
        w("Нет активных активностей для выгрузки.\n")
        f.close()
        return

    for aid in active_ids:
        act = Activity.objects.filter(id=aid).first()
        if not act:
            continue
        cohort = act.discipline.cohort
        groups = Group.objects.filter(cohort=cohort).values_list("id", flat=True)
        w(f"\nАктивность ID={aid}, поток ID={cohort.id}, групп: {len(groups)}\n")
        for gid in groups:
            w(f"  Группа ID={gid}: запуск download_activity_works...\n")
            try:
                call_command("download_activity_works", str(aid), str(gid), stdout=f)
                w(f"  Группа ID={gid}: завершено\n")
            except Exception as e:
                w(f"  Группа ID={gid}: ошибка {e}\n")
                logger.exception("Ошибка выгрузки activity=%s group=%s", aid, gid)

    w(f"\nЗавершено: {timezone.now():%Y-%m-%d %H:%M:%S}\n")
    f.close()


def run_schedule(schedule_id: int) -> None:
    ensure_logs_dir()
    sched = Schedule.objects.filter(id=schedule_id).first()
    if not sched:
        return

    log_entry = ScheduleLog.objects.create(schedule=sched, status="in_progress")
    tmp_path = LOGS_DIR / f"tmp_{log_entry.id}.log"
    log_entry.log_path = str(tmp_path)
    log_entry.save(update_fields=["log_path"])

    try:
        write_log(tmp_path, sched)
        log_hash, final_path = finalize_log(tmp_path)
        log_entry.log_hash = log_hash
        log_entry.log_path = final_path
        log_entry.status = "done"
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        log_entry.log_path = None
        log_entry.log_hash = None
        log_entry.status = "done"
        logger.exception("Ошибка выполнения расписания %s", sched.name)
    finally:
        log_entry.finished_at = timezone.now()
        log_entry.save(update_fields=["finished_at", "status", "log_hash", "log_path"])
