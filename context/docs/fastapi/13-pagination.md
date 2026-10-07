# Python FastAPI Tutorial (Part 13): Pagination - Loading More Data with Query Parameters

## 1. Overview

- **What this lesson teaches**: This lesson demonstrates how to implement offset-based pagination in a FastAPI application to slice large dataset responses into manageable batches. It covers defining query parameters (`skip` and `limit`) with validation constraints, creating a structured contract schema (`PaginatedPostResponse`) containing pagination metadata, performing database-level pagination using SQLAlchemy's `func.count()`, `.offset()`, and `.limit()`, centralizing page settings in `config.py`, building a hybrid frontend rendering model (initial server-side Jinja2 render + dynamic client-side JavaScript "Load More" button), sanitizing dynamic content against Cross-Site Scripting (XSS) attacks with `escapeHtml`, and applying pagination to user-specific post feeds.
- **Learning objectives**:
  - Understand the architectural necessity of pagination for database performance, lower memory overhead, and user experience.
  - Define a Pydantic schema for paginated responses (`PaginatedPostResponse`) encapsulating data arrays and metadata (`total`, `skip`, `limit`, `has_more`).
  - Enforce query parameter validation for `skip` (offset) and `limit` (batch size) using FastAPI's `Annotated` and `Query`.
  - Execute a dual SQLAlchemy database query pattern: a count query (`select(func.count()).select_from(...)`) for total items and a paginated data query using `.offset(skip).limit(limit)`.
  - Dynamically evaluate `has_more` on the backend (`(skip + len(posts)) < total`) to streamline client UI logic.
  - Build a hybrid frontend approach that server-renders the initial batch of posts for SEO and fast load times, while using asynchronous JavaScript `fetch()` calls to load subsequent batches.
  - Prevent client-side XSS vulnerabilities using HTML escaping (`escapeHtml`) when dynamically injecting API responses into the DOM.
  - Apply pagination mechanics consistently to resource-filtered endpoints (such as user-specific post feeds).
- **Why the topic matters**: Unpaginated list endpoints that query and return every database record at once create massive performance bottlenecks as database tables grow. Loading thousands of records simultaneously consumes excessive server memory, degrades network throughput, and freezes web clients. Offset-based pagination provides an industry-standard pattern driven by the backend API to guarantee predictable database performance and optimal client bandwidth usage.

---

## 2. Concepts

### Offset-Based Pagination (`skip` & `limit`)

- **What it is**: A query parameter pattern where `skip` defines the starting database row offset and `limit` sets the maximum batch size returned.
- **Why it is needed**: Gives API clients the flexibility to request any arbitrary window of data records across a resource collection.
- **How it works**: In SQL and SQLAlchemy, `.offset(skip)` instructs the database engine to skip `skip` rows before collecting results, while `.limit(limit)` caps the result set to at most `limit` rows.
- **Important details**: Offset-based pagination requires an explicit sort order (`.order_by()`). Without explicit ordering, database engines make no guarantee about row return sequence, leading to duplicate or skipped records across pagination requests.
- **Examples**: Requesting `GET /api/posts?skip=20&limit=10` fetches database records 21 through 30.

### Paginated Contract Schema (`PaginatedPostResponse`)

- **What it is**: A wrapper Pydantic schema returning both the resource data array and structural metadata.
- **Why it is needed**: Frontend clients require contextual metadata alongside raw resource records to determine total counts, current offsets, and whether additional pages remain to be loaded.
- **How it works**: Defined as a Pydantic model containing:
  - `posts`: List of item response models (`list[PostResponse]`).
  - `total`: Integer count of all matching records in the database.
  - `skip`: Integer representing the current query offset.
  - `limit`: Integer representing the requested page size.
  - `has_more`: Boolean flag indicating if additional records exist past the current batch.
- **Important details**: Calculating `has_more` on the backend simplifies frontend implementation by removing calculations from web, iOS, or Android clients.

### Dual Query Pattern (Count Query + Data Query)

- **What it is**: Executing two targeted database queries per paginated request: an aggregate count query and a windowed data query.
- **Why it is needed**: Calculating `total` and `has_more` requires knowing the total number of matching records in the database, which cannot be inferred solely from a windowed slice.
- **How it works**:
  1. **Count Query**: `select(func.count()).select_from(models.Post)` returns the total row count efficiently without loading ORM objects into memory.
  2. **Data Query**: `select(models.Post).order_by(...).offset(skip).limit(limit)` retrieves the specific page slice with pre-loaded relationships (`selectinload`).

### Hybrid Rendering Strategy

- **What it is**: Combining server-side Jinja2 template rendering for the initial page load with client-side JavaScript API requests for subsequent data pages.
- **Why it is needed**: Delivers fast initial page load speeds and search engine optimization (SEO) benefits, while providing smooth dynamic loading ("Load More Posts") without full page reloads.
- **How it works**: The initial GET template route loads the first page batch (e.g. 10 posts) using `settings.posts_per_page` and passes `has_more` into the Jinja2 context. Client-side JavaScript initializes `currentOffset = limit` and issues asynchronous `fetch()` calls to `/api/posts?skip=${currentOffset}&limit=${limit}` when the user clicks "Load More".

### Client-Side XSS Escaping (`escapeHtml`)

- **What it is**: Converting raw string values into safe text nodes before injecting them into the DOM using JavaScript.
- **Why it is needed**: Jinja2 automatically escapes unsafe HTML characters during server-side template rendering. However, when client-side JavaScript constructs HTML strings dynamically from JSON API responses, inserting unescaped user content via template literals creates Cross-Site Scripting (XSS) vulnerabilities.
- **How it works**: Assigns untrusted text strings to an element's `textContent` property (which treats all input as plain text) and reads back the sanitized `innerHTML` representation.
- **Examples**: `function escapeHtml(str) { const div = document.createElement('div'); div.textContent = str; return div.innerHTML; }`.

---

## 3. Step-by-Step Tutorial

### Step 1: Populating Sample Data (`populate_db.py`)

- **What he does**: Executes `uv run python populate_db.py` to seed the SQLite database with test users, profile pictures, and 44 realistic sample posts distributed across recent months.
- **Why he does it**: Testing pagination requires a dataset larger than a single page batch (e.g. 44 posts to test batch sizes of 10).
- **Relevant command**:
  ```bash
  uv run python populate_db.py
  ```
- **How the code works**: The utility script issues HTTP requests to the application's registration, login, profile picture upload, and post creation endpoints, updating `date_posted` column timestamps across past months.
- **Result**: The database is populated with 6 users and 44 sample posts.

### Step 2: Defining `PaginatedPostResponse` Schema (`schemas.py`)

- **What he does**: Appends `PaginatedPostResponse` to `schemas.py`.
- **Why he does it**: Establishes the response structure for paginated API routes.
- **Relevant code**:
  ```python
  class PaginatedPostResponse(BaseModel):
      posts: list[PostResponse]
      total: int
      skip: int
      limit: int
      has_more: bool
  ```
- **How the code works**: Combines a typed array of `PostResponse` items with metadata fields (`total`, `skip`, `limit`, `has_more`).
- **Result**: The paginated response contract is defined.

### Step 3: Refactoring API Endpoint `GET /api/posts` (`routers/posts.py`)

- **What he does**: Updates `GET /api/posts` to accept `skip` and `limit` query parameters with validation, performs aggregate count and offset/limit database queries, computes `has_more`, and serializes the response models.
- **Why he does it**: Replaces the unpaginated list endpoint with a paginated API route.
- **Relevant code**:

  ```python
  from typing import Annotated
  from fastapi import APIRouter, Depends, Query
  from sqlalchemy import func, select
  from sqlalchemy.ext.asyncio import AsyncSession
  from sqlalchemy.orm import selectinload

  from database import get_db
  import models
  import schemas

  router = APIRouter()

  @router.get("", response_model=schemas.PaginatedPostResponse)
  async def get_posts(
      db: Annotated[AsyncSession, Depends(get_db)],
      skip: Annotated[int, Query(ge=0)] = 0,
      limit: Annotated[int, Query(ge=1, le=100)] = 10,
  ):
      # 1. Total count query
      count_stmt = select(func.count()).select_from(models.Post)
      total = (await db.execute(count_stmt)).scalar() or 0

      # 2. Windowed data query
      stmt = (
          select(models.Post)
          .order_by(models.Post.date_posted.desc())
          .options(selectinload(models.Post.author))
          .offset(skip)
          .limit(limit)
      )
      result = await db.execute(stmt)
      posts = result.scalars().all()

      # 3. Calculate has_more boolean
      has_more = (skip + len(posts)) < total

      # 4. Construct response dictionary with explicit model conversion
      return schemas.PaginatedPostResponse(
          posts=[schemas.PostResponse.model_validate(post) for post in posts],
          total=total,
          skip=skip,
          limit=limit,
          has_more=has_more,
      )
  ```

- **How the code works**:
  - `skip: Annotated[int, Query(ge=0)] = 0` enforces non-negative offsets, defaulting to `0`.
  - `limit: Annotated[int, Query(ge=1, le=100)] = 10` enforces page sizes between 1 and 100, defaulting to `10`.
  - `select(func.count()).select_from(models.Post)` calculates the total record count.
  - `.offset(skip).limit(limit)` applies windowing to the ordered query.
  - `(skip + len(posts)) < total` calculates whether further records exist.
  - `[schemas.PostResponse.model_validate(post) for post in posts]` converts ORM objects into Pydantic models so nested relationships (`author`) serialize properly when returning custom response instances.
- **Result**: `GET /api/posts` returns paginated JSON payloads with metadata.

### Step 4: Centralizing Page Size Settings (`config.py`)

- **What he does**: Adds `posts_per_page: int = 10` to the `Settings` class in `config.py`.
- **Why he does it**: Avoids hardcoding page size integers across multiple application template routes.
- **Relevant code**:
  ```python
  class Settings(BaseSettings):
      ...
      posts_per_page: int = 10
  ```
- **Result**: `settings.posts_per_page` manages default pagination page sizes centrally.

### Step 5: Updating Homepage Template Route (`main.py`)

- **What he does**: Refactors `GET /` and `GET /posts` template routes in `main.py` to count total posts, query the initial batch using `settings.posts_per_page`, calculate `has_more`, and pass `has_more` into the Jinja2 context.
- **Why he does it**: Renders only the first page batch on initial HTML page load instead of fetching all database posts at once.
- **Relevant code**:

  ```python
  @app.get("/", include_in_schema=False, name="home")
  @app.get("/posts", include_in_schema=False, name="posts")
  async def home(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
      count_stmt = select(func.count()).select_from(models.Post)
      total = (await db.execute(count_stmt)).scalar() or 0

      stmt = (
          select(models.Post)
          .order_by(models.Post.date_posted.desc())
          .options(selectinload(models.Post.author))
          .limit(settings.posts_per_page)
      )
      result = await db.execute(stmt)
      posts = result.scalars().all()

      has_more = len(posts) < total

      return templates.TemplateResponse(
          request=request,
          name="home.html",
          context={
              "posts": posts,
              "title": "Home",
              "has_more": has_more,
          },
      )
  ```

- **Result**: Homepage initial rendering fetches only the first 10 posts and passes `has_more` state to the template.

### Step 6: Adding Client JavaScript Helpers (`static/js/utils.js`)

- **What he does**: Exports `escapeHtml()` and `formatDate()` from `static/js/utils.js`.
- **Why he does it**: `escapeHtml()` prevents XSS vulnerabilities when generating HTML strings in JS, and `formatDate()` converts ISO date strings into `Month DD, YYYY` format to match Jinja2 template formatting.
- **Relevant code**:

  ```javascript
  export function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  export function formatDate(dateString) {
    const options = { year: "numeric", month: "long", day: "numeric" };
    return new Date(dateString).toLocaleDateString("en-US", options);
  }
  ```

- **Result**: Formatting and sanitization utilities are exported for client script import.

### Step 7: Updating `templates/home.html` with Dynamic "Load More" JS Logic

- **What he does**: Wraps Jinja2 posts in `<div id="postContainer">`, adds a conditional "Load More Posts" button (`{% if has_more %}`), and appends a `<script type="module">` block to fetch and append subsequent pages.
- **Why he does it**: Connects UI interactions to the paginated API endpoint.
- **Relevant code**:

  ```html
  <div id="postContainer">
    {% for post in posts %}
    <!-- Original article markup preserved -->
    {% endfor %}
  </div>

  {% if has_more %}
  <div class="text-center my-4" id="loadMoreContainer">
    <button id="loadMoreBtn" class="btn btn-outline-primary">
      Load More Posts
    </button>
  </div>
  {% endif %} {% block scripts %}
  <script type="module">
    import { escapeHtml, formatDate } from "{{ url_for('static', path='js/utils.js') }}";

    const postContainer = document.getElementById('postContainer');
    const loadMoreBtn = document.getElementById('loadMoreBtn');
    const loadMoreContainer = document.getElementById('loadMoreContainer');

    const limit = 10;
    let currentOffset = limit; // Initial batch (0 to limit) already server-rendered
    let hasMore = {{ 'true' if has_more else 'false' }};

    function createPostHTML(post) {
        return `
            <article class="media content-section">
                <img class="rounded-circle article-img" src="${post.author.image_path}">
                <div class="media-body">
                    <div class="article-metadata">
                        <a class="mr-2" href="/user/${post.author.id}">${escapeHtml(post.author.username)}</a>
                        <small class="text-muted">${formatDate(post.date_posted)}</small>
                    </div>
                    <h2><a class="article-title" href="/post/${post.id}">${escapeHtml(post.title)}</a></h2>
                    <p class="article-content">${escapeHtml(post.content)}</p>
                </div>
            </article>
        `;
    }

    async function loadMorePosts() {
        if (!loadMoreBtn) return;
        loadMoreBtn.disabled = true;
        loadMoreBtn.textContent = 'Loading...';

        try {
            const response = await fetch(`/api/posts?skip=${currentOffset}&limit=${limit}`);
            if (response.ok) {
                const data = await response.json();

                data.posts.forEach(post => {
                    postContainer.insertAdjacentHTML('beforeend', createPostHTML(post));
                });

                currentOffset += data.posts.length;
                hasMore = data.has_more;

                if (!hasMore && loadMoreContainer) {
                    loadMoreContainer.remove();
                } else {
                    loadMoreBtn.disabled = false;
                    loadMoreBtn.textContent = 'Load More Posts';
                }
            } else {
                loadMoreBtn.disabled = false;
                loadMoreBtn.textContent = 'Error. Click to retry';
            }
        } catch (error) {
            loadMoreBtn.disabled = false;
            loadMoreBtn.textContent = 'Error. Click to retry';
        }
    }

    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', loadMorePosts);
    }
  </script>
  {% endblock scripts %}
  ```

- **How the code works**:
  - Initial offset starts at `limit` (10) because page 1 is server-rendered.
  - Clicking "Load More Posts" issues a `fetch()` request for the next batch using `skip=${currentOffset}&limit=${limit}`.
  - `insertAdjacentHTML('beforeend', ...)` appends newly constructed elements to `#postContainer`.
  - Increments `currentOffset` by `data.posts.length` and removes `#loadMoreContainer` when `data.has_more` becomes `false`.
- **Result**: Clicking "Load More Posts" dynamically fetches and appends subsequent post batches.

### Step 8: Updating Paginated User Feeds (`routers/users.py`, `main.py`, `user_post.html`)

- **What he does**: Refactors `GET /api/users/{user_id}/posts` in `routers/users.py` to accept `skip` and `limit`, applying `.where(models.Post.user_id == user_id)` to both count and data queries. Updates `user_post_page` in `main.py` and `templates/user_post.html`.
- **Why he does it**: Applies pagination to user-specific post feeds.
- **Relevant code**:

  ```python
  @router.get("/{user_id}/posts", response_model=schemas.PaginatedPostResponse)
  async def get_user_posts(
      user_id: int,
      db: Annotated[AsyncSession, Depends(get_db)],
      skip: Annotated[int, Query(ge=0)] = 0,
      limit: Annotated[int, Query(ge=1, le=100)] = 10,
  ):
      user = (await db.execute(select(models.User).where(models.User.id == user_id))).scalars().first()
      if not user:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

      # Count query filtered by user_id
      count_stmt = select(func.count()).select_from(models.Post).where(models.Post.user_id == user_id)
      total = (await db.execute(count_stmt)).scalar() or 0

      # Data query filtered by user_id
      stmt = (
          select(models.Post)
          .where(models.Post.user_id == user_id)
          .order_by(models.Post.date_posted.desc())
          .options(selectinload(models.Post.author))
          .offset(skip)
          .limit(limit)
      )
      result = await db.execute(stmt)
      posts = result.scalars().all()

      has_more = (skip + len(posts)) < total

      return schemas.PaginatedPostResponse(
          posts=[schemas.PostResponse.model_validate(post) for post in posts],
          total=total,
          skip=skip,
          limit=limit,
          has_more=has_more,
      )
  ```

- **Result**: User profile feeds support identical paginated API endpoints and UI behaviors.

---

## 4. Code Examples

### Paginated Contract Schema (`schemas.py`)

```python
from pydantic import BaseModel
from schemas import PostResponse

class PaginatedPostResponse(BaseModel):
    posts: list[PostResponse]
    total: int
    skip: int
    limit: int
    has_more: bool
```

### Complete Paginated API Router Endpoint (`routers/posts.py`)

```python
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
import models
import schemas

router = APIRouter()

@router.get("", response_model=schemas.PaginatedPostResponse)
async def get_posts(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    # Total record count
    count_stmt = select(func.count()).select_from(models.Post)
    total = (await db.execute(count_stmt)).scalar() or 0

    # Paginated slice
    stmt = (
        select(models.Post)
        .order_by(models.Post.date_posted.desc())
        .options(selectinload(models.Post.author))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    posts = result.scalars().all()

    # Remaining items flag
    has_more = (skip + len(posts)) < total

    # Manual model validation for nested ORM serialization
    return schemas.PaginatedPostResponse(
        posts=[schemas.PostResponse.model_validate(post) for post in posts],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )
```

---

## 5. FastAPI & Python Knowledge

- **`Annotated` with `Query(...)` Validation**: Attaching `Query(ge=0)` and `Query(ge=1, le=100)` metadata parameters to `skip` and `limit` forces FastAPI to validate query parameters automatically before route handler execution. `ge=0` blocks negative offsets, while `le=100` caps batch sizes to 100 items, returning an HTTP 422 Unprocessable Entity error on invalid input.
- **Explicit Model Validation (`PostResponse.model_validate(post)`)**: When an endpoint returns a custom wrapper instance (`PaginatedPostResponse`) containing a nested list of models, FastAPI does not automatically convert raw SQLAlchemy ORM objects inside that list. Calling `schemas.PostResponse.model_validate(post)` converts ORM instances (including relationships like `author`) into Pydantic models explicitly.
- **SQLAlchemy Aggregation (`func.count()`)**: `select(func.count()).select_from(models.Post)` constructs a `SELECT COUNT(*) FROM posts` query executed directly by the SQL engine, returning total integer row counts without instantiating heavy ORM objects.
- **DOM Insertion (`insertAdjacentHTML('beforeend', ...)`)**: A browser DOM method that appends an HTML string into a container element without re-parsing or destroying existing child DOM nodes.

---

## 6. Tips & Important Details

- **Mandatory Ordering in Paginated Queries**: Always append `.order_by()` (e.g., `models.Post.date_posted.desc()`) to paginated queries. Without explicit ordering, database engines make no guarantee about row return order across separate query calls, causing items to duplicate or disappear between page loads.
- **Skip/Limit vs. Page/Per_Page**: `skip` (offset) and `limit` (count) are preferred in REST APIs due to their range flexibility. Converting from page numbers is straightforward: `skip = (page - 1) * per_page` and `limit = per_page`.
- **Backend `has_more` Simplifies Frontend Logic**: Returning a boolean `has_more` directly from the API removes calculation overhead from frontend web and mobile clients, allowing UI code to toggle "Load More" controls using a simple boolean check.
- **`fastapi-pagination` Library Alternative**: Third-party packages such as `fastapi-pagination` automate pagination boilerplate, but manual implementation provides clearer insight into underlying database query mechanics.

---

## 7. Errors & Pitfalls

- **Unbounded Batch Size Requests**: Accepting `limit` parameters without upper bound validation allows clients to request massive batch sizes (e.g. `?limit=1000000`), causing server memory exhaustion and database slowdowns. Always enforce upper limits using `Query(le=100)`.
- **Omitting Explicit `.order_by()` Clauses**: Executing offset/limit queries without explicit column sorting causes non-deterministic row ordering, resulting in missing or repeated items across pagination fetches.
- **Nested ORM Serialization Errors**: Returning raw SQLAlchemy ORM lists inside custom response dictionaries without explicit model validation (`model_validate`) causes missing attribute errors or Pydantic validation failures.
- **Client-Side XSS Vulnerabilities via `innerHTML`**: Constructing client-side HTML strings from JSON API responses without escaping user text introduces XSS vulnerabilities. Always sanitize user content strings using `escapeHtml()`.

---

## 8. Best Practices & Trade-offs

- **Offset-Based vs. Cursor-Based Pagination**:
  - **Offset-Based (`skip`/`limit`)**: Simple to implement, supports jumping to arbitrary page offsets, and works directly with SQL query tools. Trade-off: Query performance degrades on large offsets (e.g., `OFFSET 1000000`) because the database engine must scan and discard preceding rows.
  - **Cursor-Based (Keyset)**: Uses unique indexed column markers (e.g., `WHERE id < last_seen_id`). Delivers consistent query performance on massive datasets and stays immune to row drift. Trade-off: Does not support jumping to arbitrary page numbers.
- **Hybrid Rendering Pattern**:
  - Server-rendering the first batch delivers fast initial page loads and strong SEO, while client-side API requests handle subsequent pages without full page reloads.

---

## 9. Resources

- **GitHub Source Code Repository**: Companion code repository for Part 13 linked in the video description.
- **`fastapi-pagination` Package**: Third-party utility package for automated FastAPI pagination.
- **FastAPI Official Query Parameters Documentation**: Reference guide for parameter validation using `Query`.

---

## 10. Key Takeaways

1. Pagination prevents server memory exhaustion, network bandwidth bloat, and slow client render times.
2. Offset-based pagination uses `skip` (offset) and `limit` (batch size) query parameters.
3. `PaginatedPostResponse` packages resource arrays alongside `total`, `skip`, `limit`, and `has_more`.
4. Validate query parameters using `Query(ge=0)` for `skip` and `Query(ge=1, le=100)` for `limit`.
5. Execute two queries per request: `select(func.count())` for total records and `.offset(skip).limit(limit)` for page items.
6. Always include explicit `.order_by()` clauses in paginated queries to guarantee deterministic row ordering.
7. Compute `has_more = (skip + len(posts)) < total` on the backend to simplify client UI logic.
8. Convert ORM objects explicitly using `PostResponse.model_validate(post)` when constructing custom response objects.
9. Centralize page size configuration (`posts_per_page`) in `config.py`.
10. Combine initial server-side Jinja2 rendering with dynamic client-side `fetch()` loading for an optimal balance of speed, SEO, and user experience.
11. Prevent client-side XSS vulnerabilities by sanitizing user strings using `escapeHtml()`.
12. Append dynamic DOM elements efficiently using `element.insertAdjacentHTML('beforeend', ...)`.
13. Apply identical filter criteria (`.where()`) to both count and data queries on filtered routes.
14. Third-party packages like `fastapi-pagination` can reduce repetitive pagination code in production applications.

---

## 11. Quick Reference

### Paginated Schema Definition

```python
class PaginatedPostResponse(BaseModel):
    posts: list[PostResponse]
    total: int
    skip: int
    limit: int
    has_more: bool
```

### Paginated Endpoint Pattern

```python
@router.get("", response_model=schemas.PaginatedPostResponse)
async def get_posts(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    total = (await db.execute(select(func.count()).select_from(models.Post))).scalar() or 0
    stmt = (
        select(models.Post)
        .order_by(models.Post.date_posted.desc())
        .offset(skip)
        .limit(limit)
    )
    posts = (await db.execute(stmt)).scalars().all()

    return schemas.PaginatedPostResponse(
        posts=[schemas.PostResponse.model_validate(p) for p in posts],
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + len(posts)) < total,
    )
```

---

## 12. Mental Model

- **Paginated Request/Response Life Cycle**:
  1. **Client Request**: Browser requests `GET /api/posts?skip=10&limit=10`.
  2. **Query Validation**: FastAPI validates parameter constraints (`skip >= 0` and `1 <= limit <= 100`).
  3. **Total Aggregation**: Database executes `SELECT COUNT(*) FROM posts` to compute total matching records.
  4. **Data Slicing**: Database executes `SELECT * FROM posts ORDER BY date_posted DESC OFFSET 10 LIMIT 10`.
  5. **State Calculation**: Server calculates `has_more = (10 + 10) < total`.
  6. **Response Serialization**: Server converts ORM models via `model_validate()` and returns a `PaginatedPostResponse` JSON payload.
  7. **Client DOM Injection**: Client JavaScript receives JSON, sanitizes user strings via `escapeHtml()`, appends cards via `insertAdjacentHTML()`, updates `currentOffset += data.posts.length`, and removes the "Load More" button if `has_more` is `false`.

---

💡 _I have generated detailed developer study notes covering Part 13 of Corey Schafer's FastAPI series on Pagination with Query Parameters. Let me know if you would like to explore password reset functionality or background tasks next!_
