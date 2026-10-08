# 04 — Restructure Backend to `src/` Domain-Driven Modular Layout

**Status:** Planned
**Branch:** `refactor/backend-src-modular-structure`
**References:**
- `context/docs/reference/fastapi_directory_structure.md` (FastAPI modular monolith layout)
- https://jod35.github.io/fastapi-beyond-crud-docs/site/chapter4/ (routers + `src/` package)
- `context/coding-standards.md`, `context/backend-architecture-playbook.md`

---

## Goal

Reorganize the entire `backend/app/` tree into a `backend/src/` domain-driven
modular monolith so each feature owns its `router / service / crud / models /
schemas`, business and application logic stay separated per feature, and the app
remains fully working (server boots, `/api/v1/health` + SSR home respond,
alembic still sees the schema, lint/tests pass).

The restructure is timely: all feature modules are currently empty scaffolds, so
moving models into domains is low-risk. No DB schema change — the applied
migration `1aa8bf86d9fb` is untouched.

## Decisions (confirmed)

1. **Package root:** `app/` → `src/` (import paths `app.*` → `src.*`).
2. **Models:** decentralize into each domain module's `models.py` (with its
   enums inline). `db/models/` package is dissolved.
3. **API versioning:** drop the `api/v1/` aggregator; `main.py` includes each
   domain router directly with `prefix=f"{API_V1_PREFIX}/<domain>"`.
4. **Run command:** `uvicorn src.main:app --reload` (from `backend/`).

---

## Target Directory Structure

```text
backend/
├── src/
│   ├── __init__.py                 # empty (makes src a package)
│   ├── main.py                     # create_app() + app = create_app()
│   ├── core/                       # app-wide technical setup
│   │   ├── __init__.py
│   │   ├── config.py               # Pydantic Settings (was app/core/config.py)
│   │   ├── database.py             # engine, SessionLocal, get_db (was app/db/session.py)
│   │   ├── security.py             # bcrypt + JWT (was app/core/security.py)
│   │   ├── constants.py           # API_V1_PREFIX, API_VERSION (was app/core/constants.py)
│   │   ├── logging.py             # configure_logging (was app/core/logging.py)
│   │   └── dependencies.py        # NEW: home for cross-module deps (get_current_user etc.); empty for now
│   ├── shared/                     # cross-cutting utilities
│   │   ├── __init__.py
│   │   ├── base_model.py          # Base, CreatedAtMixin, TimestampMixin, enum_values (was app/db/base.py + helper)
│   │   └── exceptions.py          # register_exception_handlers (was app/core/exceptions.py)
│   ├── users/                      # User, Role, Profile, MemberFollow
│   │   ├── __init__.py
│   │   ├── router.py              # router = APIRouter() (domain-relative paths)
│   │   ├── service.py
│   │   ├── crud.py                # NEW (placeholder)
│   │   ├── models.py              # User, Role, Profile, MemberFollow + AuthProvider, LastLoginRole
│   │   └── schemas.py
│   ├── products/                   # Product, ProductTopic, ProductLaunch, Submission
│   │   ├── ... + models.py: ProductStatus, LaunchState, SubmissionStatus
│   ├── community/                 # Vote, Comment, Report (was empty dir)
│   │   ├── ... + models.py: ReportTargetType, ReportReason, ReportStatus
│   ├── topics/                    # Topic, TopicFollow (was empty dir)
│   │   ├── ... + models.py
│   ├── notifications/             # NotificationPreference, Notification, NotificationDelivery
│   │   ├── ... + models.py: NotificationChannel, NotificationDeliveryStatus
│   ├── staff/                     # StaffAction, AuditLog (was empty dir)
│   │   ├── ... + models.py
│   ├── auth/                      # no models (uses users); router/service/schemas only
│   │   ├── __init__.py, router.py, service.py, schemas.py
│   ├── integrations/              # redis.py, email.py (cross-cutting infra)
│   ├── tasks/                     # base.py, scheduler.py, jobs/ (background abstraction)
│   ├── web/                        # router.py, views.py (SSR)
│   ├── templates/                  # layout.html, home.html, error.html
│   └── static/                     # css/, js/, images/
├── alembic/
│   ├── env.py                      # imports updated to src.*
│   ├── script.py.mako
│   └── versions/1aa8bf86d9fb_initial_schema.py   # UNCHANGED
├── tests/
│   ├── conftest.py                 # import updated to src.main
│   └── (no test files yet)
├── requirements/
├── scripts/
├── pyproject.toml                  # pythonpath = ["."]
├── alembic.ini                     # unchanged (prepend_sys_path = .)
├── .env.development / .env.example / .env.production(.example)
└── README.md                       # run command updated
```

**Removed/dissolved:** `app/api/` (v1 aggregator + health + deps), `app/db/`
(base/session/models package), `app/modules/` parent (domains flatten to
`src/<domain>/`), stale `__pycache__` in empty `community/staff/topics` dirs.

---

## Layer Responsibilities (enforce during implementation)

- `router.py` — endpoint defs only; delegate to `service.py`.
- `service.py` — business logic, policy, orchestration; calls `crud.py`.
- `crud.py` — raw ORM queries/filters/updates/deletes.
- `models.py` — SQLAlchemy tables + domain enums.
- `schemas.py` — Pydantic request/response DTOs.
- `core/` — config, DB engine/session, security, logging, constants, shared deps.
- `shared/` — `Base` + mixins + `enum_values`, global exception handlers.

**Guardrails:** a domain may import `core/` and `shared/`; `core/` and `shared/`
never import a domain module. Cross-module data access goes through the other
module's `service`/`crud`, not its `models` directly (TYPE_CHECKING imports for
type hints are OK). Routers must not contain query logic.

---

## Implementation Steps (serial)

Use `git mv` for every move to preserve history. Update imports in the same
commit as each move.

### Step 0 — Branch + plan doc
- Create branch `refactor/backend-src-modular-structure`.
- Copy this plan to `context/docs/plans/04-backend-restructure-to-src-modular.md`.
- Clean stale `__pycache__` under `app/modules/{community,staff,topics}` and
  `app/api*/`.

### Step 1 — Scaffold new `src/` skeleton
- `mkdir -p src/{core,shared,users,products,community,topics,notifications,staff,auth,integrations,tasks/jobs,web,templates,static/{css,js,images}}`
- Create `src/__init__.py` (empty) and `__init__.py` in each package dir.

### Step 2 — Move `core/` + `shared/` (global layers)
- `git mv app/core/config.py src/core/config.py` (no code change).
- `git mv app/core/security.py src/core/security.py`; update import
  `from app.core.config import settings` → `from src.core.config import settings`.
- `git mv app/core/constants.py src/core/constants.py`; add `API_VERSION = "v1"`.
- `git mv app/core/logging.py src/core/logging.py` (no change).
- `git mv app/core/exceptions.py src/shared/exceptions.py` (no code change; only fastapi imports).
- `git mv app/db/base.py src/shared/base_model.py`; append `enum_values()` helper
  (moved from `app/db/models/enums.py`) into `base_model.py`.
- `git mv app/db/session.py src/core/database.py`; update import
  `from app.core.config import settings` → `from src.core.config import settings`.
- Create `src/core/dependencies.py` (empty placeholder for future auth deps).

### Step 3 — Decentralize models into domain modules
For each model file, move with `git mv`, then rewrite imports:
- `from app.db.base import Base, CreatedAtMixin, TimestampMixin` →
  `from src.shared.base_model import Base, CreatedAtMixin, TimestampMixin, enum_values`
- Remove `from app.db.models.enums import ...`; define the domain's enums inline
  at top of the same `models.py`.
- TYPE_CHECKING cross-imports: `from app.db.models.<x> import <C>` →
  `from src.<domain>.models import <C>`.

Mapping:

| From | To | Enums moved in | TYPE_CHECKING targets |
|---|---|---|---|
| `app/db/models/user.py` | `src/users/models.py` | AuthProvider, LastLoginRole | community, notifications, products, topics |
| `app/db/models/product.py` | `src/products/models.py` | ProductStatus, LaunchState, SubmissionStatus | community, topics, users |
| `app/db/models/community.py` | `src/community/models.py` | ReportTargetType, ReportReason, ReportStatus | products, users |
| `app/db/models/notification.py` | `src/notifications/models.py` | NotificationChannel, NotificationDeliveryStatus | users |
| `app/db/models/topic.py` | `src/topics/models.py` | (none) | users |
| `app/db/models/audit.py` | `src/staff/models.py` | (none) | users |

- Delete `app/db/models/enums.py` and `app/db/models/__init__.py` and
  `app/db/__init__.py` after moves (their roles are replaced).
- String-based `relationship("Product", ...)` targets resolve across modules at
  mapper-configure time, so no runtime circular imports.

### Step 4 — Move feature modules (flatten `modules/` → `src/<domain>/`)
- `auth`: `git mv app/modules/auth/{__init__,router,service,schemas}.py src/auth/`.
- `users`, `products`, `notifications`: same move; then add `crud.py`
  (placeholder, empty) to each.
- `community`, `topics`, `staff`: these dirs are empty — create fresh files in
  `src/<domain>/`: `__init__.py`, `router.py` (with `router = APIRouter()`),
  `service.py`, `crud.py`, `models.py` (from Step 3), `schemas.py`.
- Ensure every domain `router.py` defines `router = APIRouter()` so `main` can
  include it (they're empty-but-ready for later phases).
- Remove now-empty `app/modules/` tree.

### Step 5 — Move integrations, tasks, web, templates, static
- `git mv app/integrations/{__init__,redis,email}.py src/integrations/`;
  update `from app.core.config import settings` → `from src.core.config import settings`.
- `git mv app/tasks/{__init__,base,scheduler}.py src/tasks/`; `git mv app/tasks/jobs src/tasks/jobs`.
- `git mv app/web/{__init__,router,views}.py src/web/`;
  - `views.py`: `Jinja2Templates(directory="app/templates")` → robust
    `Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))`.
  - `router.py`: `from app.web.views import ...` → `from src.web.views import ...`.
- `git mv app/templates/* src/templates/`.
- `git mv app/static/* src/static/` (keep css/js/images subdirs).

### Step 6 — Rewrite `src/main.py`
New entry point (replaces `app/main.py`):

```python
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.core.config import settings
from src.core.constants import API_V1_PREFIX, API_VERSION
from src.core.logging import configure_logging
from src.shared.exceptions import register_exception_handlers
from src.auth.router import router as auth_router
from src.users.router import router as users_router
from src.products.router import router as products_router
from src.community.router import router as community_router
from src.topics.router import router as topics_router
from src.notifications.router import router as notifications_router
from src.staff.router import router as staff_router
from src.web.router import web_router


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
        name="static",
    )
    register_exception_handlers(app)

    prefix = API_V1_PREFIX
    app.include_router(auth_router, prefix=f"{prefix}/auth", tags=["auth"])
    app.include_router(users_router, prefix=f"{prefix}/users", tags=["users"])
    app.include_router(products_router, prefix=f"{prefix}/products", tags=["products"])
    app.include_router(community_router, prefix=f"{prefix}/community", tags=["community"])
    app.include_router(topics_router, prefix=f"{prefix}/topics", tags=["topics"])
    app.include_router(notifications_router, prefix=f"{prefix}/notifications", tags=["notifications"])
    app.include_router(staff_router, prefix=f"{prefix}/staff", tags=["staff"])

    @app.get(f"{prefix}/health", tags=["health"])
    def health_check():
        return {"status": "ok"}

    app.include_router(web_router)  # SSR, include_in_schema=False set in web_router
    return app


app = create_app()
```

Notes:
- Wires previously-dead `configure_logging()` + `register_exception_handlers(app)`.
- Static/templates now use `Path(__file__)` (CWD-independent) — fixes a latent bug.
- `API_V1_PREFIX` (`/api/v1`) now actually used (was hard-coded).
- Keep `src/core/dependencies.py` for future `get_current_user`; add imports there
  only when Phase 2 auth deps land.

### Step 7 — Update alembic
- `alembic/env.py`: rewrite model imports so all tables register on metadata:
  ```python
  from src.core.config import settings
  from src.shared.base_model import Base
  import src.users.models        # noqa: F401
  import src.products.models    # noqa: F401
  import src.community.models   # noqa: F401
  import src.topics.models       # noqa: F401
  import src.notifications.models  # noqa: F401
  import src.staff.models       # noqa: F401
  ```
  Keep `config.set_main_option("sqlalchemy.url", settings.database_url)` and
  `target_metadata = Base.metadata`.
- `alembic/versions/1aa8bf86d9fb_initial_schema.py`: **UNCHANGED** (never edit
  applied migrations). Verify enum type names in models still match the
  migration's `sa.Enum(..., name="...")` so autogenerate stays a no-op.
- `alembic.ini`: unchanged (`prepend_sys_path = .`).

### Step 8 — Update tests + project config
- `tests/conftest.py`: `from app.main import app` → `from src.main import app`.
- `pyproject.toml`: `[tool.pytest.ini_options]` → `pythonpath = ["."]` (so `src`
  package imports resolve when running pytest from `backend/`). Keep `testpaths =
  ["tests"]`.
- `backend/README.md`: update run command to `uvicorn src.main:app --reload --host 0.0.0.0 --port 8000`.
- `AGENTS.md` (repo root) backend commands: update dev-server line to
  `cd backend && uvicorn src.main:app --reload --host 0.0.0.0 --port 8000`.

### Step 9 — Remove the old `app/` tree
- After all moves verified, `rm -rf app/` (ensure nothing left). Confirm via
  `git status` that only renames + edits show.

### Step 10 — Update docs referencing old paths (follow-up, same PR)
- `context/phases.md`: `app/modules/*`, `app/db/models/`, `app/core/security.py`,
  `app/api/deps.py`, `app/tasks/*` → `src/<domain>/*`, `src/shared/base_model.py`,
  `src/core/security.py`, `src/core/dependencies.py`, `src/tasks/*`.
- `context/docs/plans/02-backend-implementation-phases.md`: same path swaps.

---

## Critical files to touch (quick index)

- `backend/src/main.py` (new)
- `backend/src/core/{config,security,constants,logging,dependencies,database}.py`
- `backend/src/shared/{base_model,exceptions}.py`
- `backend/src/{users,products,community,topics,notifications,staff,auth}/*.py`
- `backend/src/integrations/{redis,email}.py`
- `backend/src/web/{router,views}.py`
- `backend/alembic/env.py`
- `backend/tests/conftest.py`
- `backend/pyproject.toml`, `backend/README.md`, `AGENTS.md`
- `context/phases.md`, `context/docs/plans/02-backend-implementation-phases.md`

## Verification

1. **Import sanity:** `cd backend && python -c "import src.main; print('ok')"`.
2. **Boot server:** `cd backend && uvicorn src.main:app --reload` →
   `GET http://localhost:8000/api/v1/health` returns `{"status":"ok"}`;
   `GET /` renders the SSR home page; `/static/*` mounts.
3. **Alembic sees schema (no diff):**
   `cd backend && alembic check` (or `alembic revision --autogenerate -m verify`
   then delete the empty file) — must produce no changes against the existing DB.
4. **Lint/format:**
   `cd backend && python -m ruff check . && python -m black --check .`.
5. **Tests:** `cd backend && python -m pytest` (collection only — no test files
   yet, but conftest import must not error).
6. **Grep guard:** `grep -rn "from app\." backend/src backend/alembic backend/tests`
   must return nothing; `grep -rn "app/main" backend` must return nothing.

## Out of scope

- Implementing any feature logic in the (currently empty) modules — that's
  Phase 2+ per `context/phases.md`.
- Refresh-token storage, rate limiting, real email/Redis providers — later phases.
- Any DB schema change — migration is untouched.
