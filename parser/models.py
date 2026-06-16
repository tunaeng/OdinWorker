from django.db import models
from django.utils import timezone


class University(models.Model):
    id = models.IntegerField(primary_key=True, verbose_name="ID университета")
    name = models.CharField(max_length=512, verbose_name="Название")
    city_name = models.CharField(max_length=256, verbose_name="Город", null=True, blank=True)
    library_id = models.IntegerField(verbose_name="ID библиотеки", null=True, blank=True)

    class Meta:
        verbose_name = "Университет"
        verbose_name_plural = "Университеты"

    def __str__(self):
        return self.name or f"University #{self.id}"


class Division(models.Model):
    id = models.IntegerField(primary_key=True, verbose_name="ID дивизиона")
    university = models.ForeignKey(
        University, on_delete=models.CASCADE,
        related_name="divisions", verbose_name="Университет"
    )
    name = models.CharField(max_length=512, verbose_name="Название")
    short_name = models.CharField(max_length=256, verbose_name="Короткое название", null=True, blank=True)
    type_of_string = models.CharField(max_length=256, verbose_name="Тип", null=True, blank=True)

    class Meta:
        verbose_name = "Дивизион"
        verbose_name_plural = "Дивизионы"

    def __str__(self):
        return self.name or f"Division #{self.id}"


class EducationalProgram(models.Model):
    id = models.IntegerField(primary_key=True, verbose_name="ID программы")
    division = models.ForeignKey(
        Division, on_delete=models.CASCADE,
        related_name="educational_programs", verbose_name="Дивизион"
    )
    name = models.CharField(max_length=512, verbose_name="Название")
    short_name = models.CharField(max_length=256, verbose_name="Короткое название", null=True, blank=True)
    degree = models.CharField(max_length=256, verbose_name="Степень", null=True, blank=True)

    class Meta:
        verbose_name = "Образовательная программа"
        verbose_name_plural = "Образовательные программы"

    def __str__(self):
        return self.name or f"EducationalProgram #{self.id}"


class Cohort(models.Model):
    id = models.IntegerField(primary_key=True, verbose_name="ID потока")
    educational_program = models.ForeignKey(
        EducationalProgram, on_delete=models.CASCADE,
        related_name="cohorts", verbose_name="Образовательная программа"
    )
    name = models.CharField(max_length=512, verbose_name="Имя", null=True, blank=True)
    title = models.CharField(max_length=512, verbose_name="Название", null=True, blank=True)
    start_education_date = models.DateTimeField(
        verbose_name="Дата начала обучения", null=True, blank=True
    )
    end_education_date = models.DateTimeField(
        verbose_name="Дата окончания обучения", null=True, blank=True
    )

    class Meta:
        verbose_name = "Поток"
        verbose_name_plural = "Потоки"

    def __str__(self):
        return self.title or self.name or f"Cohort #{self.id}"


class Group(models.Model):
    id = models.IntegerField(primary_key=True, verbose_name="ID группы")
    cohort = models.ForeignKey(
        Cohort, on_delete=models.CASCADE,
        related_name="groups", verbose_name="Поток"
    )
    title = models.CharField(max_length=512, verbose_name="Название", null=True, blank=True)
    students_number = models.PositiveIntegerField(
        verbose_name="Количество студентов", null=True, blank=True
    )

    class Meta:
        verbose_name = "Группа"
        verbose_name_plural = "Группы"

    def __str__(self):
        return self.title or f"Group #{self.id}"


class Discipline(models.Model):
    id = models.IntegerField(primary_key=True, verbose_name="ID дисциплины")
    cohort = models.ForeignKey(
        Cohort, on_delete=models.CASCADE,
        related_name="disciplines", verbose_name="Поток"
    )
    name = models.CharField(max_length=512, verbose_name="Название", null=True, blank=True)

    class Meta:
        verbose_name = "Дисциплина"
        verbose_name_plural = "Дисциплины"

    def __str__(self):
        return self.name or f"Discipline #{self.id}"


class Activity(models.Model):
    id = models.IntegerField(primary_key=True, verbose_name="ID активности")
    discipline = models.ForeignKey(
        Discipline, on_delete=models.CASCADE,
        related_name="activities", verbose_name="Дисциплина"
    )
    name = models.CharField(max_length=512, verbose_name="Название", null=True, blank=True)
    type = models.CharField(max_length=256, verbose_name="Тип", null=True, blank=True)
    type_id = models.IntegerField(verbose_name="ID типа", null=True, blank=True)
    start_date = models.DateTimeField(verbose_name="Дата начала", null=True, blank=True)
    end_date = models.DateTimeField(verbose_name="Дата окончания", null=True, blank=True)
    duration = models.IntegerField(verbose_name="Длительность (мин)", null=True, blank=True)

    class Meta:
        verbose_name = "Активность"
        verbose_name_plural = "Активности"

    def __str__(self):
        return self.name or f"Activity #{self.id}"


class Student(models.Model):
    id = models.IntegerField(primary_key=True, verbose_name="ID студента")
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE,
        related_name="students", verbose_name="Группа",
    )
    first_name = models.CharField(max_length=256, verbose_name="Имя", null=True, blank=True)
    last_name = models.CharField(max_length=256, verbose_name="Фамилия", null=True, blank=True)
    middle_name = models.CharField(max_length=256, verbose_name="Отчество", null=True, blank=True)

    class Meta:
        verbose_name = "Студент"
        verbose_name_plural = "Студенты"

    def __str__(self):
        parts = [p for p in (self.last_name, self.first_name, self.middle_name) if p]
        return " ".join(parts) or f"Student #{self.id}"


class StudentWork(models.Model):
    student_id = models.IntegerField(verbose_name="ID студента")
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE,
        related_name="student_works", verbose_name="Активность"
    )
    file_hash = models.CharField(max_length=64, verbose_name="SHA-256 хэш файла")
    local_path = models.CharField(max_length=1024, verbose_name="Путь к файлу на диске")
    solution_url = models.URLField(
        max_length=2048, verbose_name="Ссылка на страницу решения", null=True, blank=True
    )
    parsed_at = models.DateTimeField(
        default=timezone.now, verbose_name="Дата загрузки"
    )

    class Meta:
        verbose_name = "Работа студента"
        verbose_name_plural = "Работы студентов"
        unique_together = ("student_id", "activity")

    def __str__(self):
        return f"Student {self.student_id} / Activity {self.activity_id}"


class LecturePresentation(models.Model):
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE,
        related_name='presentations', verbose_name="Активность"
    )
    file_path = models.TextField(verbose_name="Путь из API")
    local_path = models.CharField(max_length=1024, verbose_name="Путь на диске")
    file_hash = models.CharField(max_length=64, verbose_name="SHA-256 хэш файла")
    task = models.TextField(verbose_name="Текст задания (последний слайд)", null=True, blank=True)
    parsed_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")

    class Meta:
        verbose_name = "Презентация лекции"
        verbose_name_plural = "Презентации лекций"
        unique_together = ("activity", "file_hash")

    def __str__(self):
        return f"Lecture {self.activity_id} / {self.local_path.split('/')[-1]}"
