from django.contrib import admin

from parser.models import (
    Activity,
    Cohort,
    Discipline,
    Division,
    EducationalProgram,
    Group,
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


# ---------------------------------------------------------------------------
# University
# ---------------------------------------------------------------------------

@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "city_name")
    inlines = [DivisionInline]


# ---------------------------------------------------------------------------
# Division
# ---------------------------------------------------------------------------

@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "type_of_string", "university")
    list_filter = ("university", "type_of_string")
    search_fields = ("name",)
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
    search_fields = ("name",)
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
    search_fields = ("title",)

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
    search_fields = ("name",)

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
    search_fields = ("name",)

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
    search_fields = ("last_name", "first_name")
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
    list_display = ("id", "student_id", "activity", "file_hash_short", "parsed_at")
    list_filter = ("parsed_at", "activity__type")
    search_fields = ("file_hash",)

    @admin.display(description="SHA-256")
    def file_hash_short(self, obj):
        return obj.file_hash[:16] + "…" if obj.file_hash else "—"
