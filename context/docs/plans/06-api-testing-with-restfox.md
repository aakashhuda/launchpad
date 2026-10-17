# API Testing with Restfox

A step-by-step guide to exploring and testing the Launchpad API by hand using
[Restfox](https://restfox.dev), plus the reasoning behind the collection format
so it can be kept up to date.

- **Collection (canonical):** `restfox/launchpad-api.restfox.json`
- **Legacy:** `restfox/launchpad-auth.postman_collection.json` — a Postman v2.1
  collection limited to Phase 2 auth. Superseded by the file above; kept for
  reference only.

---

## 1. Why a Restfox-native collection

The canonical collection is exported in **Restfox's own format**
(`"exportedFrom": "Restfox-1.0.0"`), not a Postman collection.

Restfox *can* import Postman collections (`Import → Postman`), but it converts
them on the way in, and Postman scripts use a different scripting API
(`pm.collectionVariables.set(...)`) than Restfox's (`rf.setEnvVar(...)`). In a
Postman→Restfox conversion those scripts do not run, so token capture and
assertions break.

A Restfox-native export attaches its scripts as **plugins on each request**
(`item.plugins` with `code.pre_request` / `code.post_request`) using the `rf.*`
runtime, so everything — token capture, assertions, dynamic variables — works
the moment the file is imported.

To load it: **Import → "Import From" = `Restfox`**.

---

## 2. Prerequisites

- Python 3.10.12, PostgreSQL and Redis running locally.
- Restfox installed (desktop or <https://restfox.dev>) — optional, but this is
  the client the collection targets.

### Run the backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env.development          # fill SECRET_KEY / DATABASE_URL / REDIS_URL
sudo -u postgres psql -c "CREATE DATABASE launchpad_dev;"
alembic upgrade head
psql "postgresql://postgres:postgres@localhost:5432/launchpad_dev" -f scripts/seed_roles.sql

# terminal 1 — API (Swagger UI at http://localhost:8000/docs)
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# terminal 2 — background worker (notifications, exports, digests)
python -m src.tasks.worker
```

Interactive docs: **<http://localhost:8000/docs>** (Swagger UI),
`/redoc`, `/openapi.json`.

---

## 3. Import into Restfox

1. Restfox → workspace menu → **Import**.
2. **Import From:** `Restfox`.
3. Choose `restfox/launchpad-api.restfox.json`.
4. Pick the workspace to import into.

The collection tree is: **Launchpad API → Auth, Users, Products, Community,
Topics, Discovery, Notifications, Staff, Health**.

---

## 4. Variables and environments

The root group carries the variables (and a matching `Launchpad Local`
environment is provided). Edit them for your setup if needed:

| Variable             | Default                 | Purpose |
| -------------------- | ----------------------- | ------- |
| `baseUrl`            | `http://localhost:8000` | API base URL (no `/api/v1` suffix) |
| `user_email`         | `tester@example.com`    | Account used by Signup/Login |
| `user_password`      | `password123`           | Account password |
| `new_password`       | `newpass123`            | Target for reset/change password |
| `access_token`       | *(captured)*            | Set by Signup/Login/Refresh scripts |
| `refresh_token`      | *(captured)*            | Set by Signup/Login/Refresh scripts |
| `user_id`            | *(captured)*            | Set by the **Me** script |
| `profile_slug`       | *(captured)*            | Set by the **Me** script |
| `product_id`         | *(captured)*            | Set by **Create product** |
| `submission_id`      | *(captured)*            | Set by **Submit for review** |
| `comment_id`         | *(captured)*            | Set by **Comment** |
| `report_id`          | *(captured)*            | Set by **Report product** |
| `export_id`          | *(captured)*            | Set by **Request export** |
| `topic_slug`         | `ai`                    | Topic used by follow/leaderboard |
| `launch_date`        | *(script)*              | Set to today by the **Schedule launch** pre-request script |
| `snapshot_date`      | *(script)*              | Set to yesterday by the **Day snapshot** pre-request script (days freeze at close) |
| `verification_token` | *(manual)*              | Dev-only; see §6 |
| `reset_token`        | *(manual)*              | Dev-only; see §6 |
| `google_id_token`    | *(manual)*              | Real Google ID token; 501 until configured |

**Flow dependency:** run **Signup** (or **Login**) early. Its response script
saves `access_token`/`refresh_token`; every protected request sends
`Authorization: Bearer {{access_token}}`.

---

## 5. Accounts and roles

Signup is **self-serve for `member` and `founder` only**. `reviewer` and
`admin` cannot be created through the API — create them directly (roles are
seeded by `scripts/seed_roles.sql`; `ProfileService` will also create a missing
role on demand):

```bash
cd backend && .venv/bin/python - <<'PY'
from src.core.database import SessionLocal
from src.core.security import hash_password
from src.users.models import AuthProvider
from src.users.schemas import ProfileCreate, UserCreate
from src.users.service import ProfileService, UserService

db = SessionLocal()
for role, email in [("reviewer", "reviewer@example.com"), ("admin", "admin@example.com")]:
    user = UserService(db).create(
        UserCreate(email=email, first_name=role.title(), last_name="User",
                   auth_provider=AuthProvider.EMAIL),
        password_hash=hash_password("password123"),
    )
    user.email_verified = True
    ProfileService(db).create_for_user(user, ProfileCreate(role_slug=role))
    db.commit()
    print("created", role, "id", user.id)
PY
```

Log in as those accounts (change `user_email`/`user_password`, run **Login**) to
exercise the **Staff** folder.

- A single account can hold multiple profiles (`member` + `founder`): re-run
  **Signup** with the same email and a new `role` plus `confirm_add_profile: true`.
- Most actions require a **verified email** (see §6) and the right role.

---

## 6. Dev-only tokens (verify email / reset password)

Email is disabled by default (`EMAIL_ENABLED=false`), so verification and reset
tokens are not emailed. Generate them with the app's own helpers (run from
`backend/` so settings load), using the numeric `user_id` from **Me**:

```bash
# verify email
.venv/bin/python -c "from src.core.security import create_email_verification_token as t; print(t('1'))"
# reset password
.venv/bin/python -c "from src.core.security import create_password_reset_token as t; print(t('1'))"
```

Paste the value into `verification_token` / `reset_token`, then run the
**Verify Email** / **Reset Password** requests.

---

## 7. Golden-path walkthrough

With the server running and the collection imported:

1. **Auth → Signup** — creates the account, captures tokens.
2. *(optional)* set `verification_token` (§6) → **Auth → Verify Email**.
   Most member/founder actions return `403` until the email is verified.
3. **Users → Me** — captures `user_id`, `profile_slug`; confirms profiles/roles.
4. **Products → Create product** — captures `product_id`.
5. **Products → Submit for review** — captures `submission_id`.
6. Log in as a **reviewer** → **Staff → Submission queue** →
   **Staff → Decide submission** (`approve`).
7. Back as the founder → **Products → Schedule launch** — the pre-request script
   sets `launch_date` to today; the product becomes publicly visible.
8. **Discovery → Today's launches** — the product appears (velocity-ranked).
9. As a **member** → **Community → Vote**, **Comment** — captures `comment_id`.
10. **Products → Featured products**, **Discovery → Search**, **Notifications**,
    **Staff → Audit logs** — explore the rest.

Notes:

- Enums are strict: e.g. report `reason` ∈ `spam | abuse | misleading |
  copyright | other`; report resolution ∈ `resolve | dismiss`; submission
  decision ∈ `approve | reject | request_changes`.
- Emails are sent only when `EMAIL_ENABLED=true`; otherwise in-app notifications
  are still recorded (visible via **Notifications → List notifications**).

---

## 8. How the scripts work

Each captured value is a **plugin** on the request (`type: "script"`,
`code.post_request`). Scripts run in Restfox's JS runtime with:

- `rf.response.getBodyJSON()` — parsed response body.
- `rf.setEnvVar(name, value)` / `rf.getEnvVar(name)` — read/write variables.
- `test(description, fn)` + `expect(...)` (chai) — assertions shown in the Tests tab.

Example (Signup):

```js
try {
  const body = rf.response.getBodyJSON()
  if (body.access_token) rf.setEnvVar('access_token', body.access_token)
  if (body.refresh_token) rf.setEnvVar('refresh_token', body.refresh_token)
  test('response has an access_token', () => { expect(body).to.have.property('access_token') })
} catch (error) {
  test('response is JSON', () => { expect.fail('non-JSON response: ' + error.message) })
}
```

Pre-request scripts set dynamic values, e.g. the **Schedule launch** request sets
`launch_date` to today:

```js
rf.setEnvVar('launch_date', new Date().toISOString().slice(0, 10))
```

---

## 9. Endpoint map

| Folder        | Endpoints |
| ------------- | --------- |
| **Auth**      | `/api/v1/auth/{signup,login,refresh,logout,verify-email,forgot-password,reset-password,change-password,google}` |
| **Users**     | `/api/v1/users/me`, `/users/{slug}`, `/users/{slug}/follow`, `/users/me/following` |
| **Products**  | `/api/v1/products`, `/products/mine`, `/products/{id}`, `/products/{id}/submit`, `/products/{id}/launch`, `/products/featured`, `/products/{id}/export[/{exportId}/download]` |
| **Community** | `/api/v1/community/products/{id}/vote`, `/comments`, `/reports`; `/community/comments/{id}[/reports]`; `/community/reports[/{id}/assign\|/resolve]`; `/community/feed` |
| **Topics**    | `/api/v1/topics/{slug}/follow`, `/topics/me/following` |
| **Discovery** | `/api/v1/discovery/today`, `/discovery/launches/{date}`, `/discovery/topics/{slug}/leaderboard`, `/discovery/products/search` |
| **Notifications** | `/api/v1/notifications[/unread-count\|/read-all\|/preferences]`, `/notifications/{id}/read` |
| **Staff**     | `/api/v1/staff/submissions[/{id}/decision]`, `/staff/reports`, `/staff/actions`, `/staff/audit-logs`, `/staff/users/{id}/suspend\|reactivate`, `/staff/products/{id}/takedown\|restore\|feature\|unfeature` |
| **Health**    | `/api/v1/health`, `/api/v1/health/ready` |

The full, authoritative surface is the OpenAPI schema — see `/docs` or
`context/api-versioning-policy.md`. When the API changes, refresh the committed
baseline with `backend/scripts/export_openapi.py`.

---

## 10. Troubleshooting

| Symptom | Meaning |
| ------- | ------- |
| `401 Not authenticated` | Missing/expired `access_token` — run Login/Refresh. |
| `403 Email verification required` | Verify the email (§6) or use a verified account. |
| `403 Insufficient role` | The account lacks the role the endpoint needs (member/founder/reviewer/admin). |
| `403 Account suspended` | The user was suspended by an admin; reactivate it. |
| `403 Cannot vote for your own product` | Self-voting is blocked — vote from a different member. |
| `404 Product not found` | The product is a draft or under embargo (not yet on its launch day), or was taken down. |
| `409 Conflict` | Illegal state transition (double decision, duplicate report, launch cap reached, already featured, …). |
| `422 Unprocessable Entity` | Schema/validation error (bad enum value, past launch date, >3 topics, etc.). |
| `429 Too Many Requests` | Rate limited. See the `Retry-After` header; relevant for auth/vote/comment/report. |

Observability: every response echoes `X-Request-Id`; send your own to correlate
with structured logs and the audit trail.

To disable rate limiting locally for rapid clicking, set
`RATE_LIMIT_ENABLED=false` in `.env.development` and restart the API.

---

## 11. Keeping the collection up to date

The API has grown since the collection was first written (Phases 1–8). When you
add or change an endpoint:

1. Update `restfox/launchpad-api.restfox.json` — add/adjust the request node and,
   if it needs capture or assertions, its `plugins[].code`.
2. In Restfox you can also edit requests and use **Export** (Restfox format),
   then drop the result back into `restfox/`.
3. Keep `baseUrl` and the variable list above in sync.

Because this file is Restfox-native, exported→re-imported collections round-trip
cleanly (scripts included). Prefer editing it in Restfox and re-exporting over
hand-editing the JSON.
