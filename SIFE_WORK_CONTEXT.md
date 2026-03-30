# SIFE Work Context (Persistent)

Обновлено: 2026-03-30

## Текущий контекст
- Special-режим олимпиады реализован end-to-end: импорт, массовый допуск, генерация документов, рассадка, печать.
- Наблюдатель работает по поиску участников (с active attempt), а не по абстрактному поиску бланков.
- Генерация бланков и A3 работает через редактируемые DOCX шаблоны.

## Ключевые доработки последнего шага
- Добавлен конструктор рассадки по столам в админке:
  - `мест за столом` и `командный режим` для каждой аудитории.
- Добавлены настройки и валидация в `competition.special_settings`:
  - `room_layouts`, `team_room_layouts`, `default_seats_per_table`, `team_default_seats_per_table`.
- `seating-plan` и `seating-plan/print` поддерживают `tour_number`:
  - можно строить схему под конкретный тур;
  - командный тур отображается отдельной столовой структурой.
- В печати рассадки добавлены:
  - визуализация столов;
  - карточки по столам;
  - матрица мест с привязкой `стол/место`.
- В `AssignSeatUseCase` добавлен конфликт-контроль внутри стола для special-индивидуальных режимов.
- Дефолтный A3 шаблон сделан в формате книжки (две половины A3).
- В админке в модале регистраций добавлена кнопка печати командной схемы с выбором номера командного тура.

## Основные файлы текущей итерации
- `backend/src/olimpqr/presentation/api/v1/admin.py`
- `backend/src/olimpqr/application/use_cases/seating/assign_seat.py`
- `backend/src/olimpqr/domain/entities/competition.py`
- `backend/src/olimpqr/infrastructure/docx/template_generator.py`
- `backend/tests/unit/test_seating_algorithm.py`
- `frontend/src/pages/admin/CompetitionsAdminPage.tsx`

## Что осталось
- Технический прогон полного тестового контура в полноценном dev-окружении:
  - backend `pytest`;
  - frontend `npm run build`/typecheck с установленными зависимостями.
