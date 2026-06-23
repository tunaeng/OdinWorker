# OdinWorker

Парсинг данных из LMS Odin по REST API в PostgreSQL с веб-интерфейсом,
админкой и выгрузкой работ студентов через headless-браузер (Playwright).

## Быстрый старт

```bash
git clone https://github.com/Zhidkov-Nikita/OdinWorker.git && cd OdinWorker
python3 -m venv venv
source venv/bin/activate          # Linux
# venv\Scripts\activate           # Windows
pip install -r requirements.txt
cp .env.example .env              # отредактировать — указать токены
playwright install chromium       # только для выгрузки работ
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Переменные окружения (`.env`)

| Переменная | Обязательна | Назначение |
|---|---|---|
| `ODIN_BEARER_TOKEN` | для API | Bearer-токен для REST-запросов к Odin |
| `ODIN_AUTHORIZATIONSTORE` | для браузера | JSON с jwtToken для авторизации в SPA |

Один из двух токенов обязателен для выгрузки работ (Playwright), для парсинга
структуры достаточно `ODIN_BEARER_TOKEN`.

## Веб-интерфейс (`/`)

Стартовая страница доступна после входа в админку (`/admin/`).

**Левая панель — формы запуска:**
- **Парсинг структуры** — указывается один или несколько ID университетов
  через пробел (по умолчанию `1`).
- **Выгрузка работ** — указывается ID активности и ID группы.
- **Извлечение заданий из .pptx** — парсит презентации, извлекает текст
  с последнего слайда.
- **Выставление оценок** — загружает CSV-файл (studentId, markValue)
  и отправляет оценки через REST API.

**Правая панель — консоль:** все логи выполнения команды выводятся в реальном
времени через `StreamingHttpResponse`.

## Как найти нужные ID в админке

### Университет
1. Зайти в `/admin/parser/university/`
2. Открыть свой университет — `id` виден в заголовке строки таблицы.

### Группа
1. Зайти в `/admin/parser/cohort/`, открыть нужный поток.
2. Внизу отобразятся inline-группы — `id` в первой колонке.
3. Либо сразу `/admin/parser/group/` — таблица со всеми группами.

### Активность (для выгрузки работ / выставления оценок)
1. Зайти в `/admin/parser/activity/`.
2. Колонка `id` — это ID активности, он же первый аргумент
   команд `download_activity_works` и `set_marks_from_csv`.

**Сквозная навигация:** от университета можно провалиться в дивизионы →
программы → потоки → группы и дисциплины через inline-таблицы в админке.

## Команды

### Парсинг структуры

```bash
python manage.py parse_odin_structure <university_id>
```

Обходит иерархию:

```
University → Division → EducationalProgram → Cohort → Group → Discipline → Activity
```

### Выгрузка работ студентов

```bash
python manage.py download_activity_works <activity_id> <group_id>
```

Что делает:
1. Открывает страницу активности в Chromium (headless).
2. Прокручивает виртуальный список Quasar до стабилизации `scrollHeight`.
3. Кликает по каждому студенту, ищет кнопку скачивания (SVG-иконка).
4. Скачивает файл, вычисляет SHA-256, сохраняет в БД путь до файла.
5. Ищет лекцию с таким же именем в том же потоке — скачивает презентации
   через REST API (`Activity/Contents`).

Условие повторного скачивания: если файл с таким хэшем уже есть — пропускается
(кэширование по SHA-256). Если студент не прикрепил работу — пропускается.

### Извлечение заданий из .pptx

```bash
python manage.py extract_pptx_tasks
```

Что делает:
1. Берёт все записи `LecturePresentation` из БД.
2. Парсит `.pptx` как zip-архив (стандартная библиотека `zipfile` + `re`).
3. Извлекает текст из тегов `<a:t>` последнего слайда.
4. Сохраняет текст в поле `task`.

### Выставление оценок из CSV

```bash
python manage.py set_marks_from_csv <activity_id> <csv_path>
```

CSV-файл — два столбца: `studentId`, `markValue`. Что делает:
1. Читает строки из CSV.
2. Для каждой строки отправляет POST-запрос на `/api/Mark/SetMarkForTask`.
3. Логирует HTTP-ответ для каждого студента.

Формат CSV:
```
studentId,markValue
12345,85
12346,90
```

## Хранение работ студентов

Файлы сохраняются в директорию:

```
media/solutions/<sha256>.ext
```

В базе данных (таблица `StudentWork`) хранятся:
- `student_id` — ID студента
- `activity` — FK на активность
- `file_hash` — SHA-256
- `local_path` — путь к файлу
- `solution_url` — полная ссылка на страницу решения
- `parsed_at` — дата загрузки

## Хранение презентаций лекций

Файлы сохраняются в директорию:

```
media/lections/<sha256>.ext
```

В базе данных (таблица `LecturePresentation`) хранятся:
- `activity` — FK на активность
- `file_path` — URL из API
- `local_path` — путь к файлу на диске
- `file_hash` — SHA-256
- `task` — текст задания с последнего слайда .pptx
- `parsed_at` — дата загрузки

## Модели данных

| Модель | Поля | Связь |
|---|---|---|
| **University** | id, name, city_name, library_id | — |
| **Division** | id, name, short_name, type_of_string | FK → University |
| **EducationalProgram** | id, name, short_name, degree | FK → Division |
| **Cohort** | id, name, title, start/end_education_date | FK → EducationalProgram |
| **Group** | id, title, students_number | FK → Cohort |
| **Discipline** | id, name | FK → Cohort |
| **Activity** | id, name, type, type_id, start/end_date, duration | FK → Discipline |
| **Student** | id, first_name, last_name, middle_name | FK → Group |
| **StudentWork** | student_id, activity, file_hash, local_path, solution_url, parsed_at | — |
| **LecturePresentation** | activity, file_path, local_path, file_hash, task, parsed_at | FK → Activity |

## Playwright

Для выгрузки работ требуется установить Chromium:

```bash
playwright install chromium
```

## Docker

```bash
docker compose up --build
```

Сервер будет доступен на `http://localhost:8000`. База данных PostgreSQL
и директория `media/` (скачанные файлы) сохраняются в Docker volumes.
