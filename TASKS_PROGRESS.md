# Tasks Progress

All 10 tasks are implemented. Summary of files changed:

## Changed Files
### Backend
- `backend/src/olimpqr/presentation/api/v1/admin.py` — Tasks 1, 3, 6, 7, 8, 9, 10
- `backend/src/olimpqr/presentation/api/v1/scans.py` — Task 3 (pass tour_time)
- `backend/src/olimpqr/presentation/schemas/scan_schemas.py` — Task 3 (tour_time field)
- `backend/src/olimpqr/presentation/schemas/admin_schemas.py` — Tasks 3, 6 (tour_time, captains_task_numbers)
- `backend/src/olimpqr/domain/entities/attempt.py` — Task 3 (apply_task_scores with tour_time)
- `backend/src/olimpqr/application/use_cases/competitions/get_scoring_progress.py` — Task 3 (tour_time extraction)
- `backend/src/olimpqr/infrastructure/pdf/json_badge_generator.py` — Task 2 (transparent bg fix)
- `backend/src/olimpqr/presentation/utils/qr_utils.py` — Tasks 5, 6 (answer blank + captains QR patterns)

### Frontend
- `frontend/src/pages/scanner/ScannerResultsPage.tsx` — Task 1 (import button)
- `frontend/src/pages/scanner/ManualQRScoringPage.tsx` — Task 3 (time input)
- `frontend/src/components/ScoringProgressTable.tsx` — Tasks 3, 4 (time display, sort tiebreaker)
- `frontend/src/pages/admin/CompetitionsAdminPage.tsx` — Tasks 6, 7, 8, 9 (captains tasks, progress bar, template info, delete)
- `frontend/src/types/index.ts` — Tasks 3, 6 (tour_time, captains_task_numbers)

---

## Task 1: Import results table (XLSX) to update scores
**Status:** DONE  
**Changes:**
- Backend: Added `POST /admin/competitions/{id}/results-table/import` endpoint in `admin.py`. Parses XLSX (same format as export), matches participants by name (ФИО column D), applies task scores and tour time via `apply_task_scores()`. Returns count of updated + list of skipped names.
- Frontend: Added "Импорт таблицы (.xlsx)" button in `ScannerResultsPage.tsx` with file picker and result display (updated count + skipped names).

---

## Task 2: Transparent PNG background turns black in badge generation
**Status:** DONE  
**Changes:**
- `backend/src/olimpqr/infrastructure/pdf/json_badge_generator.py` — `_draw_image_bytes()`: Added PIL-based detection of RGBA/LA/P+transparency images. Flattens alpha channel onto white background (RGB) before passing to ReportLab ImageReader.

---

## Task 3: Per-participant tour time (hh.mm.ss format)
**Status:** DONE  
**Changes:**
- Backend schema: Added `tour_time: str | None` field to `QRScoreEntryRequest` (regex pattern `^\d{2}\.\d{2}\.\d{2}$`)
- Domain entity: Updated `Attempt.apply_task_scores()` to accept optional `tour_time` param, stores as `"time"` key in `task_scores[tour_number]`, excluded from score total calculation. Preserves existing time if not provided in update.
- Use case: `GetScoringProgressUseCase` extracts `tour_time` from task_scores, adds to `TourProgressResult`
- Pydantic schema: Added `tour_time: Optional[str]` to `TourProgress`
- Admin endpoint: Passes `tour_time` in scoring progress response items
- XLSX export: Per-participant `tour_prog.tour_time` takes priority over competition-wide `tour_time_map`; parsed from `hh.mm.ss` to `timedelta`
- Frontend ManualQRScoringPage: Added time input field (placeholder "чч.мм.сс") after task score inputs, sent as `tour_time` in API payload
- Frontend ScoringProgressTable: Displays per-participant time below task scores in tour cells
- TypeScript types: Added `tour_time: string | null` to `ScoringProgressTour`

---

## Task 4: Sort results table by score (desc), then by time (asc) as tiebreaker
**Status:** DONE  
**Changes:**
- Frontend `ScoringProgressTable.tsx`: Added `parseTourTimeToSeconds()` and `getTotalTimeSeconds()` helpers. Updated `sortItems()` to automatically use total time as tiebreaker when sorting by score columns — equal scores are resolved by ascending time (less time = higher rank).
- Backend XLSX: Already had COUNTIFS-based ranking formulas with time tiebreaker (`_tour_rank_formula`). Per-participant times from Task 3 now flow into those formulas correctly.

---

## Task 5: QR on answer blank = QR on A3 cover (both work for score entry)
**Status:** DONE  
**Changes:**
- `backend/src/olimpqr/presentation/utils/qr_utils.py`: Added `ANSWER_BLANK_PATTERN` regex matching `attempt:<UUID>:tour:<N>:task:<M>` format. Updated `extract_a3_cover_info()` to try both `A3_COVER_PATTERN` and `ANSWER_BLANK_PATTERN`, so scanning either A3 cover QR or answer blank QR correctly extracts `attempt_id + tour_number`.
- Note: QR codes on answer blank and A3 cover have different payloads (cover includes `:cover`, blank includes `:task:<M>`), but both now resolve to the same participant + tour context when scanned.

---

## Task 6: "Задания для капитанов" checkbox per tour
**Status:** DONE  
**Changes:**
- Frontend `CompetitionsAdminPage.tsx`:
  - The "Задания для капитанов" checkbox already existed per tour. Renamed label to "Задания для капитанов".
  - Added `specialTourCaptainsTasks` state (string[]). When checkbox is checked, an input field appears for comma-separated captain task numbers (e.g., "1,2").
  - Values saved to `special_settings.tours[].captains_task_numbers` and restored when editing.
  - Updated `extractToursFromSettings()` to parse `captains_task_numbers`.
- Backend `admin.py`:
  - Updated `_extract_special_tours()` to parse `captains_task_numbers` from settings.
  - Updated `_build_tour_configs()` to include `captains_task_numbers` in API response.
  - Updated both `admit_and_download_single()` and `admit_all_special_and_download()` to generate per-captain-task blanks in "Задания для капитанов" subfolder, with +5 extras each per task number.
- Backend `qr_utils.py`: Added `CAPTAINS_TASK_PATTERN` to resolve captains task QR codes (`attempt:<UUID>:tour:<N>:captains_task[:<M>]`).
- Schemas: Added `captains_task_numbers: list[int]` to both `TourConfigItem` (Pydantic) and `TourConfig` (TypeScript).

---

## Task 7: Progress bar for "Допустить всех + zip"
**Status:** DONE  
**Changes:**
- Frontend `CompetitionsAdminPage.tsx`: Added animated indeterminate progress bar with descriptive text ("Генерация бланков для всех участников... Это может занять несколько минут.") below the "Допустить всех + ZIP" button while `admitAndDownloadLoading` is true. Uses CSS animation (`admitProgress` keyframes). Button is disabled during loading to prevent double-clicks.

---

## Task 8: Template filenames not displayed after re-entering settings
**Status:** DONE  
**Changes:**
- Backend `admin.py`: Enhanced `GET /admin/special/templates` to return `filename`, `size_bytes`, and `modified_at` (ISO timestamp from file mtime) for each template.
- Frontend `CompetitionsAdminPage.tsx`: Added `templateInfo` state. Fetched on competition settings panel open (parallel with registration data load). Displayed as "(filename, обновлен: date)" in grey text next to each template label (answer_blank, a3_cover, badge) using `toLocaleString('ru-RU')` for date formatting.

---

## Task 9: Add delete function for answer blank and A3 templates
**Status:** DONE  
**Changes:**
- Backend `admin.py`: Added `DELETE /admin/special/templates/{kind}` endpoint. Deletes the custom template file and calls `ensure_templates_exist()` to recreate the default template.
- Frontend `CompetitionsAdminPage.tsx`: Added `templateDeletingKind` state and `handleDeleteTemplate()` function with confirmation dialog. Added "Сбросить" button (variant="danger") next to each template's "Загрузить" button for answer_blank and a3_cover templates.

---

## Task 10: UnicodeEncodeError for replaced participant in admit_and_download
**Status:** DONE  
**Changes:**
- `admin.py`: URL-encoded the `X-Warnings` header value using `quote(value, safe="")` to ensure only ASCII-safe characters in HTTP headers. The error occurred because `gen_errors` contained Cyrillic text (e.g., "Бейдж: отсутствует...") which can't be encoded as latin-1 (HTTP header requirement).
