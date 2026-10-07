# Python FastAPI Tutorial (Part 17): Testing the API - Pytest, Fixtures, and Mocking External Services

## 1. Overview

- **What this lesson teaches**: How to build a complete, professional test suite for an asynchronous FastAPI application. It covers configuring `pytest`, setting up shared test fixtures in `conftest.py`, overriding environment variables for testing, implementing the transactional rollback pattern with PostgreSQL, mocking AWS S3 file uploads using Moto, testing REST API endpoints asynchronously using `httpx.AsyncClient` with `ASGITransport`, overriding FastAPI dependencies (`app.dependency_overrides`), testing authentication and authorization (distinguishing HTTP 401 vs. 403), validating CRUD operations and pagination, and mocking asynchronous background tasks using `unittest.mock.patch` and `AsyncMock`.
- **Learning objectives**:
  - Understand the necessity of automated testing for catching regressions, refactoring code safely, and meeting industry standards.
  - Configure `pytest` and Moto as development dependencies using `uv`.
  - Avoid configuration leaks by setting environment variables in `conftest.py` prior to application module imports.
  - Configure `anyio` as the pytest plugin for async test execution and resolve conflicts with `pytest-asyncio`.
  - Implement the **transactional rollback pattern** using SQLAlchemy's `join_transaction_mode="create_savepoint"` to achieve isolated, ultra-fast database tests against PostgreSQL.
  - Use `app.dependency_overrides` to seamlessly replace production database sessions with transactional test sessions.
  - Utilize `httpx.AsyncClient` with `ASGITransport` to execute fast, in-memory HTTP requests against FastAPI without spinning up a live web server.
  - Write authentication helper functions to handle OAuth2 form data login requirements.
  - Test validation errors (HTTP 422), duplicate data rules (HTTP 400), authentication failures (HTTP 401), and ownership authorization checks (HTTP 403).
  - Test multi-part file uploads and verify side effects in S3 using Moto's virtual in-memory S3 client.
  - Mock async background functions using `unittest.mock.patch` and `AsyncMock`, adhering to the rule of patching names where they are looked up rather than where they are defined.
- **Why the topic matters**: Production applications contain many interconnected components—authentication, relational databases, S3 storage, and background email tasks. Relying solely on manual testing in Swagger UI or web browsers is slow, error-prone, and unsustainable. Automated testing gives developers the confidence that app updates will not break existing features, enables safe code refactoring, and is a non-negotiable requirement on professional engineering teams.

---

## 2. Concepts

### Synchronous vs. Asynchronous Testing in FastAPI (`TestClient` vs. `httpx.AsyncClient`)

- **What it is**:
  - `fastapi.testclient.TestClient`: A synchronous testing client provided by FastAPI (built on Starlette and HTTPX).
  - `httpx.AsyncClient` + `ASGITransport`: An asynchronous testing client from HTTPX that interacts directly with ASGI apps in memory.
- **Why it is needed**: Simple FastAPI apps can use `TestClient`. However, when an application uses an async database stack (`AsyncSession`, `create_async_engine`, async route handlers), using a synchronous `TestClient` creates awkward bridging between sync test code and async database setups.
- **How it works**: `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")` passes HTTP requests directly into the FastAPI ASGI pipeline in memory without starting a live Uvicorn web server or opening TCP sockets.
- **Important details**: `ASGITransport` does not automatically trigger application lifespan events (`startup` and `shutdown`). If an app relies on startup code (such as populating caches), `asgi-lifespan` (`LifespanManager`) can be used.

### The `anyio` Pytest Plugin

- **What it is**: An asynchronous test runner plugin included with HTTPX and FastAPI standard installations.
- **Why it is needed**: Standard `pytest` only runs synchronous test functions. Decorating test functions with `@pytest.mark.anyio` allows `pytest` to execute `async def test_*()` functions on an event loop.
- **Important details**: If `pytest-asyncio` is installed with `asyncio_mode = auto`, it conflicts with `anyio`'s built-in plugin. Remove `pytest-asyncio` or remove `asyncio_mode = auto` to prevent event loop conflicts.

### Pytest Fixtures & Dependency Injection

- **What it is**: Reusable setup/teardown functions decorated with `@pytest.fixture` in `conftest.py`.
- **Why it is needed**: Eliminates repetitive test code by providing clean, isolated inputs (database sessions, HTTP clients, mocked S3 buckets) to test functions.
- **How it works**: Pytest inspects the parameter names of test functions and automatically injects matching fixture return values.
- **Scopes**:
  - `scope="session"`: Runs once for the entire test suite execution (e.g., creating database engines, setting up table metadata).
  - `scope="function"` (default): Runs fresh for every individual test function (e.g., transactional rollback, S3 bucket state, HTTP client).

### Transactional Rollback Pattern

- **What it is**: An industry-standard pattern for database test isolation.
- **Why it is needed**: Creating and dropping database tables for every single test is extremely slow.
- **How it works**:
  1. All database tables are created once at the beginning of the test session.
  2. Before each test runs, a database connection begins a transaction.
  3. A session is bound to that connection with `join_transaction_mode="create_savepoint"`.
  4. When application route code calls `await session.commit()`, SQLAlchemy intercepts it as a savepoint (fake commit). To the application, data appears saved; to the database, the transaction remains uncommitted.
  5. After the test finishes, the transaction is explicitly rolled back (`await transaction.rollback()`), instantly erasing all test mutations without needing to recreate tables.

### Dependency Overrides (`app.dependency_overrides`)

- **What it is**: A built-in FastAPI dictionary that maps production dependency functions to test replacement functions.
- **Why it is needed**: Route handlers consume database sessions via `Depends(get_db)`. In tests, `app.dependency_overrides[get_db] = override_get_db` forces routes to receive the transactional test session instead of connecting to the production database.

### S3 Mocking with Moto

- **What it is**: A Python library (`moto[s3]`) that intercepts `boto3` AWS calls globally and redirects them to an in-memory virtual AWS environment.
- **Why it is needed**: Prevents tests from making real network calls to Amazon Web Services, avoiding costs, security key exposures, network latency, and accidental production bucket modifications.

### Function Patching & Name Lookup Rule (`unittest.mock.patch`)

- **What it is**: Temporarily replacing a function with an `AsyncMock` during test execution.
- **Why it is needed**: Prevents background tasks (such as sending password reset emails) from making real network calls to SMTP servers.
- **Golden Rule of Patching**: **Patch where the name is looked up / imported, NOT where it is defined.**
  - If `routers/users.py` executes `from email_utils import send_password_reset_email`, it creates a local reference in `routers.users`.
  - Patching `email_utils.send_password_reset_email` will fail because the router calls its local reference. You must patch `"routers.users.send_password_reset_email"`.

---

## 3. Step-by-Step Tutorial

### Step 1: Installing Development Dependencies

- **What he does**: Uses `uv` to install `pytest` and `moto[s3]` as development-only dependencies.
- **Why he does it**: Isolates testing utilities from production dependencies in `pyproject.toml`.
- **Relevant commands**:
  ```bash
  uv add --dev pytest
  uv add --dev "moto[s3]"
  ```
- **Result**: `pytest` and `moto` are added under `[dependency-groups] dev` in `pyproject.toml`.

### Step 2: Setting Up Test Directory Structure

- **What he does**: Creates a `tests/` directory containing `__init__.py`, `conftest.py`, `test_posts.py`, `test_users.py`, and moves `test_image.jpg` into `tests/`.
- **Why he does it**: Follows Pytest conventions (`test_*` naming prefix for automatic test discovery) and keeps test assets colocated with test code.
- **Directory Layout**:
  ```text
  tests/
  ├── __init__.py
  ├── conftest.py
  ├── test_image.jpg
  ├── test_posts.py
  └── test_users.py
  ```

### Step 3: Demonstrating Synchronous `TestClient` (Conceptual Comparison)

- **What he does**: Creates a temporary `tests/test_demo.py` file to demonstrate FastAPI's synchronous `TestClient` and plain Python `assert` statements.
- **Why he does it**: Explains why `TestClient` works for basic apps but becomes awkward when working with async database sessions.
- **Relevant Code**:

  ```python
  from fastapi import FastAPI
  from fastapi.testclient import TestClient

  demo_app = FastAPI()

  @demo_app.get("/")
  def demo_home():
      return {"message": "hello"}

  client = TestClient(demo_app)

  def test_homepage():
      response = client.get("/")
      assert response.status_code == 200
      assert response.json() == {"message": "hello"}
  ```

- **How it works**: Demonstrates that Pytest uses Python's standard `assert` keyword (raising `AssertionError` on failure), which is cleaner than `unittest` methods (`self.assertEqual`). Deletes `test_demo.py` after the demonstration.

### Step 4: Configuring `conftest.py` — Environment Variables and Plugin Setup

- **What he does**: Opens `conftest.py` and sets environment variables using `os.environ` **before** importing any application modules. Registers the `anyio` plugin and defines the `anyio_backend` fixture.
- **Why he does it**: `pydantic-settings` loads `.env` settings upon module import. Setting test environment variables at the top of `conftest.py` ensures the app never loads development/production database URLs or real AWS credentials.
- **Relevant Code**:

  ```python
  import os
  from collections.abc import AsyncGenerator
  import pytest

  # MUST occur before importing main app or database modules!
  os.environ["DATABASE_URL"] = "postgresql+psycopg://blog_user:blog_pass@localhost/test_blog"
  os.environ["S3_BUCKET"] = "test-bucket"
  os.environ["SECRET_KEY"] = "test-secret-key"
  os.environ["S3_ACCESS_KEY_ID"] = "testing"
  os.environ["S3_SECRET_ACCESS_KEY"] = "testing"
  os.environ["S3_REGION"] = "us-east-1"
  os.environ["AWS_ACCESS_KEY_ID"] = "testing"
  os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
  os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

  import boto3
  from httpx import ASGITransport, AsyncClient
  from moto import mock_aws
  from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
  from sqlalchemy.pool import NullPool

  from database import Base, get_db
  from main import app

  pytest_plugins = ["anyio"]

  @pytest.fixture(scope="session")
  def anyio_backend():
      return "asyncio"
  ```

- **How it works**:
  - Overrides `DATABASE_URL` to point to a dedicated `test_blog` database.
  - Overrides both `S3_*` (Pydantic settings) and `AWS_*` (boto3 SDK defaults) credentials.
  - `pytest_plugins = ["anyio"]` enables async test support.
  - `anyio_backend` returning `"asyncio"` ensures a single event loop is reused across session-scoped fixtures.

### Step 5: Provisioning the Test Database

- **What he does**: Runs `createdb` in the terminal to create the `test_blog` PostgreSQL database owned by `blog_user`.
- **Why he does it**: Tests run against a real PostgreSQL database rather than SQLite to ensure production-identical SQL behavior.
- **Relevant Command**:
  ```bash
  createdb -O blog_user test_blog
  ```

### Step 6: Implementing Database Fixtures (`conftest.py`)

- **What he does**: Creates session-scoped `test_engine` and `setup_database` fixtures, and a function-scoped `db_session` fixture implementing the transactional rollback pattern.
- **Why he does it**: Provides fast test isolation without destroying and recreating database tables for every test.
- **Relevant Code**:

  ```python
  @pytest.fixture(scope="session")
  def test_engine():
      return create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)

  @pytest.fixture(scope="session", autouse=True)
  async def setup_database(test_engine):
      async with test_engine.begin() as conn:
          await conn.run_sync(Base.metadata.create_all)
      yield
      async with test_engine.begin() as conn:
          await conn.run_sync(Base.metadata.drop_all)
      await test_engine.dispose()

  @pytest.fixture
  async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
      connection = await test_engine.connect()
      transaction = await connection.begin()

      session = AsyncSession(
          bind=connection,
          expire_on_commit=False,
          join_transaction_mode="create_savepoint",
      )

      try:
          yield session
      finally:
          await session.close()
          await transaction.rollback()
          await connection.close()
  ```

- **How it works**:
  - `NullPool` disables connection pooling to prevent closed connection errors between tests.
  - `setup_database` runs table creation once per session and drops all tables when tests finish.
  - `join_transaction_mode="create_savepoint"` turns `session.commit()` calls into savepoints, allowing `transaction.rollback()` in the `finally` block to instantly erase test data.

### Step 7: Implementing Mocked S3 and HTTP Client Fixtures (`conftest.py`)

- **What he does**: Creates a function-scoped `mocked_aws` fixture and a `client` fixture using `ASGITransport` and `app.dependency_overrides`.
- **Why he does it**: Connects HTTP test requests directly to the app in memory and intercepts AWS S3 calls.
- **Relevant Code**:

  ```python
  @pytest.fixture
  def mocked_aws():
      with mock_aws():
          s3_client = boto3.client("s3", region_name="us-east-1")
          s3_client.create_bucket(Bucket=os.environ["S3_BUCKET"])
          yield s3_client

  @pytest.fixture
  async def client(db_session, mocked_aws) -> AsyncGenerator[AsyncClient, None]:
      async def override_get_db():
          yield db_session

      app.dependency_overrides[get_db] = override_get_db

      async with AsyncClient(
          transport=ASGITransport(app=app),
          base_url="http://test",
      ) as ac:
          yield ac

      app.dependency_overrides.clear()
  ```

- **How it works**:
  - `mock_aws()` intercepts `boto3` calls and creates a fresh virtual S3 bucket per test.
  - `app.dependency_overrides[get_db] = override_get_db` injects the transactional `db_session` into route handlers.
  - `app.dependency_overrides.clear()` cleans up overrides after each test.

### Step 8: Adding Authentication Helpers (`conftest.py`)

- **What he does**: Adds `create_test_user`, `login_user`, and `auth_header` helper functions to `conftest.py`.
- **Why he does it**: Simplifies authenticating requests across protected test endpoints.
- **Relevant Code**:

  ```python
  async def create_test_user(
      client: AsyncClient,
      username: str = "testuser",
      email: str = "test@example.com",
      password: str = "testpassword123",
  ):
      response = await client.post(
          "/api/users",
          json={"username": username, "email": email, "password": password},
      )
      assert response.status_code == 201, f"Failed to create user: {response.text}"
      return response.json()

  async def login_user(
      client: AsyncClient,
      username: str = "testuser",
      password: str = "testpassword123",
  ):
      # OAuth2 password request form expects form data (data=), NOT JSON (json=)!
      response = await client.post(
          "/api/users/token",
          data={"username": username, "password": password},
      )
      assert response.status_code == 200, f"Failed to log in: {response.text}"
      return response.json()["access_token"]

  def auth_header(token: str) -> dict[str, str]:
      return {"Authorization": f"Bearer {token}"}
  ```

- **How it works**: `login_user` uses `data={` to submit `application/x-www-form-urlencoded` form data as required by FastAPI's `OAuth2PasswordRequestForm`.

### Step 9: Writing Post Route Tests (`tests/test_posts.py`)

- **What he does**: Implements comprehensive tests for post retrieval, post creation, authentication enforcement, authorization ownership checks, and pagination.
- **Why he does it**: Validates post CRUD functionality under various user permissions and query configurations.
- **Relevant Code**:

  ```python
  import pytest
  from httpx import AsyncClient
  from tests.conftest import auth_header, create_test_user, login_user

  @pytest.mark.anyio
  async def test_get_posts_empty(client: AsyncClient):
      response = await client.get("/api/posts")
      assert response.status_code == 200
      data = response.json()
      assert data["posts"] == []
      assert data["total"] == 0
      assert data["has_more"] is False

  @pytest.mark.anyio
  async def test_get_post_not_found(client: AsyncClient):
      response = await client.get("/api/posts/999")
      assert response.status_code == 404
      assert response.json()["detail"] == "Post not found"

  @pytest.mark.anyio
  async def test_create_post_success(client: AsyncClient):
      user = await create_test_user(client)
      token = await login_user(client)

      response = await client.post(
          "/api/posts",
          json={"title": "Test Post", "content": "Test content body"},
          headers=auth_header(token),
      )
      assert response.status_code == 201
      data = response.json()
      assert data["title"] == "Test Post"
      assert data["content"] == "Test content body"
      assert data["user_id"] == user["id"]
      assert data["author"]["username"] == "testuser"
      assert "id" in data
      assert "date_posted" in data

  @pytest.mark.anyio
  async def test_create_post_unauthenticated(client: AsyncClient):
      response = await client.post(
          "/api/posts",
          json={"title": "Test Post", "content": "Test content body"},
      )
      assert response.status_code == 401
      assert response.json()["detail"] == "Not authenticated"

  @pytest.mark.anyio
  async def test_update_post_success(client: AsyncClient):
      await create_test_user(client)
      token = await login_user(client)

      create_res = await client.post(
          "/api/posts",
          json={"title": "Original Title", "content": "Content"},
          headers=auth_header(token),
      )
      post_id = create_res.json()["id"]

      response = await client.patch(
          f"/api/posts/{post_id}",
          json={"title": "Updated Title"},
          headers=auth_header(token),
      )
      assert response.status_code == 200
      assert response.json()["title"] == "Updated Title"

  @pytest.mark.anyio
  async def test_update_post_unauthorized_ownership(client: AsyncClient):
      # User 1 creates post
      await create_test_user(client, username="user1", email="user1@example.com")
      token1 = await login_user(client, username="user1")
      create_res = await client.post(
          "/api/posts",
          json={"title": "User 1 Post", "content": "Content"},
          headers=auth_header(token1),
      )
      post_id = create_res.json()["id"]

      # User 2 attempts to update User 1's post
      await create_test_user(client, username="user2", email="user2@example.com")
      token2 = await login_user(client, username="user2")

      response = await client.patch(
          f"/api/posts/{post_id}",
          json={"title": "Hacked Title"},
          headers=auth_header(token2),
      )
      assert response.status_code == 403
      assert response.json()["detail"] == "Not authorized to update this post"

  @pytest.mark.anyio
  async def test_get_posts_pagination(client: AsyncClient):
      await create_test_user(client)
      token = await login_user(client)

      # Create 5 posts
      for i in range(5):
          res = await client.post(
              "/api/posts",
              json={"title": f"Post {i}", "content": f"Content {i}"},
              headers=auth_header(token),
          )
          assert res.status_code == 201

      # Test default (returns all 5)
      res_default = await client.get("/api/posts")
      assert res_default.json()["total"] == 5
      assert len(res_default.json()["posts"]) == 5
      assert res_default.json()["has_more"] is False

      # Test limit=2
      res_limit = await client.get("/api/posts?limit=2")
      assert res_limit.json()["total"] == 5
      assert len(res_limit.json()["posts"]) == 2
      assert res_limit.json()["has_more"] is True

      # Test skip=2&limit=2
      res_skip_limit = await client.get("/api/posts?skip=2&limit=2")
      assert res_skip_limit.json()["total"] == 5
      assert len(res_skip_limit.json()["posts"]) == 2
      assert res_skip_limit.json()["skip"] == 2
      assert res_skip_limit.json()["limit"] == 2
  ```

### Step 10: Writing User Route & Advanced Feature Tests (`tests/test_users.py`)

- **What he does**: Implements tests for Pydantic validation errors (HTTP 422), duplicate data enforcement (HTTP 400), password exposure security checks, multi-part S3 profile picture uploads, and background task email mocking.
- **Why he does it**: Demonstrates advanced testing techniques including S3 side-effect assertions and `unittest.mock.patch` for background tasks.
- **Relevant Code**:

  ```python
  from io import BytesIO
  from pathlib import Path
  from unittest.mock import AsyncMock, patch
  import pytest
  from httpx import AsyncClient
  from tests.conftest import auth_header, create_test_user, login_user

  @pytest.mark.anyio
  async def test_create_user_validation_error(client: AsyncClient):
      response = await client.post("/api/users", json={"username": "testuser"})
      assert response.status_code == 422
      assert "email" in response.text
      assert "password" in response.text

  @pytest.mark.anyio
  async def test_create_user_duplicate_email(client: AsyncClient):
      await create_test_user(client, username="user1", email="duplicate@example.com")
      response = await client.post(
          "/api/users",
          json={
              "username": "user2",
              "email": "duplicate@example.com",
              "password": "password123",
          },
      )
      assert response.status_code == 400
      assert response.json()["detail"] == "Email already registered"

  @pytest.mark.anyio
  async def test_create_user_success(client: AsyncClient):
      response = await client.post(
          "/api/users",
          json={
              "username": "newuser",
              "email": "newuser@example.com",
              "password": "password123",
          },
      )
      assert response.status_code == 201
      data = response.json()
      assert data["username"] == "newuser"
      assert data["email"] == "newuser@example.com"
      assert "id" in data
      assert "image_path" in data
      # Crucial security assertion: passwords MUST NEVER be returned in API responses!
      assert "password" not in data
      assert "password_hash" not in data

  @pytest.mark.anyio
  async def test_upload_profile_picture(client: AsyncClient, mocked_aws):
      user = await create_test_user(client)
      token = await login_user(client)

      # Read test image from disk
      test_dir = Path(__file__).parent
      image_path = test_dir / "test_image.jpg"
      image_bytes = image_path.read_bytes()

      # Send multi-part form data upload
      response = await client.patch(
          f"/api/users/{user['id']}/picture",
          files={"file": ("profile.jpg", BytesIO(image_bytes), "image/jpeg")},
          headers=auth_header(token),
      )
      assert response.status_code == 200
      data = response.json()
      assert data["image_file"].endswith(".jpg")
      assert "s3" in data["image_path"]

      # Verify side effect: Check that file was actually written to the mocked S3 bucket
      objects = mocked_aws.list_objects_v2(Bucket="test-bucket")
      assert objects["KeyCount"] == 1
      assert objects["Contents"]["Key"] == f"profile_pics/{data['image_file']}"

  @pytest.mark.anyio
  async def test_forgot_password_background_task(client: AsyncClient):
      user = await create_test_user(client)

      # Patch name where it is LOOKED UP in routers/users.py
      with patch(
          "routers.users.send_password_reset_email", new_callable=AsyncMock
      ) as mock_send:
          response = await client.post(
              "/api/users/forgot-password",
              json={"email": user["email"]},
          )
          assert response.status_code == 202
          assert response.json()["detail"] == (
              "If an account exists with this email, you will receive password reset instructions."
          )

          # Verify async background task execution and call arguments
          mock_send.assert_awaited_once()
          call_kwargs = mock_send.call_args.kwargs
          assert call_kwargs["to_email"] == user["email"]
          assert call_kwargs["username"] == user["username"]
          assert "token" in call_kwargs
  ```

- **How it works**:
  - `files={"file": ("profile.jpg", BytesIO(image_bytes), "image/jpeg")}` simulates a browser file upload.
  - `mocked_aws.list_objects_v2(...)` inspects the virtual Moto S3 bucket to confirm file creation.
  - `patch("routers.users.send_password_reset_email", new_callable=AsyncMock)` replaces the background task with an `AsyncMock`, ensuring no emails are sent and allowing `assert_awaited_once()` inspection.

### Step 11: Running the Test Suite

- **What he does**: Runs all tests from the terminal using `uv run pytest tests/ -v`.
- **Why he does it**: Executes the full test suite and verifies that all tests pass.
- **Relevant Command**:
  ```bash
  uv run pytest tests/ -v
  ```
- **Result**: All tests pass in less than 1 second.

---

## 4. Code Examples

### Complete `conftest.py`

```python
import os
from collections.abc import AsyncGenerator
import pytest

# Override environment variables before app imports
os.environ["DATABASE_URL"] = "postgresql+psycopg://blog_user:blog_pass@localhost/test_blog"
os.environ["S3_BUCKET"] = "test-bucket"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["S3_ACCESS_KEY_ID"] = "testing"
os.environ["S3_SECRET_ACCESS_KEY"] = "testing"
os.environ["S3_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

import boto3
from httpx import ASGITransport, AsyncClient
from moto import mock_aws
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from database import Base, get_db
from main import app

pytest_plugins = ["anyio"]

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="session")
def test_engine():
    return create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)

@pytest.fixture(scope="session", autouse=True)
async def setup_database(test_engine):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()

@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    connection = await test_engine.connect()
    transaction = await connection.begin()

    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()

@pytest.fixture
def mocked_aws():
    with mock_aws():
        s3_client = boto3.client("s3", region_name="us-east-1")
        s3_client.create_bucket(Bucket=os.environ["S3_BUCKET"])
        yield s3_client

@pytest.fixture
async def client(db_session, mocked_aws) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()

async def create_test_user(
    client: AsyncClient,
    username: str = "testuser",
    email: str = "test@example.com",
    password: str = "testpassword123",
):
    response = await client.post(
        "/api/users",
        json={"username": username, "email": email, "password": password},
    )
    assert response.status_code == 201, f"Failed to create user: {response.text}"
    return response.json()

async def login_user(
    client: AsyncClient,
    username: str = "testuser",
    password: str = "testpassword123",
):
    response = await client.post(
        "/api/users/token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, f"Failed to log in: {response.text}"
    return response.json()["access_token"]

def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
```

---

## 5. FastAPI & Python Knowledge

- **`join_transaction_mode="create_savepoint"`**: SQLAlchemy setting on `AsyncSession` that intercepts `commit()` calls and converts them into SQL savepoints. This tricks application route code into thinking data was committed while leaving the outer transaction open for global rollback.
- **`ASGITransport`**: HTTPX transport component that routes requests directly into an ASGI web application in memory. Avoids network socket latency and server process overhead.
- **`app.dependency_overrides`**: FastAPI dictionary mapping original dependency callables to test callables. Essential for swapping database connections, authentication providers, or external API clients during tests.
- **`NullPool`**: SQLAlchemy pool class that disables connection pooling. Ensures each test connection is closed cleanly without lingering pooled connections causing event loop mismatch errors.
- **`unittest.mock.AsyncMock`**: Python standard library mock class designed for `async def` functions. Tracks whether the mock was awaited (`assert_awaited_once()`) and records passed arguments.
- **OAuth2 Form Data vs. JSON**: FastAPI's `OAuth2PasswordRequestForm` expects urlencoded form data (`data={"username": ..., "password": ...}`), not JSON (`json={...}`). Submitting JSON to `/api/users/token` results in HTTP 422 errors.

---

## 6. Tips & Important Details

- **Environment Override Timing**: Always set test environment variables in `conftest.py` _before_ importing `app` or `database` modules.
- **Failure Messages in Asserts**: Pass a custom failure message string as a second argument to `assert` (e.g., `assert res.status_code == 201, f"Failed: {res.text}"`). When a test fails, Pytest outputs the full response body text, drastically speeding up debugging.
- **Matching Fixture Scopes**: Keep `anyio_backend` session-scoped (`scope="session"`) to match session-scoped database engine fixtures, avoiding "Event loop is closed" errors.
- **Pytest Command Line Flags**:
  - `uv run pytest tests/ -v`: Runs tests with verbose output showing individual test names.
  - `uv run pytest tests/test_posts.py::test_get_posts_empty`: Runs a single specific test function.
  - `uv run pytest tests/ -s`: Disables stdout capture, allowing `print()` statements to render in the terminal.
  - `uv run pytest tests/` (without `-v`): Displays compact dot notation summary output (`....`).
- **AI for Test Coverage**: AI tools (such as Claude Code) excel at identifying missing functional test cases, boundary conditions, and unhandled edge cases in existing FastAPI route handlers.

---

## 7. Errors & Pitfalls

- **`pytest-asyncio` Conflicts**: Installing `pytest-asyncio` with `asyncio_mode = auto` conflicts with `anyio`. Uninstall `pytest-asyncio` or remove `asyncio_mode = auto`.
- **Patching the Definition Instead of the Lookup**: Patching where a function is defined (`email_utils.send_password_reset_email`) instead of where it is looked up (`routers.users.send_password_reset_email`) leaves the real function active during tests.
- **Misusing `json=` for OAuth2 Login**: Sending JSON to `/api/users/token` instead of form data (`data=`) causes 422 Unprocessable Entity errors.
- **Leaking Dependency Overrides**: Failing to call `app.dependency_overrides.clear()` in fixture teardowns allows test overrides to bleed into subsequent tests.
- **Forgetting `NullPool` in Test Engine**: Using standard connection pooling in test engines can cause "connection already closed" or event loop binding errors across async tests.

---

## 8. Best Practices & Trade-offs

- **Transactional Rollbacks vs. Recreating Tables**:
  - _Transactional Rollbacks_ (Chosen): Creates tables once, rolls back transactions per test. Extremely fast (entire suite runs in <1 second) and maintains strict test isolation.
  - _Recreating Tables_: Drops and recreates tables per test. Very slow and unnecessary for most applications.
- **In-Memory ASGI Transport vs. Live Uvicorn Server**:
  - _In-Memory ASGI_: Fast, lightweight, requiring no port management or process management.
  - _Live Server_: Necessary only for full end-to-end browser testing tools (e.g., Playwright, Selenium).
- **Security Assertions in API Tests**:
  - Always write explicit negative assertions verifying sensitive fields (such as `password` or `password_hash`) are absent from API JSON responses.

---

## 9. Resources

- **GitHub Source Code Repository**: Companion code repository for Part 17 linked in the video description.
- **Pytest Official Documentation**: Reference guide for Pytest fixtures and execution flags.
- **HTTPX AsyncClient Documentation**: Guide for testing ASGI apps with `AsyncClient` and `ASGITransport`.
- **Moto Documentation**: Official documentation for mocking AWS services in Python.

---

## 10. Key Takeaways

1. Automated testing ensures application stability, simplifies refactoring, and is expected on professional engineering teams.
2. Install `pytest` and `moto[s3]` as development dependencies using `uv add --dev`.
3. Set environment variables in `conftest.py` before importing application modules to prevent settings leaks.
4. Use `httpx.AsyncClient` with `ASGITransport` for fast, in-memory async HTTP testing.
5. Decorate async test functions with `@pytest.mark.anyio`.
6. Implement the transactional rollback pattern (`join_transaction_mode="create_savepoint"`) for fast database isolation.
7. Use `NullPool` on the test database engine to prevent async event loop connection issues.
8. Override database dependencies using `app.dependency_overrides[get_db]`.
9. Clear dependency overrides (`app.dependency_overrides.clear()`) after each test.
10. Mock AWS S3 calls globally using Moto's `mock_aws()` context manager.
11. Submit form data (`data=`) when testing OAuth2 token login endpoints.
12. Verify S3 side effects using Moto's virtual client (`mocked_aws.list_objects_v2()`).
13. Mock async background tasks using `unittest.mock.patch` with `new_callable=AsyncMock`.
14. Always patch names where they are looked up (`routers.users.send_password_reset_email`), not where defined.
15. Verify background task execution using `mock_send.assert_awaited_once()`.
16. Include explicit security assertions confirming passwords are never returned in JSON responses.
17. Differentiate between validation errors (HTTP 422), business rule violations (HTTP 400), authentication failures (HTTP 401), and authorization ownership failures (HTTP 403).

---

## 11. Quick Reference

### Command Line Cheat Sheet

```bash
# Install test dependencies
uv add --dev pytest "moto[s3]"

# Run all tests in tests/ directory with verbose output
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_posts.py -v

# Run a single specific test function
uv run pytest tests/test_posts.py::test_get_posts_empty -v

# Run tests with terminal stdout output enabled
uv run pytest tests/ -s
```

### Essential Test File Syntax

```python
import pytest
from httpx import AsyncClient

@pytest.mark.anyio
async def test_example(client: AsyncClient):
    response = await client.get("/api/posts")
    assert response.status_code == 200
    assert response.json()["total"] == 0
```

---

## 12. Mental Model

- **FastAPI Testing Architecture**:
  1. **Test Invocation (`pytest`)**: Pytest discovers `tests/test_*.py` files and identifies `@pytest.mark.anyio` async test functions.
  2. **Fixture Resolution (`conftest.py`)**:
     - Pytest sets environment variables pointing to `test_blog`.
     - `setup_database` creates tables once per session.
     - `db_session` opens a connection, begins a transaction, and sets `join_transaction_mode="create_savepoint"`.
     - `mocked_aws` creates an in-memory virtual AWS S3 environment.
     - `client` overrides `get_db` with `db_session` via `app.dependency_overrides` and creates an `httpx.AsyncClient(transport=ASGITransport(app=app))`.
  3. **In-Memory Request Execution**: `client.get()` / `client.post()` passes requests directly into FastAPI's ASGI pipeline without network calls.
  4. **Route Handler & Database Interaction**:
     - Route handler receives `db_session` via overridden `Depends(get_db)`.
     - Route executes database queries and calls `session.commit()`.
     - SQLAlchemy intercepts `commit()` as a savepoint.
  5. **Background Tasks & Side Effects**:
     - S3 uploads write to Moto's virtual in-memory bucket.
     - Background email tasks execute against `AsyncMock` patches.
  6. **Assertions & Cleanup**:
     - Test function asserts on HTTP status codes, JSON response bodies, S3 object listings, and mock invocation arguments.
     - `db_session` fixture teardown executes `transaction.rollback()`, erasing all test mutations instantly.
     - `client` fixture clears `app.dependency_overrides`.
