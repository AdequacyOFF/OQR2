# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OlimpQR is an Olympic Competition Management System with anonymous QR code-based answer sheet tracking. Backend is FastAPI (Python 3.13), frontend is React+TypeScript+Vite, with PostgreSQL, Redis, MinIO, and Celery for async OCR processing and badge PDF generation.

## Commands

### Backend (from `backend/`)

```bash
poetry install                                    # Install dependencies
poetry run uvicorn olimpqr.main:app --reload      # Run dev server (port 8000)
poetry run pytest                                 # All 124 tests with coverage
poetry run pytest tests/unit -v                   # Unit tests only (54)
poetry run pytest tests/integration -v            # Integration tests (40, in-memory SQLite)
poetry run pytest tests/e2e -v                    # E2E tests (30)
poetry run pytest tests/unit/test_entities.py::TestUser -v  # Single test class
poetry run pytest --no-cov                        # Skip coverage for faster runs
poetry run ruff check src/                        # Lint
poetry run mypy src/                              # Type check
```

### Frontend (from `frontend/`)

```bash
npm install                  # Install dependencies
npm run dev                  # Dev server (port 5173)
npm run build                # Production build
npm run lint                 # ESLint
npx tsc --noEmit             # TypeScript check
```

### Docker

```bash
docker-compose up -d                              # Start all 6 services
docker-compose up -d --build backend              # Rebuild single service
docker-compose logs -f backend                    # Tail logs
docker-compose exec backend alembic upgrade head  # Run migrations
docker-compose exec backend alembic revision --autogenerate -m "description"
```

## Architecture

Clean Architecture with 4 layers. Dependencies point inward only: `presentation -> application -> domain`, with `infrastructure` implementing interfaces from both `domain` and `application`.

```
backend/src/olimpqr/
├── domain/           # Pure business logic, no external dependencies
│   ├── entities/     # User, Competition, Participant, Registration, EntryToken, Attempt, Scan, AuditLog,
│   │                 # Institution, Room, SeatAssignment, Document, AnswerSheet, ParticipantEvent
│   ├── value_objects/# UserRole, CompetitionStatus, AttemptStatus, RegistrationStatus, Token, Score,
│   │                 # EventType, SheetKind
│   ├── services/     # TokenService (HMAC-SHA256), QRService
│   └── repositories/ # Abstract repository interfaces
├── application/      # Use cases orchestrating domain logic
│   ├── use_cases/    # Single-responsibility classes with execute() method
│   ├── dto/          # Data transfer objects between layers
│   └── interfaces/   # Abstract service interfaces (OCR, PDF, Storage)
├── infrastructure/   # Technical implementations
│   ├── database/     # SQLAlchemy 2.0 async models, session, Alembic migrations
│   ├── repositories/ # SQLAlchemy repository implementations
│   ├── security/     # bcrypt passwords, PyJWT tokens, slowapi rate limiting
│   ├── ocr/          # PaddleOCR + OpenCV pipeline
│   ├── pdf/          # ReportLab answer sheet + badge PDF generation
│   ├── storage/      # MinIO S3 client
│   └── tasks/        # Celery async tasks (ocr_tasks, badge_tasks)
└── presentation/     # FastAPI API layer
    ├── api/v1/       # Endpoint routers: auth, competitions, admission, scans, results, admin,
    │                 # institutions, rooms, documents, invigilator, registrations, profiles
    │                 # Badge endpoints live in admin.py: /competitions/{id}/badge-template,
    │                 # /registrations/{id}/badges-pdf, /registrations/{id}/badges-docx,
    │                 # /special/templates/badge/photos/upload, /special/templates/badge/fonts/upload
    ├── dependencies/ # JWT auth + role-based access (require_role factory)
    └── schemas/      # Pydantic v2 request/response models
```

### Roles

Four user roles: `ADMIN`, `ADMITTER`, `SCANNER`, `INVIGILATOR`. The `invigilate was added later — it grants access to `/invigilator/*` endpoints for recording participant events and issuing extra answer sheets.

### Key Patterns

- **Repository pattern**: Abstract interfaces in `domain/repositories/`, SQLAlchemy implementations in `infrastructure/repositories/`
- **Use cases**: Instantiated in endpoint handlers with repository injection: `use_case = RegisterUserUseCase(user_repo, participant_repo)`
- **RBAC**: `require_role(UserRole.ADMIN, UserRole.ADMITTER)` dependency factory on endpoints
- **Async throughout**: async SQLAlchemy sessions, async FastAPI endpoints, Celery for background OCR
- **Entity validation**: Dataclasses with `__post_init__` validation, raise `ValueError` for domain errors
- **API errors**: Catch `ValueError` in endpoints, convert to `HTTPException`
- **Answer sheets**: Each attempt has a primary `AnswerSheet` (created at admission) and optional extra sheets. Scans link to an `AnswerSheet`, not directly to an `Attempt`.
- **Seating algorithm** (`AssignSeatUseCase`): spreads participants from the same institution across different rooms; tie-breaks on most free seats; variant = `(seat_number % variants_count) + 1`; idempotent
- **Badge system**: `BadgeTemplateModel` stores a JSON layout config (width/height, elements array) and optional background image bytes per competition. `BadgePhotoModel` stores participant photos keyed by normalized name/institution. PDF generation runs as a Celery task (`badge_tasks.py`); poll status via `/badge-tasks/{task_id}/status`, download via `/badge-tasks/{task_id}/download`. DOCX generation is synchronous via python-docx and returned as a ZIP.

### Frontend

```
frontend/src/
├── api/client.ts        # Axios with baseURL=/api/v1, JWT interceptor
├── store/authStore.ts   # Zustand: JWT token, user info, login/logout
├── router/routes.tsx    # React Router 6 with role-based route protection
├── pages/               # Organized by role: auth/, participant/, admitter/, scanner/, admin/, public/
├── components/          # Shared components (QR scanner, layout, forms)
└── types/               # TypeScript interfaces
```

Vite dev server proxies `/api` requests to the backend (`VITE_PROXY_TARGET` env var, defaults to `http://localhost:8000`).

## Testing

Integration and E2E tests use **in-memory SQLite** (`sqlite+aiosqlite:///:memory:`) with `StaticPool`. The `get_db` dependency is overridden, and tables are created/dropped per test via the `setup_database` autouse fixture.

Key fixtures in `tests/integration/conftest.py`:
- `client` — httpx `AsyncClient` with `ASGITransport`
- `db_session` — raw async SQLAlchemy session
- `admin_user` / `participant_user` — pre-created users with auth headers
- `make_auth_header(user_id, email, role)` — generates JWT Authorization header

Rate limiter is auto-disabled when `ENVIRONMENT=test`.

## Database

PostgreSQL 16 with async driver (asyncpg). Tables: `users`, `participants`, `competitions`, `registrations`, `entry_tokens`, `attempts`, `scans`, `audit_log`, `institutions`, `rooms`, `seat_assignments`, `documents`, `answer_sheets`, `participant_events`, `badge_templates`, `badge_photos`. All enum columns use `values_callable=lambda e: [member.value for member in e]` to map Python enum names (uppercase) to PostgreSQL enum values (lowercase).

Alembic migrations in `backend/alembic/`. Multiple numbered migrations (001–007+); run them in order via `alembic upgrade head`.

## Environment

Required services (all provided by `docker-compose.yml`): PostgreSQL, Redis, MinIO. Key env vars:
- `DATABASE_URL` — asyncpg connection string (use `postgres` as host in Docker)
- `SECRET_KEY` / `HMAC_SECRET_KEY` — 32+ char secrets for JWT and QR token hashing
- `MINIO_ENDPOINT` — use `minio:9000` in Docker
- `ENVIRONMENT` — `development`, `production`, or `test`

After first launch, create the admin account:
```bash
ADMIN_PASSWORD="YourPassword" docker-compose exec backend python scripts/init_admin.py
# Default email: admin@admin.com
```

## Known Constraints

- passlib is **not used** — replaced with direct `bcrypt` calls due to incompatibility with bcrypt >= 4.1
- Docker base image is `python:3.13-slim` (Debian Trixie): use `libgl1` not `libgl1-mesa-glx` for OpenCV
- Axios paths must **not** start with `/` (e.g., `'auth/login'` not `'/auth/login'`) — leading slash overrides the baseURL
- Pydantic models that have a field named `date` must use `import datetime as dt` + `dt.date` to avoid type/field name clash
- API endpoints with rate limiting (`@limiter.limit`) require a `response: Response` parameter in the signature
