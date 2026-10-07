## Launchpad Project Specifications

🚀 Product launch and discovery platform for founders and makers.

---

## Launchpad Project Specifications

🚀 **Community-driven launch platform** with moderation, ranking, voting, discovery, and founder analytics.

---

## 📌 Problem (Core Idea)

Founders need a trusted platform to launch products and get community feedback, while members need high-signal discovery instead of noisy listings.

Without moderation, anti-abuse rules, and quality ranking, product discovery becomes low trust and low value.

➡️ **Launchpad provides structured submissions, moderated publishing, fair ranking, and real-time community interaction.**

---

## 🧑‍💻 Users

| Persona  | Needs |
| -------- | ----- |
| Visitor  | Browse launches and evaluate products |
| Member   | Vote, comment, follow topics and makers |
| Founder  | Submit products, schedule launch, track performance |
| Reviewer | Moderate submissions and reported content |
| Admin    | Govern platform integrity and policy actions |

---

## ✨ Core Features

### A) Accounts & Authentication

- Email/password signup/login
- Google sign-in
- Email verification
- Password reset and change
- JWT-based API authentication

### B) Product Submission & Moderation

- Draft submission workflow
- Structured submission metadata and assets
- Reviewer outcomes: approve, reject, request changes
- Founder notifications for moderation decisions

### C) Launch Scheduling & Visibility Rules

- Founder-selectable launch day for approved products
- Daily launch quota constraints per founder
- Embargo before launch day
- Restricted edit policy after launch

### D) Voting, Comments, and Reporting

- Single vote per member/product
- No self-voting
- Threaded comments and replies
- Report pipeline for moderation

### E) Discovery, Ranking, and Topic Views

- Dynamic trending ranking for daily launches
- Immutable historical day snapshots
- Topic leaderboard views (week/month/all-time)
- Search and filtering by relevance and recency

### F) Notifications & Background Jobs

- In-app and email notifications
- User-level email preference enforcement
- Durable async processing for retries and provider downtime

---

## 🗄️ Data Model

Core entities:

- User, role, and profile
- Product, submission, topic, and launch
- Vote, comment, and report
- Notification preferences, notifications, and delivery events
- Staff actions and audit logs
- Member and topic follows

### Entity Relationship Diagram

```mermaid
erDiagram
    USERS ||--o| PROFILES : "has"
    ROLES ||--o{ PROFILES : "grants"

    PROFILES ||--o{ PRODUCTS : "founds"
    PRODUCTS ||--o| PRODUCT_LAUNCHES : "launches"
    PRODUCTS ||--o{ PRODUCT_TOPICS : "tagged"
    TOPICS ||--o{ PRODUCT_TOPICS : "tags"

    PROFILES ||--o{ SUBMISSIONS : "submits"
    PRODUCTS ||--o{ SUBMISSIONS : "moderated"

    PROFILES ||--o{ VOTES : "casts"
    PRODUCTS ||--o{ VOTES : "receives"

    PROFILES ||--o{ COMMENTS : "writes"
    PRODUCTS ||--o{ COMMENTS : "receives"
    COMMENTS ||--o{ COMMENTS : "replies to"

    PROFILES ||--o{ REPORTS : "files"
    PRODUCTS ||--o{ REPORTS : "targeted product"
    COMMENTS ||--o{ REPORTS : "targeted comment"

    PROFILES ||--o| NOTIFICATION_PREFERENCES : "configures"
    PROFILES ||--o{ NOTIFICATIONS : "receives"
    NOTIFICATIONS ||--o{ NOTIFICATION_DELIVERIES : "delivered via"

    PROFILES ||--o{ STAFF_ACTIONS : "performs"
    PROFILES ||--o{ AUDIT_LOGS : "performs"

    PROFILES ||--o{ MEMBER_FOLLOWS : "follows"
    PROFILES ||--o{ TOPIC_FOLLOWS : "follows"
    TOPICS ||--o{ TOPIC_FOLLOWS : "followed"

    USERS {
        int id PK
        string email UK
        string auth_provider
        string first_name
        string last_name
        bool email_verified
    }
    ROLES {
        int id PK
        string name
        string slug UK
        json permissions
    }
    PROFILES {
        int id PK
        int user_id FK
        int role_id FK
        string nick_name
        string slug UK
        string public_profile_url
    }
    TOPICS {
        int id PK
        string text
        string slug UK
    }
    PRODUCTS {
        int id PK
        int profile_id FK
        string name
        string one_line_pitch
        string status
    }
    PRODUCT_TOPICS {
        int id PK
        int product_id FK
        int topic_id FK
    }
    PRODUCT_LAUNCHES {
        int id PK
        int product_id FK
        date launch_date
        string state
    }
    SUBMISSIONS {
        int id PK
        int profile_id FK
        int product_id FK
        int reviewed_by_profile_id FK
        string status
    }
    VOTES {
        int id PK
        int profile_id FK
        int product_id FK
    }
    COMMENTS {
        int id PK
        int profile_id FK
        int product_id FK
        int parent_comment_id FK
        text text
    }
    REPORTS {
        int id PK
        int reporter_profile_id FK
        string target_type
        int target_product_id FK
        int target_comment_id FK
        string reason
        string status
        int assigned_reviewer_profile_id FK
        int resolved_by_profile_id FK
    }
    NOTIFICATION_PREFERENCES {
        int id PK
        int profile_id FK
        bool email_verification_enabled
        bool comment_alert_enabled
        bool daily_top_five_enabled
    }
    NOTIFICATIONS {
        int id PK
        int recipient_profile_id FK
        int actor_profile_id FK
        string event_type
        json payload
        datetime read_at
    }
    NOTIFICATION_DELIVERIES {
        int id PK
        int notification_id FK
        string channel
        string provider
        string status
    }
    STAFF_ACTIONS {
        int id PK
        int actor_profile_id FK
        string action_type
        string target_type
        int target_id
    }
    AUDIT_LOGS {
        int id PK
        int actor_profile_id FK
        string event_type
        string entity_type
        int entity_id
    }
    MEMBER_FOLLOWS {
        int id PK
        int follower_profile_id FK
        int followed_profile_id FK
    }
    TOPIC_FOLLOWS {
        int id PK
        int profile_id FK
        int topic_id FK
    }
```

The authoritative schema is defined in the SQLAlchemy models under `backend/app/db/models/` and the Alembic migration under `backend/alembic/versions/`.

---

## 🧱 Tech Stack

| Category   | Choice |
| ---------- | ------ |
| Framework  | **FastAPI** |
| Language   | Python **3.10.12** |
| Database   | PostgreSQL |
| Caching    | Redis |
| Auth       | JWT (+ social sign-in integration) |
| ORM/Migrate| SQLAlchemy + Alembic |
| Validation | Pydantic |
| Background | Async task abstraction (worker-ready) |

---

## 🗂️ Directory Structure

```text
backend/
├── alembic/
│   ├── versions/           # numbered migrations
│   ├── env.py              # migration runtime config
│   └── script.py.mako      # migration file template
├── app/
│   ├── api/                # API transport (v1 routers, deps)
│   ├── core/               # config, security, logging, constants
│   ├── db/
│   │   ├── models/         # SQLAlchemy models + domain enums
│   │   ├── repositories/   # data-access layer
│   │   ├── base.py         # declarative base + timestamp mixins
│   │   └── session.py      # engine + session factory
│   ├── integrations/       # Redis, email, external systems
│   ├── modules/            # feature logic (auth, users, products, notifications)
│   ├── tasks/              # background job abstraction
│   ├── templates/          # SSR templates
│   ├── web/                # SSR web routes
│   ├── static/             # static assets (css/js/images)
│   └── main.py             # FastAPI app factory
├── requirements/           # base.txt / dev.txt / prod.txt
├── scripts/                # operational scripts
├── tests/
│   ├── unit/
│   └── integration/
├── alembic.ini
├── pyproject.toml
├── .env.example
└── .env.development

frontend/                   # reserved for the future frontend app
```

---

## 🎨 UI / UX

Backend phase only:

- API-first architecture with `/api/v1`
- Optional SSR templates/static scaffolding for rapid iteration and parity with learning style
- Frontend application in separate `frontend/` directory to be implemented later

### Layout

- `backend/` for API + backend SSR scaffolding
- `frontend/` reserved for future dedicated frontend app

### Responsive

Frontend responsive strategy will be finalized during frontend architecture phase.

---

## 🔌 API Architecture

```mermaid
graph TD;
  Clients --> FastAPI
  FastAPI --> PostgreSQL
  FastAPI --> Redis
  FastAPI --> BackgroundJobs
  BackgroundJobs --> EmailProvider
```

---

## 🔐 Auth Flow

```mermaid
flowchart LR
  Client --> LoginOrSignup
  LoginOrSignup --> IdentityChecks
  IdentityChecks --> JWTIssue
  JWTIssue --> ProtectedAPIAccess
```

---

## 🧠 Background Task Flow

```mermaid
flowchart TD
  Event[Domain Event] --> Queue[Task Queue Abstraction]
  Queue --> Worker[Task Executor]
  Worker --> Provider[Email/Notification Provider]
  Provider --> Status[Delivery Status + Retry]
```

---

## 🗂️ Development Workflow

- Modular monolith backend structure with feature boundaries
- Migration-first DB evolution
- Environment-separated configuration (`dev` and `prod`)
- Test split across unit and integration layers
- Quality gates: lint, type checks, tests

---

## 🧭 Roadmap

### **MVP**

- Auth and profile baseline
- Product submission + moderation
- Launch scheduling + voting + comments
- Core ranking/discovery

### **Phase 2**

- Personalized feed refinement
- Founder analytics and exports
- Notification resilience upgrades

### **Future Enhancements**

- Mobile clients
- Extended abuse detection
- Advanced recommendation and ranking intelligence

---

## 📌 Status

- Backend foundation scaffolded
- Configuration and standards baseline defined
- Ready for domain modeling and feature implementation
