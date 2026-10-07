# Python FastAPI Tutorial (Part 7): Sync vs Async - Converting Your App to Asynchronous

## 1. Overview

- **What this lesson teaches**: This lesson covers the fundamentals of synchronous (sync) versus asynchronous (async) execution in FastAPI and walks through converting a complete web application and REST API from synchronous SQLAlchemy to fully asynchronous execution. It demonstrates when to use `async def` versus standard `def` routes, how to configure asynchronous database engines and session factories, how to manage database table creation using modern lifespan context managers, how eager loading (`selectinload`) replaces unsupported lazy loading in async SQLAlchemy, and how to convert custom exception handlers to use FastAPI's built-in async default handlers.
- **Learning objectives**:
  - Understand the core differences between synchronous execution (blocking I/O) and asynchronous execution (non-blocking I/O).
  - Identify when asynchronous routes provide performance gains (I/O-bound tasks under concurrent load) and when synchronous routes are preferred (CPU-bound tasks, simple fast queries).
  - Understand how FastAPI executes synchronous `def` routes in a separate threadpool and asynchronous `async def` routes directly on the main event loop.
  - Install and configure asynchronous database drivers (`aiosqlite`) and dependencies (`greenlet`).
  - Convert `database.py` using `create_async_engine`, `async_sessionmaker`, `AsyncSession`, and an asynchronous generator `get_db()`.
  - Replace deprecated startup event handlers with an `@asynccontextmanager` application `lifespan` handler.
  - Prevent `greenlet` missing errors by applying eager loading (`selectinload`) to queries and `attribute_names` parameter to `db.refresh()`.
  - Update all HTML and REST API routes to use `async def`, `AsyncSession`, and `await` on asynchronous database operations.
  - Refactor exception handlers using FastAPI's default `http_exception_handler` and `request_validation_exception_handler`.
- **Why the topic matters**: Converting a web application to asynchronous execution allows it to handle thousands of concurrent I/O-bound requests (such as database queries, external API calls, and file operations) without blocking the server. Understanding FastAPI's dual execution model ensures developers avoid catastrophic performance bottlenecks like running blocking synchronous code inside `async def` routes.

---

## 2. Concepts

### Synchronous vs. Asynchronous Execution

- **What it is**:
  - **Synchronous (Sync)**: Code executes sequentially, line by line. Each operation must finish before the next begins.
  - **Asynchronous (Async)**: Code allows the program to pause waiting tasks (like I/O) and work on other incoming tasks concurrently on a single thread.
- **Why it is needed**: In web applications, waiting for external systems (database queries, network calls, disk reads) leaves the CPU idle. Async execution reclaims this idle waiting time to process other concurrent user requests.
- **How it works**:
  - _Subway Analogy (Sync)_: A single worker builds one customer's sandwich completely from start to finish before taking the next customer's order.
  - _McDonald's Analogy (Async)_: A worker takes your order and immediately moves on to the next customer while kitchen staff prepare your food in the background.
- **Important details**: Asynchronous execution improves concurrency, not necessarily raw execution speed for a single isolated request.
- **Examples**: Waiting for a database query result (`await db.execute(...)`) frees the event loop to serve another user's incoming HTTP request.

### I/O-Bound vs. CPU-Bound Tasks

- **What it is**: Classification of computational work based on where bottlenecks occur:
  - **I/O-Bound**: Bottlenecked by waiting for external input/output (databases, network APIs, disk files).
  - **CPU-Bound**: Bottlenecked by intense CPU calculation (data crunching, image processing, machine learning).
- **Why it is needed**: Asynchronous programming optimizes _only_ I/O-bound tasks because it yields execution while waiting. CPU-bound tasks keep the CPU fully engaged, leaving no idle time to yield.
- **How it works**: For I/O-bound tasks, `await` yields control back to the event loop. For CPU-bound tasks, async provides no performance benefit and can add minor overhead.
- **Examples**: Database queries are I/O-bound; resizing images or calculating prime numbers are CPU-bound.

### FastAPI Threadpool (`def`) vs. Event Loop (`async def`) Execution

- **What it is**: The underlying mechanism FastAPI uses to handle synchronous and asynchronous route handlers.
- **Why it is needed**: Prevents synchronous blocking code from freezing the web server while offering maximum efficiency for true async handlers.
- **How it works**:
  - **Standard `def` Routes**: FastAPI automatically runs synchronous routes inside a background **threadpool**. The main event loop remains unblocked, allowing concurrent requests to be handled smoothly across threads.
  - **`async def` Routes**: FastAPI runs these routes directly on the **main event loop**. They must strictly use non-blocking non-synchronous operations with `await`.
- **Important details**: Running blocking synchronous code (like `requests.get()` or standard synchronous SQLAlchemy) inside an `async def` route blocks the entire main event loop, halting all server processing—making it worse than using a standard `def` route.
- **Examples**: `@app.get("/") def home(): ...` runs in threadpool; `@app.get("/") async def home(): ...` runs on the main event loop.

### Async Database Drivers & `aiosqlite`

- **What it is**: An asynchronous database driver enabling non-blocking database communication for SQLite.
- **Why it is needed**: Standard database drivers (like Python's built-in `sqlite3`) are synchronous and block execution during disk read/write queries.
- **How it works**: `aiosqlite` wraps SQLite operations in asynchronous interfaces, which SQLAlchemy's async extension (`sqlalchemy.ext.asyncio`) uses via the `sqlite+aiosqlite://` connection string protocol.
- **Important details**: For production databases like PostgreSQL, an equivalent async driver such as `asyncpg` or `psycopg` (v3 async) is used.
- **Examples**: Connection string: `"sqlite+aiosqlite:///./blog.db"`.

### `AsyncSession` & `async_sessionmaker`

- **What it is**: The asynchronous counterparts to SQLAlchemy's synchronous `Session` and `sessionmaker`.
- **Why it is needed**: Manages database transactions, object states, and queries asynchronously without blocking thread execution.
- **How it works**: `async_sessionmaker` instantiates `AsyncSession` instances. Operations that interact with the database (`execute`, `commit`, `refresh`, `delete`) return coroutines that must be awaited.
- **Important details**: Must be initialized with `expire_on_commit=False` in async mode to prevent implicit lazy-loading crashes after transaction commits.
- **Examples**: `AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)`.

### Application Lifespan Context Manager (`lifespan`)

- **What it is**: An asynchronous context manager registered on the `FastAPI` app instance that manages startup and shutdown logic.
- **Why it is needed**: Replaces deprecated `@app.on_event("startup")` and `@app.on_event("shutdown")` decorators with a clean, unified lifecycle handler.
- **How it works**: Code executing _before_ `yield` runs during server startup (e.g., creating database tables); code executing _after_ `yield` runs during server shutdown (e.g., closing database connection pools).
- **Important details**: Uses `engine.begin()` and `conn.run_sync(Base.metadata.create_all)` to run synchronous table creation logic safely inside an async startup context.
- **Examples**: `@asynccontextmanager async def lifespan(app: FastAPI): ...`.

### Lazy Loading Failure (`greenlet` Error) vs. Eager Loading (`selectinload`)

- **What it is**:
  - **Lazy Loading**: Synchronous SQLAlchemy automatically fetches related database objects on demand when accessed (e.g., accessing `post.author` triggers an implicit SQL query).
  - **Eager Loading (`selectinload`)**: Instructs SQLAlchemy to query and load specified relationships immediately alongside the primary query.
- **Why it is needed**: Lazy loading is fundamentally disabled in async SQLAlchemy because triggering an implicit synchronous database fetch inside an async context throws a missing `greenlet` execution error.
- **How it works**: `selectinload(models.Post.author)` generates an explicit combined or secondary SQL query during the initial `await db.execute(...)` call, populating the relationship attribute before rendering templates or returning JSON responses.
- **Important details**: Any route or template that accesses a child object property (e.g., `post.author.username`) MUST explicitly eager load that relationship using `options(selectinload(...))` or `db.refresh(..., attribute_names=[...])`.
- **Examples**: `stmt = select(models.Post).options(selectinload(models.Post.author))`.

---

## 3. Step-by-Step Tutorial

### Step 1: Installing Asynchronous Dependencies

- **What he does**: Installs `aiosqlite` and `greenlet` using the package manager (`uv add aiosqlite greenlet` or `pip install aiosqlite greenlet`).
- **Why he does it**: `aiosqlite` provides the asynchronous database driver for SQLite, while `greenlet` provides the underlying C-extension coroutine execution context required by SQLAlchemy's async engine.
- **Relevant code**:
  ```bash
  uv add aiosqlite greenlet
  ```
- **How the code works**: Adds the async SQLite driver and greenlet concurrency library into the virtual environment.
- **The result**: Package dependencies for asynchronous database interactions become available.

### Step 2: Converting `database.py` to Asynchronous Architecture

- **What he does**: Refactors `database.py` to use `create_async_engine`, `async_sessionmaker`, `AsyncSession`, updated connection URLs (`sqlite+aiosqlite://`), and an asynchronous `get_db()` generator.
- **Why he does it**: Establishes non-blocking database connections and session management.
- **Relevant code**:

  ```python
  from collections.abc import AsyncGenerator
  from sqlalchemy.ext.asyncio import (
      AsyncSession,
      async_sessionmaker,
      create_async_engine,
  )
  from sqlalchemy.orm import DeclarativeBase

  SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./blog.db"

  engine = create_async_engine(SQLALCHEMY_DATABASE_URL)

  AsyncSessionLocal = async_sessionmaker(
      bind=engine,
      class_=AsyncSession,
      expire_on_commit=False,
  )

  class Base(DeclarativeBase):
      pass

  async def get_db() -> AsyncGenerator[AsyncSession, None]:
      async with AsyncSessionLocal() as session:
          yield session
  ```

- **How the code works**:
  - `sqlite+aiosqlite://` instructs SQLAlchemy to use the `aiosqlite` async driver.
  - `create_async_engine` initializes an asynchronous database engine.
  - `async_sessionmaker` configures the session factory to produce `AsyncSession` instances.
  - `expire_on_commit=False` prevents objects from expiring after commit, avoiding implicit lazy-loading queries in async mode.
  - `async def get_db()` uses `async with` to yield an `AsyncSession` per HTTP request and guarantees session closure upon completion.
- **The result**: `database.py` exports an asynchronous database engine and dependency provider.

### Step 3: Updating Imports in `main.py`

- **What he does**: Removes synchronous database imports and imports `asynccontextmanager` from `contextlib`, `AsyncSession` from `sqlalchemy.ext.asyncio`, `select` and `selectinload` from `sqlalchemy.orm`, and FastAPI's default exception handlers (`HTTPExceptionHandler`, `RequestValidationExceptionHandler`).
- **Why he does it**: Prepares `main.py` with the asynchronous classes and helper functions needed for lifespan events, route handlers, and exception handling.
- **Relevant code**:

  ```python
  from contextlib import asynccontextmanager
  from typing import Annotated

  from fastapi import Depends, FastAPI, HTTPException, Request, status
  from fastapi.exception_handlers import (
      http_exception_handler as default_http_exception_handler,
      request_validation_exception_handler as default_validation_exception_handler,
  )
  from fastapi.exceptions import RequestValidationError
  from fastapi.staticfiles import StaticFiles
  from fastapi.templating import Jinja2Templates
  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession
  from sqlalchemy.orm import selectinload
  from starlet.exceptions import HTTPException as StarletHTTPException

  from database import Base, engine, get_db
  import models
  import schemas
  ```

- **How the code works**: Brings in async equivalents for sessions, queries, eager loading, and standard exception handlers.
- **The result**: `main.py` imports align with the async architecture.

### Step 4: Replacing `Base.metadata.create_all()` with a Lifespan Context Manager

- **What he does**: Deletes the synchronous `Base.metadata.create_all(bind=engine)` call and defines an `@asynccontextmanager` `lifespan` function passed into `FastAPI(lifespan=lifespan)`.
- **Why he does it**: `Base.metadata.create_all()` is a blocking synchronous method that cannot be called directly on an async engine. Lifespan context managers safely execute synchronous table creation via an async connection during startup and clean up the engine during shutdown.
- **Relevant code**:

  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      # Startup: Create database tables asynchronously
      async with engine.begin() as conn:
          await conn.run_sync(Base.metadata.create_all)
      yield
      # Shutdown: Clean up database engine resources
      await engine.dispose()

  app = FastAPI(lifespan=lifespan)
  ```

- **How the code works**:
  - `engine.begin()` opens an async connection.
  - `conn.run_sync(...)` runs the synchronous `create_all` method inside a special synchronous runner context.
  - `yield` yields control to run the FastAPI web application.
  - `engine.dispose()` closes database connection pools cleanly when the application stops.
- **The result**: Tables are created safely on server startup without blocking the async event loop.

### Step 5: Converting HTML Web Routes to `async def` and Eager Loading

- **What he does**: Refactors `/`, `/post/{post_id}`, and `/user/{user_id}` routes to use `async def`, `AsyncSession`, `await db.execute(...)`, and `options(selectinload(models.Post.author))`.
- **Why he does it**: Converts handlers to non-blocking async functions while preventing lazy-loading `greenlet` errors when Jinja2 templates access `post.author.username` or `post.author.image_path`.
- **Relevant code**:
  ```python
  @app.get("/", include_in_schema=False, name="home")
  @app.get("/posts", include_in_schema=False, name="posts")
  async def home(
      request: Request,
      db: Annotated[AsyncSession, Depends(get_db)]
  ):
      stmt = select(models.Post).options(selectinload(models.Post.author))
      result = await db.execute(stmt)
      posts = result.scalars().all()
      return templates.TemplateResponse(
          request=request,
          name="home.html",
          context={"posts": posts, "title": "Home"}
      )
  ```
- **How the code works**:
  - `async def` runs the route directly on the main event loop.
  - `options(selectinload(models.Post.author))` instructs SQLAlchemy to query and attach the `User` author record eagerly.
  - `await db.execute(stmt)` asynchronously fetches query results without blocking the thread.
- **The result**: Home page renders HTML templates with full author details populated asynchronously.

### Step 6: Converting REST API CRUD Routes to Async

- **What he does**: Updates all user and post REST API routes (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`) to use `async def`, `AsyncSession`, `await db.execute(...)`, `await db.commit()`, `await db.refresh()`, and `await db.delete()`. Note that `db.add()` does **not** take an `await`.
- **Why he does it**: Transforms all database I/O calls across REST endpoints into non-blocking operations.
- **Relevant code**:

  ```python
  # Async Post Creation with Relational Refresh
  @app.post("/api/posts", response_model=schemas.PostResponse, status_code=status.HTTP_201_CREATED)
  async def create_post(
      post: schemas.PostCreate,
      db: Annotated[AsyncSession, Depends(get_db)]
  ):
      user_stmt = select(models.User).where(models.User.id == post.user_id)
      user_result = await db.execute(user_stmt)
      user = user_result.scalars().first()
      if not user:
          raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

      new_post = models.Post(title=post.title, content=post.content, user_id=post.user_id)
      db.add(new_post)  # Synchronous in-memory operation (no await)
      await db.commit() # Async I/O (requires await)
      await db.refresh(new_post, attribute_names=["author"]) # Eager load relationship on refresh
      return new_post
  ```

- **How the code works**:
  - `db.add()` pushes the new object to the session's in-memory pending state (requires no `await`).
  - `await db.commit()` writes the transaction to disk asynchronously.
  - `await db.refresh(new_post, attribute_names=["author"])` reloads the post instance while eagerly populating the `author` relationship needed by `PostResponse`.
- **The result**: API endpoints execute database read/write/delete operations asynchronously.

### Step 7: Refactoring Exception Handlers to Async Default Handlers

- **What he does**: Converts `http_exception_handler` and `validation_exception_handler` to `async def` and delegates API error responses to `await default_http_exception_handler(...)` and `await default_validation_exception_handler(...)`.
- **Why he does it**: Simplifies error handling code, matches FastAPI's standard internal exception formatting, and maintains non-blocking execution.
- **Relevant code**:

  ```python
  @app.exception_handler(StarletHTTPException)
  async def custom_http_exception_handler(request: Request, exc: StarletHTTPException):
      if request.url.path.startswith("/api"):
          return await default_http_exception_handler(request, exc)

      message = exc.detail if exc.detail else "An error occurred. Please check your request and try again."
      return templates.TemplateResponse(
          request=request,
          name="error.html",
          context={"status_code": exc.status_code, "message": message, "title": exc.status_code},
          status_code=exc.status_code
      )

  @app.exception_handler(RequestValidationError)
  async def custom_validation_exception_handler(request: Request, exc: RequestValidationError):
      if request.url.path.startswith("/api"):
          return await default_validation_exception_handler(request, exc)

      return templates.TemplateResponse(
          request=request,
          name="error.html",
          context={
              "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
              "message": "Invalid Request",
              "title": status.HTTP_422_UNPROCESSABLE_CONTENT
          },
          status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
      )
  ```

- **How the code works**: Intercepts errors on `/api/...` routes and delegates response generation directly to FastAPI's built-in async handlers, while continuing to serve `error.html` for browser template routes.
- **The result**: Standardized, non-blocking error handling across web and API paths.

### Step 8: Launching and Testing the Asynchronous Application

- **What he does**: Starts the development server using `fastapi dev main.py` or `uv run fastapi dev main.py`. Fixes any missing dependency errors (such as `greenlet`), interacts with `/docs`, creates new posts, and reloads HTML pages.
- **Why he does it**: Confirms that database table creation, eager relationship loading, API routes, and HTML rendering function without runtime errors.
- **The result**: The application runs asynchronously with full feature parity to the synchronous version.

---

## 4. Code Examples

### Full `database.py` (Async Implementation)

```python
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# Connection string specifying the aiosqlite async driver
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./blog.db"

# Asynchronous database engine
engine = create_async_engine(SQLALCHEMY_DATABASE_URL)

# Asynchronous session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Essential for async SQLAlchemy
)

class Base(DeclarativeBase):
    pass

# Asynchronous session provider generator
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
```

### Complete `main.py` (Async Architecture)

```python
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import (
    http_exception_handler as default_http_exception_handler,
    request_validation_exception_handler as default_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlet.exceptions import HTTPException as StarletHTTPException

from database import Base, engine, get_db
import models
import schemas

# Modern Application Lifespan Handler for Startup/Shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables asynchronously
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown: Dispose engine
    await engine.dispose()

app = FastAPI(lifespan=lifespan)

# Static and Media Mounts
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

templates = Jinja2Templates(directory="templates")

# --- HTML WEB ROUTES ---

@app.get("/", include_in_schema=False, name="home")
@app.get("/posts", include_in_schema=False, name="posts")
async def home(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    stmt = select(models.Post).options(selectinload(models.Post.author))
    result = await db.execute(stmt)
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request=request, name="home.html", context={"posts": posts, "title": "Home"}
    )

@app.get("/post/{post_id}", include_in_schema=False, name="post_page")
async def post_page(request: Request, post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    stmt = select(models.Post).where(models.Post.id == post_id).options(selectinload(models.Post.author))
    result = await db.execute(stmt)
    post = result.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    title = post.title[:50]
    return templates.TemplateResponse(
        request=request, name="post.html", context={"post": post, "title": title}
    )

# --- REST API ROUTES ---

@app.get("/api/posts", response_model=list[schemas.PostResponse])
async def get_posts(db: Annotated[AsyncSession, Depends(get_db)]):
    stmt = select(models.Post).options(selectinload(models.Post.author))
    result = await db.execute(stmt)
    return result.scalars().all()

@app.post("/api/posts", response_model=schemas.PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(post: schemas.PostCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    user_stmt = select(models.User).where(models.User.id == post.user_id)
    user_result = await db.execute(user_stmt)
    if not user_result.scalars().first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

    new_post = models.Post(title=post.title, content=post.content, user_id=post.user_id)
    db.add(new_post)
    await db.commit()
    await db.refresh(new_post, attribute_names=["author"])
    return new_post

@app.patch("/api/posts/{post_id}", response_model=schemas.PostResponse)
async def update_post_partial(
    post_id: int, post_data: schemas.PostUpdate, db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = select(models.Post).where(models.Post.id == post_id)
    result = await db.execute(stmt)
    post = result.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    update_data = post_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(post, field, value)

    await db.commit()
    await db.refresh(post, attribute_names=["author"])
    return post

@app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    stmt = select(models.Post).where(models.Post.id == post_id)
    result = await db.execute(stmt)
    post = result.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    await db.delete(post)
    await db.commit()

# --- ASYNC EXCEPTION HANDLERS ---

@app.exception_handler(StarletHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletHTTPException):
    if request.url.path.startswith("/api"):
        return await default_http_exception_handler(request, exc)

    message = exc.detail if exc.detail else "An error occurred."
    return templates.TemplateResponse(
        request=request, name="error.html",
        context={"status_code": exc.status_code, "message": message, "title": exc.status_code},
        status_code=exc.status_code
    )

@app.exception_handler(RequestValidationError)
async def custom_validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/api"):
        return await default_validation_exception_handler(request, exc)

    return templates.TemplateResponse(
        request=request, name="error.html",
        context={"status_code": status.HTTP_422_UNPROCESSABLE_CONTENT, "message": "Invalid Request", "title": status.HTTP_422_UNPROCESSABLE_CONTENT},
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
    )
```

---

## 5. FastAPI & Python Knowledge

- **`async def` & `await` Keywords**:
  - `async def` declares a function as a coroutine that can run concurrently on an event loop.
  - `await` pauses execution of the coroutine until the awaited task completes, yielding thread execution back to the event loop to handle other tasks.
- **`AsyncSession` vs. `Session`**: `AsyncSession` is SQLAlchemy's non-blocking session class where database I/O methods (`execute`, `commit`, `refresh`, `delete`) return awaitable coroutines.
- **`selectinload()` Strategy**: An ORM relationship loading strategy imported from `sqlalchemy.orm` that executes an immediate secondary `SELECT ... WHERE id IN (...)` query to pre-populate relationships eagerly during initial execution.
- **`attribute_names` Parameter in `db.refresh()`**: Allows passing specific relationship attribute names (e.g., `await db.refresh(post, attribute_names=["author"])`) to reload specific relationship objects after an insert or update operation.
- **`@asynccontextmanager` Decorator**: Imported from `contextlib`; turns an async generator function into an asynchronous context manager usable with `async with` blocks.
- **FastAPI Application `lifespan`**: Passed into `FastAPI(lifespan=...)` to manage startup and shutdown routines asynchronously, replacing legacy startup/shutdown event decorators.
- **`conn.run_sync()`**: A helper method on `AsyncConnection` that executes synchronous engine methods (like `Base.metadata.create_all`) inside an async context.

---

## 6. Tips & Important Details

- **When `db.add()` Needs No `await`**: `db.add(obj)` merely places an instance into the session's in-memory tracking dictionary. Because it involves no disk or network I/O, it remains a synchronous operation and must **not** be awaited.
- **When `db.delete()` Needs `await`**: Unlike `add()`, `db.delete(obj)` in async SQLAlchemy performs session state checks that interact with async relationship handlers, requiring `await db.delete(obj)`.
- **Setting `expire_on_commit=False`**: Crucial when constructing `async_sessionmaker`. Leaving it `True` causes SQLAlchemy to expire all instance attributes upon commit. Any subsequent access to an attribute would trigger an implicit lazy-loading query, throwing a `greenlet` crash in async mode.
- **Mixing Sync and Async Routes**: FastAPI allows mixing synchronous (`def`) and asynchronous (`async def`) routes in the same project. Sync routes run safely in background threadpools, while async routes run directly on the main event loop.
- **Avoiding Blocking Libraries in `async def` Routes**: Never call blocking synchronous libraries (such as `requests`, `time.sleep()`, or standard `sqlite3`) inside an `async def` function. Use non-blocking async equivalents like `httpx.AsyncClient` or `asyncio.sleep()`.

---

## 7. Errors & Pitfalls

- **`Missing Greenlet` / `greenlet_spawn` Error**:
  - **Cause**: Accessing an un-loaded ORM relationship attribute (e.g., `post.author.username`) in an async route or Jinja2 template when lazy loading is implicitly triggered.
  - **Fix**: Ensure `greenlet` is installed (`uv add greenlet`) and explicitly eager load all accessed relationships using `selectinload(models.Post.author)` or `attribute_names=["author"]` during `db.refresh()`.
- **Blocking the Main Event Loop**:
  - **Cause**: Executing a synchronous, long-running, or blocking I/O operation (like `requests.get()`) inside an `async def` route.
  - **Fix**: Use an asynchronous library (like `httpx`), or declare the route using standard synchronous `def` so FastAPI executes it in a background threadpool.
- **Missing `await` on Database Operations**:
  - **Cause**: Omitting `await` on `db.execute()`, `db.commit()`, `db.refresh()`, or `db.delete()`.
  - **Fix**: In async mode, all session I/O calls return coroutines that must be awaited. Un-awaited calls return pending coroutine objects rather than executing database statements.
- **Over-Optimizing with Async for Single Requests**:
  - **Cause**: Expecting a single sequential user request to execute twice as fast after converting to async.
  - **Fix**: Realize that async improves throughput under high concurrent load (many simultaneous users), not raw latency for a single isolated request.

---

## 8. Best Practices & Trade-offs

- **`async def` vs. Standard `def` Decision Matrix**:
  - **Use `async def`**: When performing non-blocking I/O using async drivers (`aiosqlite`, `asyncpg`), calling external web APIs with `httpx`, or handling thousands of concurrent connections.
  - **Use Standard `def`**: For simple fast endpoints, CPU-bound computations (image processing, data analysis), or when relying on legacy synchronous libraries (`requests`, `sqlite3`).
- **Eager Loading (`selectinload`) vs. Lazy Loading**:
  - **Eager Loading**: Mandated in async SQLAlchemy. Fetches related data upfront in a controlled query, preventing unexpected database calls during template rendering.
  - **Lazy Loading**: Convenient in synchronous code, but forbidden in async code due to non-blocking runtime constraints.
- **Delegating to Default Async Exception Handlers**: Using FastAPI's `default_http_exception_handler` inside custom exception handlers reduces custom boilerplate code while maintaining consistent API error formatting.

---

## 9. Resources

- **GitHub Source Code Repository**: Companion code repository for Part 7 linked in the video description.
- **Corey Schafer's Async IO Tutorial Video**: Linked in the video description for a deep dive with visual animations on Python's `asyncio` event loop.
- **SQLAlchemy Async Documentation**: Official reference guide for `sqlalchemy.ext.asyncio`, `AsyncSession`, and `selectinload`.
- **FastAPI Official Async Documentation**: Guide explaining how FastAPI manages threadpools for `def` routes and event loops for `async def` routes.

---

## 10. Key Takeaways

1. Asynchronous code allows a web server to process other tasks while waiting for I/O operations to complete.
2. Async optimizes I/O-bound tasks (database queries, network calls) but does not speed up CPU-bound work.
3. Standard `def` routes run inside FastAPI's background threadpool; `async def` routes run directly on the main event loop.
4. Never execute blocking synchronous code inside `async def` routes.
5. SQLite requires the `aiosqlite` async driver (`sqlite+aiosqlite://`).
6. `create_async_engine` and `async_sessionmaker` establish asynchronous database connections.
7. `expire_on_commit=False` must be set on `async_sessionmaker` to prevent post-commit attribute expiration.
8. Application lifespan handlers (`@asynccontextmanager`) replace deprecated startup/shutdown event decorators.
9. Lazy loading is disabled in async SQLAlchemy; accessing un-loaded relationships throws a `greenlet` error.
10. `options(selectinload(Model.relationship))` eager loads relationship data upfront.
11. `db.add()` is a synchronous in-memory operation that does NOT take an `await`.
12. `db.commit()`, `db.refresh()`, and `db.delete()` interact with the database and MUST be awaited.
13. `await db.refresh(obj, attribute_names=["relation"])` reloads specific relationships after inserts/updates.
14. `httpx` should be used instead of `requests` for making asynchronous external API calls.
15. FastAPI seamlessly supports mixing `def` and `async def` routes within the same application.

---

## 11. Quick Reference

### Dependency Installation

```bash
# Add async driver and concurrency library
uv add aiosqlite greenlet
```

### Async Database Config (`database.py`)

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./blog.db"
engine = create_async_engine(SQLALCHEMY_DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

### Application Lifespan Pattern

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(lifespan=lifespan)
```

### Async Route & Eager Loading Pattern

```python
@app.get("/api/posts")
async def get_posts(db: Annotated[AsyncSession, Depends(get_db)]):
    stmt = select(models.Post).options(selectinload(models.Post.author))
    result = await db.execute(stmt)
    return result.scalars().all()
```

---

## 12. Mental Model

- **Synchronous vs. Asynchronous Execution Architecture**:
  1. **Synchronous Execution Threadpool (`def`)**:
     - Client Request \\(\rightarrow\\) Main Event Loop \\(\rightarrow\\) Dispatched to **Worker Threadpool Thread**.
     - Thread blocks while waiting for database disk read/write.
     - Event loop stays free to accept new incoming HTTP connections on other threads.
  2. **Asynchronous Execution Event Loop (`async def`)**:
     - Client Request \\(\rightarrow\\) Main Event Loop \\(\rightarrow\\) Handler starts on **Main Event Loop**.
     - Reaches `await db.execute(...)` \\(\rightarrow\\) Handler **yields control** back to event loop.
     - Event loop processes hundreds of concurrent requests while the database query resolves in the background.
     - Query completes \\(\rightarrow\\) Event loop resumes handler execution and returns response.
  3. **Data Fetching & Eager Loading Gate**:
     - In async mode, relationship attributes (`post.author`) CANNOT trigger on-demand SQL queries during rendering.
     - Queries must explicitly declare `.options(selectinload(models.Post.author))` upfront so all required relational data is attached to object memory before `await db.execute()` completes.
