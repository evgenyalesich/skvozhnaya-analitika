# pokerhub_lessons

Вкладка в UI:
- `lessons`
- [OverviewPage.tsx](/home/fervuld/prod/analytic-system/frontend/src/pages/OverviewPage.tsx:400)
- [RoistatLessonsTable.tsx](/home/fervuld/prod/analytic-system/frontend/src/components/RoistatLessonsTable.tsx:1)

Backend endpoint:
- `/api/reports/roistat-lessons`
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:3057)

Сервис:
- [roistat_lessons_report.py](/home/fervuld/prod/analytic-system/backend/app/services/roistat_lessons_report.py:1)

## Что показывает вкладка

Это матрица прохождения уроков PokerHub по пользователям и курсам.

По каждой вкладке курса отображается:
- список пользователей;
- сколько уроков завершено;
- дата прохождения каждого урока;
- прогресс пользователя по курсу.

Курсы идут в фиксированном порядке:
- `BASE`
- `MTT_NEW`
- `SPIN_NEW`
- `MTT`
- `SPIN`
- `CASH`

Где зафиксировано:
- [roistat_lessons_report.py](/home/fervuld/prod/analytic-system/backend/app/services/roistat_lessons_report.py:34)

## Откуда берутся данные

Основной источник уроков:
- `PhUserMirrorReplica`

Сопоставление с аналитическими пользователями:
- `raw_bot_users`

Логика такая:
1. Сначала определяется cohort `ph_user_id`, если на вкладке включены фильтры.
2. Потом из `PhUserMirrorReplica` достаются lesson/courses/groups.
3. Потом по `raw_bot_users.ph_user_id` подтягиваются `tg_user_id` и `username`.

Где это видно:
- [roistat_lessons_report.py](/home/fervuld/prod/analytic-system/backend/app/services/roistat_lessons_report.py:60)
- [roistat_lessons_report.py](/home/fervuld/prod/analytic-system/backend/app/services/roistat_lessons_report.py:205)
- [roistat_lessons_report.py](/home/fervuld/prod/analytic-system/backend/app/services/roistat_lessons_report.py:223)

## Как работают фильтры

Общие cohort-фильтры:
- дата;
- bots;
- advertising_companies;
- utm-метки;
- `user_scope`.

Дополнительные фильтры вкладки:
- `pokerhub_user_id`
- `learn_start_date_from`
- `learn_start_date_to`

На фронте:
- [useRoistatLessons.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useRoistatLessons.ts:1)

Важно:
- если по cohort-фильтрам не найдено ни одного `ph_user_id`, вкладка вернет пустые курсы, а не “всех подряд”.

## Как строятся строки пользователей

Для каждого пользователя сервис строит `summary` через:
- [pokerhub_lesson_summary.py](/home/fervuld/prod/analytic-system/backend/app/services/pokerhub_lesson_summary.py:1)

Дальше из summary собираются:
- `tg_user_id`
- `username`
- `pokerhub_user_id`
- `completed_lessons`
- `lessons[key] = дата прохождения`

Пользователь попадет в курс, если:
- по этому курсу есть lesson entries;
- или есть membership в курсе;
- или срабатывает спец-правило для post-base переходов.

## Специальная бизнес-логика

### MTT_NEW

Для `MTT_NEW` в таблицу дополнительно подтягивается модуль 2 из `MTT`.

Зачем:
- чтобы post-base funnel был виден в одной вкладке.

Где видно:
- [roistat_lessons_report.py](/home/fervuld/prod/analytic-system/backend/app/services/roistat_lessons_report.py:119)

### Post-base registry match

Если `BASE` завершен, пользователь может быть отнесен к:
- `MTT_NEW`, если есть `MTT1` или группа `mtt after base couse`;
- `SPIN_NEW`, если есть `SPIN1` или группа `spin after base couse`.

Это нужно, чтобы не потерять пользователей после BASE, даже если явная lesson-матрица еще не заполнена.

## Что означает каждая часть таблицы

### Курс

Отдельная tab для конкретного курса.

### Total lessons

Нормативное число уроков в курсе.

Задано константой:
- `BASE = 5`
- `MTT_NEW = 12`
- `SPIN_NEW = 80`
- `MTT = 36`
- `SPIN = 81`
- `CASH = 10`

Но если фактических колонок больше, берется максимум из константы и реальных колонок.

### Completed

Количество уроков, по которым есть дата прохождения.

Формула:
- `sum(1 for value in lesson_map.values() if value)`

### Lesson columns

Каждая колонка урока содержит:
- ключ урока;
- label;
- module;
- lesson;
- дату прохождения или пусто.

Сортировка колонок идет по `module/lesson`.

## Что делает фронт поверх backend

Фронт не только показывает ответ API, но и добавляет локальную аналитику:
- фильтр по диапазону completion `%`;
- фильтр “урок выполнен / не выполнен”;
- локальную сортировку по дате урока;
- локальный фильтр по диапазону дат уроков;
- экспорт текущего вида.

Где это видно:
- [RoistatLessonsTable.tsx](/home/fervuld/prod/analytic-system/frontend/src/components/RoistatLessonsTable.tsx:144)

Важно:
- backend фильтрует по `learn_start_date_from/to`;
- фронт дополнительно умеет локально скрывать уроки вне выбранного диапазона дат.

## Что проговорить на созвоне

- Почему источник уроков здесь не `raw_bot_users`, а `PhUserMirrorReplica`.
- Почему один и тот же пользователь может иметь `PokerHub ID`, но не иметь `TG ID`.
- Почему `MTT_NEW` включает часть данных из `MTT`.
- Почему пустая строка по курсу не всегда означает, что пользователя нет в курсе: иногда у него есть membership без lesson dates.
