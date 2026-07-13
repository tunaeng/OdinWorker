import re
from datetime import datetime, timezone as tz

from django.utils import timezone

from parser.models import ParserRun

_SUMMARY_PATTERNS = [
    re.compile(r"Обработано.*?:.*?(\d+).*?\(.*?ok:\s*(\d+)", re.DOTALL),
    re.compile(r"скачано:\s*(\d+)"),
    re.compile(r"из кэша:\s*(\d+)"),
    re.compile(r"пропущено:\s*(\d+)"),
    re.compile(r"ошибки?:\s*(\d+)"),
    re.compile(r"ok:\s*(\d+)"),
]

_COMMAND_MAP = {
    "parse_structure": "parse_structure",
    "download_works": "download_works",
    "extract_pptx_tasks": "extract_pptx",
    "set_marks_from_csv": "set_marks",
}


def _choose_command(action: str) -> str:
    return _COMMAND_MAP.get(action, action)


def _extract_metrics(output: str) -> dict:
    metrics = {}
    for line in output.split("\n"):
        ok_m = re.search(r"\[✔\].*?ok:\s*(\d+)", line)
        if ok_m:
            metrics["ok"] = int(ok_m.group(1))
        cache_m = re.search(r"из кэша:\s*(\d+)", line)
        if cache_m:
            metrics["cache"] = int(cache_m.group(1))
        skip_m = re.search(r"(?:пропущено|ошибки?):\s*(\d+)", line)
        if skip_m:
            key = "skipped" if "пропущено" in line.split(":")[0] else "errors"
            metrics[key] = int(skip_m.group(1))
    return metrics


class ParserRunTracker:
    def __init__(self, command: str, schedule=None, schedule_log=None):
        self.run = ParserRun.objects.create(
            command=_choose_command(command),
            status="running",
            started_at=timezone.now(),
            schedule=schedule,
            schedule_log=schedule_log,
        )
        self._output: list[str] = []

    @property
    def id(self) -> int:
        return self.run.id

    def write(self, chunk: str) -> None:
        self._output.append(chunk)

    def finish(self, error: str | None = None) -> ParserRun:
        self.run.finished_at = timezone.now()
        self.run.duration = (
            self.run.finished_at - self.run.started_at
        ).total_seconds()
        self.run.status = "error" if error else "success"
        if error:
            self.run.error_message = error
        full_output = "".join(self._output)
        self.run.output_preview = full_output[-3000:]
        metrics = _extract_metrics(full_output)
        if metrics:
            self.run.metrics = metrics
        self.run.save(
            update_fields=[
                "finished_at", "duration", "status",
                "error_message", "output_preview", "metrics",
            ]
        )
        return self.run
