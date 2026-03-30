# Этапы, которые выполнены

## 1. Данные и миграции
- Добавлена миграция `backend/alembic/versions/009_special_olympiad_support.py`.
- Расширены таблицы:
  - `competitions`: `is_special`, `special_tours_count`, `special_tour_modes`, `special_settings`.
  - `participants`: `institution_location`, `is_captain`.

## 2. Backend-модели и домен
- Обновлены SQLAlchemy-модели `CompetitionModel` и `ParticipantModel`.
- Обновлены доменные сущности `Competition` и `Participant`.
- Обновлены DTO/use case/repository-слои для конкурсов и участников.

## 3. API и схемы
- Обновлены схемы конкурсов, auth, профиля, admin, scan, invigilator.
- Добавлены admin-эндпоинты для особых олимпиад:
  - `POST /api/v1/admin/competitions/{competition_id}/special/import-participants`
  - `POST /api/v1/admin/competitions/{competition_id}/special/admit-all-and-download`
- Добавлены invigilator-эндпоинты:
  - `POST /api/v1/invigilator/resolve-sheet-token`
  - `GET /api/v1/invigilator/attempt/{attempt_id}/sheets`
  - `GET /api/v1/invigilator/search-sheets`
  - `GET /api/v1/invigilator/answer-sheet/{answer_sheet_id}/download`

## 4. OCR/сканы
- OCR-пайплайн связывает скан с `answer_sheets` по QR.
- Для доп. бланков (`kind=extra`) отключено влияние на итоговый балл попытки.
- В API сканов добавлен `answer_sheet_id` в ответы.

## 5. Настраиваемые Word-шаблоны (DOCX)
- Добавлен генератор Word-документов: `backend/src/olimpqr/infrastructure/docx/template_generator.py`.
- Шаблоны редактируются как обычные `.docx` файлы:
  - `backend/templates/word/special_answer_blank_template.docx`
  - `backend/templates/word/special_cover_a3_template.docx`
- При генерации подставляются токены:
  - `{{QR_IMAGE}}`, `{{TOUR_NUMBER}}`, `{{TASK_NUMBER}}`, `{{TOUR_MODE}}`, `{{TOUR_TASK}}`.
- Добавлены admin API для шаблонов:
  - `GET /api/v1/admin/special/templates`
  - `GET /api/v1/admin/special/templates/{template_kind}/download`
  - `POST /api/v1/admin/special/templates/{template_kind}/upload`
- В ZIP после массового допуска включаются DOCX-бланки/A3 + `_templates`.

## 6. Наблюдатель
- Поиск переведен на участников с активной попыткой (`/invigilator/search-participants`).
- Выдача доп.бланка возможна сразу после выбора участника, без обязательного скана QR.
- В поиске отображаются аудитория/место и доступно скачивание primary QR/PDF.

## 7. Рассадка и special-алгоритм
- Добавлены endpoints:
  - `GET /api/v1/admin/competitions/{competition_id}/seating-plan`
  - `GET /api/v1/admin/competitions/{competition_id}/seating-plan/print`
- API рассадки расширен:
  - `seat_matrix` + `seat_matrix_columns`;
  - структура столов `tables`, `table_number`, `seat_at_table`, `seats_per_table`.
- Алгоритм `AssignSeatUseCase` усилен:
  - режимы `individual` / `individual_captains` / `team`;
  - анти-соседство 3x3 по ветке учреждения;
  - анти-конфликт внутри стола (same branch at same table);
  - `captains_room_id` для капитанов;
  - чтение `room_layouts` / `team_room_layouts`.
- `ApproveAdmissionUseCase` передает `competition` в рассадку.

## 8. Командный тур и конструктор столов
- В `special_settings` добавлены и валидируются:
  - `room_layouts`;
  - `team_room_layouts`;
  - `default_seats_per_table`;
  - `team_default_seats_per_table`.
- `seating-plan`/`print` поддерживают `tour_number`:
  - можно строить и печатать схему под конкретный тур;
  - для командного тура отображается отдельная столовая компоновка.
- В админке (`CompetitionsAdminPage`) добавлен конструктор:
  - для каждой аудитории задаются `мест за столом` и `командный режим`;
  - настройки сохраняются в `special_settings`;
  - в модале регистраций добавлена печать командной схемы с выбором тура.

## 9. A3
- Дефолтный A3 шаблон обновлен под формат книжки (A3 landscape, две половины листа, сгиб, поля для заполнения, QR на внешней стороне).

## 10. Проверка
- Успешно:
  - `python -m py_compile ...` для измененных backend-файлов;
  - `python -m compileall backend/src/olimpqr`.
- Не выполнено в этом окружении:
  - `python -m pytest ...` (нет установленного `pytest`);
  - `npm run build` во frontend (нет доступного `tsc/node_modules` в окружении).

## Что осталось
- По коду critical-функционал из `sife_plan.md` закрыт.
- Остался только инфраструктурный прогон полного тестового контура в рабочем окружении проекта.
