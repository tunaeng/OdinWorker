from django.contrib import admin

from parser.models import (
    Activity,
    Cohort,
    Discipline,
    Division,
    EducationalProgram,
    Group,
    LecturePresentation,
    ParserRun,
    Student,
    StudentWork,
    University,
)
admin.site.site_header = "Odin Worker Administration"

# This replaces the title in your browser's tab (e.g., "Odin Worker admin")
admin.site.site_title = "Odin Worker Admin"

# This replaces the default welcome text on the admin home page index
admin.site.index_title = "Добро пожаловать в панель управления Odin Worker"

# ---------------------------------------------------------------------------
# Инлайны
# ---------------------------------------------------------------------------

class DivisionInline(admin.TabularInline):
    model = Division
    extra = 0
    show_change_link = True
    fields = ("id", "name", "short_name", "type_of_string")


class EducationalProgramInline(admin.TabularInline):
    model = EducationalProgram
    extra = 0
    show_change_link = True
    fields = ("id", "name", "degree")


class CohortInline(admin.TabularInline):
    model = Cohort
    extra = 0
    show_change_link = True
    fields = ("id", "title", "start_education_date", "end_education_date")


class GroupInline(admin.TabularInline):
    model = Group
    extra = 0
    fields = ("id", "title", "students_number")


class DisciplineInline(admin.TabularInline):
    model = Discipline
    extra = 0
    show_change_link = True
    fields = ("id", "name")


class ActivityInline(admin.TabularInline):
    model = Activity
    extra = 0
    show_change_link = True
    fields = ("id", "name", "type", "start_date", "end_date")
    readonly_fields = ("id",)


# ---------------------------------------------------------------------------
# University
# ---------------------------------------------------------------------------

@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "city_name")
    search_fields = ("name", "city_name")
    inlines = [DivisionInline]


# ---------------------------------------------------------------------------
# Division
# ---------------------------------------------------------------------------

@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "type_of_string", "university")
    list_filter = ("university", "type_of_string")
    search_fields = ("name", "short_name", "type_of_string", "university__name")
    inlines = [EducationalProgramInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("university")


# ---------------------------------------------------------------------------
# EducationalProgram
# ---------------------------------------------------------------------------

@admin.register(EducationalProgram)
class EducationalProgramAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "degree", "division", "university_name")
    list_filter = ("degree", "division__university")
    search_fields = ("name", "short_name", "degree", "division__name")
    inlines = [CohortInline]

    @admin.display(description="Университет")
    def university_name(self, obj):
        return obj.division.university.name if obj.division_id else "—"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("division__university")


# ---------------------------------------------------------------------------
# Cohort
# ---------------------------------------------------------------------------

@admin.register(Cohort)
class CohortAdmin(admin.ModelAdmin):
    list_display = (
        "id", "title", "name", "start_education_date", "end_education_date",
        "educational_program",
    )
    list_filter = ("start_education_date", "educational_program__division__university")
    search_fields = ("id","title", "name", "educational_program__name")
    inlines = [GroupInline, DisciplineInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "educational_program__division__university",
        )


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "students_number", "cohort")
    search_fields = ("id","title", "cohort__title", "cohort__name")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "cohort__educational_program__division__university",
        )


# ---------------------------------------------------------------------------
# Discipline
# ---------------------------------------------------------------------------

@admin.register(Discipline)
class DisciplineAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "cohort", "cohort_title")
    search_fields = ("id","name", "cohort__title", "cohort__name")
    inlines = [ActivityInline]

    @admin.display(description="Поток")
    def cohort_title(self, obj):
        return obj.cohort.title if obj.cohort_id else "—"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "cohort__educational_program__division__university",
        )


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = (
        "id", "name", "type", "end_date", "discipline", "cohort_name",
    )
    list_filter = ("type", "end_date", "discipline__cohort")
    search_fields = ("id","name", "type", "discipline__name")

    @admin.display(description="Поток")
    def cohort_name(self, obj):
        cohort = obj.discipline.cohort
        return cohort.title or cohort.name or f"ID={cohort.id}"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "discipline__cohort__educational_program__division__university",
        )


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("id", "last_name", "first_name", "middle_name", "group")
    search_fields = ("id","last_name", "first_name", "middle_name")
    list_filter = ("group",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "group__cohort__educational_program__division__university",
        )


# ---------------------------------------------------------------------------
# StudentWork
# ---------------------------------------------------------------------------

@admin.register(StudentWork)
class StudentWorkAdmin(admin.ModelAdmin):
    list_display = ("id", "student_id", "activity", "status_colored", "file_hash_short", "parsed_at")
    list_filter = ("status", "parsed_at", "activity__type")
    search_fields = ("student_id", "file_hash", "activity__name", "status")

    @admin.display(description="Статус")
    def status_colored(self, obj):
        from django.utils.html import format_html
        colors = {"no_work": "#999", "has_work": "#2196F3", "has_mark": "#4CAF50"}
        c = colors.get(obj.status, "#999")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px">{}</span>',
            c, obj.get_status_display(),
        )

    @admin.display(description="SHA-256")
    def file_hash_short(self, obj):
        return obj.file_hash[:16] + "…" if obj.file_hash else "—"


# ---------------------------------------------------------------------------
# LecturePresentation
# ---------------------------------------------------------------------------

@admin.register(LecturePresentation)
class LecturePresentationAdmin(admin.ModelAdmin):
    list_display = ("activity__id","file_path_short", "file_hash_short","activity", "parsed_at",)
    list_filter = ("parsed_at",)
    search_fields = ("activity__id","file_path", "file_hash", "activity__name")

    @admin.display(description="Путь из API")
    def file_path_short(self, obj):
        return obj.file_path[:60] + "…" if obj.file_path else "—"

    @admin.display(description="SHA-256")
    def file_hash_short(self, obj):
        return obj.file_hash[:16] + "…" if obj.file_hash else "—"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "activity__discipline__cohort__educational_program__division__university",
        )


# ---------------------------------------------------------------------------
# ParserRun
# ---------------------------------------------------------------------------

@admin.register(ParserRun)
class ParserRunAdmin(admin.ModelAdmin):
    list_display = (
        "id", "command_colored", "status_colored", "started_at",
        "duration_display", "schedule_link",
    )
    list_filter = ("command", "status", "started_at")
    search_fields = ("error_message", "command", "status")
    ordering = ("-started_at",)
    readonly_fields = (
        "command", "status", "started_at", "finished_at", "duration",
        "metrics", "error_message", "output_preview", "schedule", "schedule_log",
    )

    @admin.display(description="Команда")
    def command_colored(self, obj):
        from django.utils.html import format_html
        colors = {
            "parse_structure": "#6b5b95",
            "download_works": "#2e86ab",
            "extract_pptx": "#a23b72",
            "set_marks": "#f18f01",
            "scheduled_run": "#4c9f70",
        }
        c = colors.get(obj.command, "#666")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px">{}</span>',
            c, obj.get_command_display(),
        )

    @admin.display(description="Статус")
    def status_colored(self, obj):
        from django.utils.html import format_html
        bg = {"running": "#2196F3", "success": "#4CAF50", "error": "#f44336"}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px">{}</span>',
            bg.get(obj.status, "#999"), obj.get_status_display(),
        )

    @admin.display(description="Длительность")
    def duration_display(self, obj):
        return obj.duration_display

    @admin.display(description="Расписание")
    def schedule_link(self, obj):
        if not obj.schedule_id:
            return "—"
        from django.urls import reverse
        from django.utils.html import format_html
        url = reverse("admin:scheduler_schedule_change", args=[obj.schedule_id])
        return format_html('<a href="{}">{}</a>', url, obj.schedule.name if obj.schedule else f"#{obj.schedule_id}")
