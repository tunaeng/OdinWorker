import logging
import os
import queue
import threading
import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from django.db import models
from django.http import StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone

from parser.models import ParserRun
from parser.run_tracker import ParserRunTracker

logger = logging.getLogger(__name__)


class _StreamWriter:
    def __init__(self, q: queue.Queue, tracker: ParserRunTracker):
        self._q = q
        self._tracker = tracker

    def write(self, text: str) -> None:
        self._q.put(text)
        self._tracker.write(text)

    def flush(self) -> None:
        pass


@staff_member_required
def index(request):
    return render(request, "parser/index.html")


def _run_in_thread(action: str, post_data: dict, q: queue.Queue) -> None:
    tracker = ParserRunTracker(action)
    writer = _StreamWriter(q, tracker)
    writer.write(f"[ID {tracker.id}] Запуск: {tracker.run.get_command_display()}\n")
    try:
        if action == "parse_structure":
            raw = post_data.get("university_ids", "").strip()
            ids = [int(x) for x in raw.split()]
            call_command("parse_odin_structure", *ids, stdout=writer)
        elif action == "download_works":
            activity_id = int(post_data.get("activity_id"))
            group_id = int(post_data.get("group_id"))
            call_command(
                "download_activity_works",
                str(activity_id), str(group_id),
                stdout=writer,
            )
        elif action == "extract_pptx_tasks":
            call_command("extract_pptx_tasks", stdout=writer)
        elif action == "set_marks":
            activity_id = int(post_data.get("activity_id"))
            csv_path = post_data.get("csv_path")
            call_command(
                "set_marks_from_csv",
                str(activity_id), csv_path,
                stdout=writer,
            )
            Path(csv_path).unlink(missing_ok=True)
        tracker.finish()
        writer.write(f"\n[✔] Завершено за {tracker.run.duration_display}\n")
    except Exception as e:
        tracker.finish(error=str(e))
        writer.write(f"\n[ОШИБКА] {e}\n")
    finally:
        q.put(None)


@staff_member_required
def run(request):
    if request.method != "POST":
        return render(request, "parser/index.html")

    action = request.POST.get("action")
    if action not in ("parse_structure", "download_works", "extract_pptx_tasks", "set_marks"):
        return render(request, "parser/index.html")

    if action == "set_marks":
        uploaded = request.FILES.get("csv_file")
        if not uploaded:
            return render(request, "parser/index.html")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        for chunk in uploaded.chunks():
            tmp.write(chunk)
        csv_path = tmp.name
        tmp.close()
        post_data = request.POST.copy()
        post_data["csv_path"] = csv_path
    else:
        post_data = request.POST

    q: queue.Queue = queue.Queue()
    thread = threading.Thread(
        target=_run_in_thread, args=(action, post_data, q), daemon=True
    )
    thread.start()

    def generate():
        while True:
            chunk = q.get()
            if chunk is None:
                break
            yield chunk

    return StreamingHttpResponse(generate(), content_type="text/plain")


@staff_member_required
def dashboard(request):
    last_runs = ParserRun.objects.select_related("schedule", "schedule_log")[:20]
    summary_counts = {r["status"]: r["count"] for r in
                      ParserRun.objects.values("status").annotate(
                          count=models.Count("id")
                      )}
    last_hour_count = ParserRun.objects.filter(
        started_at__gte=timezone.now() - timedelta(hours=1)
    ).count()
    return render(request, "parser/dashboard.html", {
        "last_runs": last_runs,
        "summary_counts": summary_counts,
        "last_hour_count": last_hour_count,
    })


@staff_member_required
def dashboard_partial(request):
    last_runs = ParserRun.objects.select_related("schedule", "schedule_log")[:20]
    return render(request, "parser/_runs_table.html", {
        "last_runs": last_runs,
    })
