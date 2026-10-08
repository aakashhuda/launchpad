# FastAPI Modular Monolith Directory Structure

This document outlines the standard, domain-driven directory structure for a **FastAPI** backend designed as a modular monolith. 

Grouping code by business domains (features) rather than technical layers (controllers, models, services) keeps the codebase clean, highly decoupled, and easy to maintain as it grows.

---

## The Directory Layout

```text
my_fastapi_project/
├── src/
│   ├── core/                  # Global application setup and configurations
│   │   ├── __init__.py
│   │   ├── config.py          # Environment variable validation via Pydantic BaseSettings
│   │   ├── database.py        # Database connection engine and session dependency
│   │   └── security.py        # Authentication, JWT, and cryptography utilities
│   ├── shared/                # Cross-cutting, generic resources across all modules
│   │   ├── __init__.py
│   │   ├── base_model.py      # Custom base models or global DB base classes
│   │   └── exceptions.py      # Global exception handlers and error classes
│   ├── users/                 # Bounded Context: User Management Domain Module
│   │   ├── __init__.py
│   │   ├── router.py          # Endpoint definitions and API routing (APIRouter)
│   │   ├── service.py         # Primary business logic and use cases
│   │   ├── crud.py            # Low-level database operations and repositories
│   │   ├── models.py          # ORM Data models (SQLAlchemy, SQLModel, etc.)
│   │   └── schemas.py         # Pydantic validation / DTO contracts
│   ├── items/                 # Bounded Context: Another Domain Module (e.g., Inventory)
│   │   ├── __init__.py
│   │   ├── router.py
│   │   ├── service.py
│   │   ├── crud.py
│   │   ├── models.py
│   │   └── schemas.py
│   └── main.py                # App entry point; mounts routes, middleware, and handlers
├── tests/                     # Isolated unit and integration tests
│   ├── __init__.py
│   ├── test_users.py
│   └── test_items.py
├── alembic/                   # Database migration schema tracking
├── .env                       # Local application environment configuration file
├── Dockerfile                 # Containerization instruction
├── pyproject.toml             # Modern Python project metadata and dependencies
└── requirements.txt           # Standard Python package pinning
```

---

## Layer Responsibilities

### 1. Global Applications Layers

*   **`src/main.py`**: The application bootstrapping entry point. It instantiates the global `FastAPI` app object, hooks up global middlewares, provisions custom exception interceptors, and aggregates domain-specific sub-routers using `app.include_router()`.
*   **`src/core/`**: Hosts static, application-wide technical requirements. It is exclusively reserved for configuration management (Pydantic `BaseSettings`), database connectivity factories, cryptographic setups (hashing/salting), and global JWT middleware.
*   **`src/shared/`**: Contains truly cross-cutting utility abstractions. Common implementations include standardized pagination schemas, universal exception types, reusable custom string validators, or common validation tools.

### 2. Domain-Driven Modules (e.g., `users/`, `items/`)

Each domain folder operates as an isolated package encapsulating a single business capability:

*   **`router.py` (API Layer)**: Exposes the HTTP endpoint specifications using FastAPI's `APIRouter`. Responsibilities are limited to parsing request paths, validating inputs via query/path parameters, processing dependency injection triggers (e.g., fetching the DB session), and assigning response schemas.
*   **`service.py` (Business Logic Layer)**: Orchestrates core application workflows, policy rules, third-party integrations, and authorization. It functions purely in terms of business requirements and calls data access methods to pull or commit data.
*   **`crud.py` (Data Access Layer)**: Translates programmatic requirements into literal persistent state operations. Contains raw ORM database query workflows, filter criteria, updates, and hard deletions. 
*   **`models.py` (Persistence Blueprint)**: Defines database table shapes using standard declarative base setups from SQLAlchemy, SQLModel, or an equivalent ORM.
*   **`schemas.py` (Data Transfer Objects)**: Configures Pydantic structures that validate data entering the API (request payloads) and prune or format data leaving the API (response payloads).

---

## Architectural Guardrails

To prevent your modular monolith from decaying into a "spaghetti" codebase, enforce these rules:

1. **Directional Dependency**: A domain module may import entities from `core/` and `shared/`. However, `core/` and `shared/` should never import anything from a specific feature domain module.
2. **Inter-Module Boundaries**: When Module A requires capabilities from Module B, it should ideally depend on Module B's exposed `service.py` or a dedicated public interface. Avoid allowing Module A to perform direct queries on Module B's database `models.py` or `crud.py`.
3. **No Layer Skipping**: Ensure routers delegate logic to the service layer rather than executing queries or parsing extensive conditional logic directly inside endpoint functions.
