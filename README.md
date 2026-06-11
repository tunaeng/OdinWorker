# OdinWorker

Парсер данных из LMS Odin по REST API с сохранением в PostgreSQL и веб-админкой на Django.

## Описание

Воркер последовательно обходит иерархию сущностей Odin:

```
University → Division → EducationalProgram → Cohort → Discipline + Group
                                                          ↓
                                                      Activity
```

Каждая сущность сохраняется в отдельную таблицу PostgreSQL через `update_or_create`
(идемпотентность — повторный запуск не создаёт дубликатов).

## Локальное развёртывание

### Ubuntu Linux

```bash
# Клонировать репозиторий
git clone https://github.com/Zhidkov-Nikita/OdinWorker.git && cd OdinWorker

# Создать и активировать виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt

# Настроить токен доступа к API
cp .env.example .env
# Отредактировать .env — указать ODIN_BEARER_TOKEN
```

### Windows 10

```powershell
# Клонировать репозиторий
git clone https://github.com/Zhidkov-Nikita/OdinWorker.git && cd OdinWorker

# Создать и активировать виртуальное окружение
python -m venv venv
venv\Scripts\activate

# Установить зависимости
pip install -r requirements.txt

# Настроить токен доступа к API
copy .env.example .env
# Отредактировать .env — указать ODIN_BEARER_TOKEN
```

## Инициализация базы данных

```bash
# Применить миграции
python manage.py makemigrations
python manage.py migrate

# Создать суперпользователя для доступа в админку
python manage.py createsuperuser
```

Админка будет доступна по адресу `http://127.0.0.1:8000/admin/`.

## Запуск парсера

```bash
# ID университетов передаются через пробел
python manage.py parse_odin id
```

Пример вывода в терминале:

```
[+] Университет ID=id ("Союз Энергетиков Поволжья")
  -> Институт ID=4091 ("Программы по СЗ ТГУ")
    => Программа ID=21236 ("Инструменты искусственного интеллекта...")
      * Поток ID=82356 ("Поток 2")
          Групп: 3
          - Дисциплина ID=179268 ("Навигатор"): 12 активностей
  -> Институт ID=3601 ("БАС. Силовые ведомства")
    ...
[✔] Парсинг успешно завершён!
--- СУММАРНАЯ СТАТИСТИКА ---
Университетов: 1 | Институтов: 4 | Программ: 18 | Потоков: 42 | Групп: 12 | Дисциплин: 96 | Активностей: 245
```

## Архитектура парсера

Парсер реализован в виде management-команды `parse_odin`. Логика обхода:

1. **University** — `GET /api/University/Info?id=...`
2. **Division** — ID из поля `divisions` ответа университета,
   `GET /api/Division/Info?id=...`
3. **EducationalProgram** — ID из `educationalPrograms` дивизиона,
   `GET /api/EducationalProgram/Info?id=...`
4. **Cohort** — ID из `cohorts` программы,
   `GET /api/Cohort/Info?id=...`
5. **Group** — сохраняется из поля `groups` ответа потока (без доп. запроса)
6. **Discipline + Activity** — дисциплины из `disciplines` потока;
   активности запрашиваются через `GET /api/Discipline/GetDisciplineActivities?disciplineId=...`
   и собираются из `moduleList[].activities` и `moduleList[].themes[].activities`.

### Обработка ошибок

- При HTTP-ошибках, таймаутах и сетевых сбоях парсер логирует проблему через
  `logger.error` и продолжает со следующей сущностью.
- Ответы API проверяются на `isSuccess == true` и `status_code == 200`.
- Токен авторизации читается из `ODIN_BEARER_TOKEN` (файл `.env`).

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

Все связи — `ForeignKey` с каскадным удалением (`CASCADE`).

## Django Admin

После запуска сервера (`python manage.py runserver`) и создания суперпользователя
админка доступна по `/admin/`. Реализована сквозная навигация:

- Университет → встроенный список институтов
- Институт → встроенный список программ
- Программа → встроенный список потоков
- Поток → встроенные группы и дисциплины
- Дисциплина → просмотр активностей (с фильтром по типу и дате)
