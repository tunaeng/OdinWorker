import logging
import os
from collections import Counter
from datetime import datetime

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from parser.models import (
    Activity,
    Cohort,
    Discipline,
    Division,
    EducationalProgram,
    Group,
    Student,
    University,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://odin.study/api"


def parse_datetime(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt
    except (ValueError, TypeError):
        return None


def unwrap_entity(data):
    if isinstance(data, dict) and "entity" in data:
        return data["entity"]
    return data


class OdinClient:
    def __init__(self, token):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })

    def _request(self, method, url, **kwargs):
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            if response.status_code != 200:
                logger.error("HTTP %s: %s — статус %d", method, url, response.status_code)
                return None
            data = response.json()
            if isinstance(data, dict) and data.get("isSuccess") is False:
                logger.error("API ошибка: %s — isSuccess=false", url)
                return None
            return data
        except requests.exceptions.ConnectionError as e:
            logger.error("Ошибка подключения: %s — %s", url, e)
        except requests.exceptions.Timeout as e:
            logger.error("Таймаут запроса: %s — %s", url, e)
        except requests.exceptions.RequestException as e:
            logger.error("Ошибка запроса: %s — %s", url, e)
        except ValueError as e:
            logger.error("Ошибка парсинга JSON: %s — %s", url, e)
        return None

    def get_university(self, university_id):
        return self._request("GET", f"{BASE_URL}/University/Info", params={"id": university_id})

    def get_division(self, division_id):
        return self._request("GET", f"{BASE_URL}/Division/Info", params={"id": division_id})

    def get_educational_program(self, program_id):
        return self._request("GET", f"{BASE_URL}/EducationalProgram/Info", params={"id": program_id})

    def get_cohort(self, cohort_id):
        return self._request("GET", f"{BASE_URL}/Cohort/Info", params={"id": cohort_id})

    def get_discipline_activities(self, discipline_id):
        return self._request(
            "GET", f"{BASE_URL}/Discipline/GetDisciplineActivities",
            params={"disciplineId": discipline_id},
        )

    def get_group_info(self, group_id):
        return self._request(
            "GET", f"{BASE_URL}/Group/Info",
            params={"groupId": group_id},
        )


def save_university(raw):
    data = unwrap_entity(raw)
    if not data or "id" not in data:
        logger.error("save_university: отсутствует 'id' в данных")
        return None
    university, _ = University.objects.update_or_create(
        id=data["id"],
        defaults={
            "name": data.get("name", ""),
            "city_name": data.get("cityName"),
            "library_id": data.get("libraryId"),
        },
    )
    return university


def save_division(raw, university):
    data = unwrap_entity(raw)
    if not data or "id" not in data:
        logger.error("save_division: отсутствует 'id' в данных")
        return None
    division, _ = Division.objects.update_or_create(
        id=data["id"],
        defaults={
            "university": university,
            "name": data.get("name", ""),
            "short_name": data.get("shortName"),
            "type_of_string": data.get("typeOfString"),
        },
    )
    return division


def save_educational_program(raw, division):
    data = unwrap_entity(raw)
    if not data or "id" not in data:
        logger.error("save_educational_program: отсутствует 'id' в данных")
        return None
    program, _ = EducationalProgram.objects.update_or_create(
        id=data["id"],
        defaults={
            "division": division,
            "name": data.get("name", ""),
            "short_name": data.get("shortName"),
            "degree": data.get("degree"),
        },
    )
    return program


def save_cohort(raw, educational_program):
    data = unwrap_entity(raw)
    if not data or "id" not in data:
        logger.error("save_cohort: отсутствует 'id' в данных")
        return None
    cohort, _ = Cohort.objects.update_or_create(
        id=data["id"],
        defaults={
            "educational_program": educational_program,
            "name": data.get("name"),
            "title": data.get("title"),
            "start_education_date": parse_datetime(data.get("startEducationDate")),
            "end_education_date": parse_datetime(data.get("endEducationDate")),
        },
    )
    return cohort


def save_groups_from_cohort(cohort, cohort_entity):
    """Сохранить группы из данных потока и вернуть список сохранённых объектов."""
    groups_data = cohort_entity.get("groups") or []
    saved = []
    for grp in groups_data:
        grp_id = grp.get("id")
        if not grp_id:
            continue
        obj, _ = Group.objects.update_or_create(
            id=grp_id,
            defaults={
                "cohort": cohort,
                "title": grp.get("title"),
                "students_number": grp.get("studentsNumber"),
            },
        )
        saved.append(obj)
    return saved


def save_students_for_group(client, group):
    """Запросить детальную информацию о группе и сохранить студентов."""
    raw = client.get_group_info(group.id)
    if not raw:
        return 0

    entity = unwrap_entity(raw)
    if not entity:
        return 0

    # Массив студентов может называться по-разному — перебираем варианты
    students_data = (
        entity.get("students")
        or entity.get("users")
        or entity.get("members")
        or entity.get("persons")
        or []
    )
    saved = 0
    for s in students_data:
        sid = s.get("id")
        if not sid:
            continue
        Student.objects.update_or_create(
            id=sid,
            defaults={
                "group": group,
                "first_name": s.get("firstName") or s.get("first_name"),
                "last_name": s.get("lastName") or s.get("last_name"),
                "middle_name": s.get("middleName") or s.get("middle_name"),
            },
        )
        saved += 1
    return saved


def _save_activity(discipline, act_data):
    act_id = act_data.get("id")
    if not act_id:
        return False
    Activity.objects.update_or_create(
        id=act_id,
        defaults={
            "discipline": discipline,
            "name": act_data.get("name"),
            "type": act_data.get("type"),
            "type_id": act_data.get("typeId"),
            "start_date": parse_datetime(act_data.get("startDate")),
            "end_date": parse_datetime(act_data.get("endDate")),
            "duration": act_data.get("duration"),
        },
    )
    return True


def fetch_discipline_activities(client, discipline):
    raw = client.get_discipline_activities(discipline.id)
    if not raw:
        return 0

    entity = unwrap_entity(raw)
    if not entity:
        return 0

    module_list = entity.get("moduleList") or []
    count = 0
    for module in module_list:
        for act in module.get("activities") or []:
            if _save_activity(discipline, act):
                count += 1
        for theme in module.get("themes") or []:
            for act in theme.get("activities") or []:
                if _save_activity(discipline, act):
                    count += 1
    return count


class Command(BaseCommand):
    help = "Парсинг структуры (University → Discipline) из LMS Odin"

    def add_arguments(self, parser):
        parser.add_argument(
            "university_ids",
            nargs="+",
            type=int,
            help="ID университетов для парсинга (например, 1 2 3)",
        )

    def handle(self, *args, **options):
        token = os.getenv("ODIN_BEARER_TOKEN")
        if not token:
            self.stderr.write(self.style.ERROR(
                "Не задан токен. Укажите ODIN_BEARER_TOKEN в .env или переменных окружения."
            ))
            return

        client = OdinClient(token)
        university_ids = options["university_ids"]
        has_errors = False
        stats = Counter()

        for uid in university_ids:
            raw_uni = client.get_university(uid)
            if not raw_uni:
                self.stderr.write(f"  [!] Не удалось получить университет ID={uid}")
                has_errors = True
                continue

            uni_entity = unwrap_entity(raw_uni)
            university = save_university(raw_uni)
            if not university:
                self.stderr.write(f"  [!] Ошибка сохранения университета ID={uid}")
                has_errors = True
                continue

            stats["Университетов"] += 1
            uni_name = university.name or f"ID={university.id}"
            self.stdout.write(f'[+] Университет ID={university.id} ("{uni_name}")')

            for div_ref in uni_entity.get("divisions") or []:
                div_id = div_ref.get("id")
                if not div_id:
                    continue

                raw_div = client.get_division(div_id)
                if not raw_div:
                    self.stderr.write(f"    [!] Не удалось получить институт ID={div_id}")
                    has_errors = True
                    continue

                div_entity = unwrap_entity(raw_div)
                division = save_division(raw_div, university)
                if not division:
                    has_errors = True
                    continue

                stats["Институтов"] += 1
                div_name = division.name or f"ID={division.id}"
                self.stdout.write(f'  -> Институт ID={division.id} ("{div_name}")')

                for prog_ref in div_entity.get("educationalPrograms") or []:
                    prog_id = prog_ref.get("id")
                    if not prog_id:
                        continue

                    raw_prog = client.get_educational_program(prog_id)
                    if not raw_prog:
                        self.stderr.write(f"      [!] Не удалось получить программу ID={prog_id}")
                        has_errors = True
                        continue

                    prog_entity = unwrap_entity(raw_prog)
                    program = save_educational_program(raw_prog, division)
                    if not program:
                        has_errors = True
                        continue

                    stats["Программ"] += 1
                    prog_name = (program.name or "")[:72]
                    self.stdout.write(f'    => Программа ID={program.id} ("{prog_name}")')

                    for coh_ref in prog_entity.get("cohorts") or []:
                        coh_id = coh_ref.get("id")
                        if not coh_id:
                            continue

                        raw_coh = client.get_cohort(coh_id)
                        if not raw_coh:
                            self.stderr.write(f"        [!] Не удалось получить поток ID={coh_id}")
                            has_errors = True
                            continue

                        coh_entity = unwrap_entity(raw_coh)
                        cohort = save_cohort(raw_coh, program)
                        if not cohort:
                            has_errors = True
                            continue

                        stats["Потоков"] += 1
                        coh_title = cohort.title or f"ID={cohort.id}"
                        self.stdout.write(f'      * Поток ID={cohort.id} ("{coh_title}")')

                        # Группы берутся из данных потока
                        saved_groups = save_groups_from_cohort(cohort, coh_entity)
                        if saved_groups:
                            self.stdout.write(f'          Групп: {len(saved_groups)}')
                        stats["Групп"] += len(saved_groups)

                        # Студенты — через API каждой группы
                        student_count = 0
                        for grp in saved_groups:
                            student_count += save_students_for_group(client, grp)
                        if student_count:
                            self.stdout.write(f'          Студентов: {student_count}')
                        stats["Студентов"] += student_count

                        for disc_ref in coh_entity.get("disciplines") or []:
                            disc_id = disc_ref.get("id")
                            if not disc_id:
                                continue

                            disc_name = disc_ref.get("title") or disc_ref.get("name", "")
                            discipline, _ = Discipline.objects.update_or_create(
                                id=disc_id,
                                defaults={"cohort": cohort, "name": disc_name},
                            )
                            stats["Дисциплин"] += 1

                            act_count = fetch_discipline_activities(client, discipline)
                            stats["Активностей"] += act_count
                            disc_label = disc_name[:60] or f"ID={disc_id}"
                            self.stdout.write(
                                f'          - Дисциплина ID={disc_id}'
                                f' ("{disc_label}"): {act_count} активностей'
                            )

        self.stdout.write("")
        if has_errors:
            self.stdout.write(self.style.WARNING("[✔] Парсинг завершён с ошибками."))
        else:
            self.stdout.write(self.style.SUCCESS("[✔] Парсинг успешно завершён!"))

        self.stdout.write("--- СУММАРНАЯ СТАТИСТИКА ---")
        parts = [f'{k}: {v}' for k, v in stats.items() if v > 0]
        self.stdout.write(" | ".join(parts))
