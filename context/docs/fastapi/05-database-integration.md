# Python FastAPI Tutorial (Part 5): Adding a Database - SQLAlchemy Models and Relationships

## 1. Overview

- **What this lesson teaches**: This lesson demonstrates how to replace temporary in-memory Python lists with a persistent SQL database using SQLAlchemy ORM and SQLite in a FastAPI application. It covers establishing database configuration files, creating declarative database models with relationship mappings, updating Pydantic schemas for nested response serialization, injecting transactional database sessions into route handlers using `Depends()`, updating API and HTML routes for persistent data storage, and rendering dynamic relational data in Jinja2 templates.
- **Learning objectives**:
  - Install SQLAlchemy and configure a database connection engine and session factory for SQLite.
  - Define SQLAlchemy ORM models with column types, primary keys, unique constraints, nullable flags, and default values.
  - Establish one-to-many and many-to-one relationships between `User` and `Post` models using `relationship()` and `ForeignKey`.
  - Update Pydantic schemas using `from_attributes=True` to enable ORM mode and nested schema serialization.
  - Inject database sessions into FastAPI routes using `Annotated` and `Depends(get_db)`.
  - Execute SQLAlchemy v2 database queries using `select()`, `db.execute()`, `scalars()`, `first()`, and `all()`.
  - Render relational properties and formatted dates dynamically inside Jinja2 templates.
- **Why the topic matters**: In-memory list storage causes all application data to disappear whenever the web server restarts. Connecting FastAPI to an ORM like SQLAlchemy ensures persistent data storage, enforces database integrity, auto-generates primary keys, and provides portability to production databases such as PostgreSQL with minimal configuration changes.

---

## 2. Concepts

### Three-Layer Architecture (Models, Schemas, Routes)

- **What it is**: The software design pattern of separating a web application into database models (SQLAlchemy), API contract schemas (Pydantic), and request handlers (FastAPI routes).
- **Why it is needed**: Decouples database storage structures from API representations, granting fine-grained control over accepted request inputs and returned response outputs.
- **How it works**: Pydantic validates incoming HTTP request payloads, SQLAlchemy executes database storage or retrieval operations, and Pydantic serializes ORM objects back into formatted JSON responses.
- **Important details**: While libraries like SQLModel attempt to merge models and schemas into a single class, maintaining separate layers is the industry standard in production applications.
- **Examples**: `models.User` manages database table definitions and relationships, whereas `schemas.UserResponse` dictates which user fields are returned to public API consumers.

### SQLAlchemy ORM & Database Portability

- **What it is**: The primary Object-Relational Mapping (ORM) library in Python that maps Python classes to database tables.
- **Why it is needed**: Eliminates the need to write raw SQL queries manually and abstracts database engine differences.
- **How it works**: Translates Python class declarations and method calls into database-specific SQL statements executed against SQLite, PostgreSQL, or MySQL.
- **Important details**: Switching from a local SQLite development database to a production PostgreSQL database requires updating only the database connection URL string.
- **Examples**: Executing `select(models.Post).where(models.Post.id == post_id)` generates standard SQL `SELECT` queries automatically.

### Declarative Base & SessionFactory (`DeclarativeBase`, `sessionmaker`)

- **What it is**: The core SQLAlchemy setup structures; `DeclarativeBase` serves as the parent class for ORM models, while `sessionmaker` generates transactional database sessions.
- **Why it is needed**: Establishes central metadata mapping for database tables and manages transactional state for queries.
- **How it works**: Subclassing `DeclarativeBase` registers models with a central metadata object, while invoking `SessionLocal()` creates an isolated transactional session.
- **Important details**: Inheriting from `DeclarativeBase` represents modern SQLAlchemy v2 syntax with enhanced IDE type-checking support, replacing the legacy `declarative_base()` function.
- **Examples**: `class Base(DeclarativeBase): pass` and `SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)`.

### Database Session Generator (`get_db`)

- **What it is**: A generator function that manages individual database session lifecycles per HTTP request.
- **Why it is needed**: Guarantees that each HTTP request operates within its own clean transaction and cleans up resources when the request completes.
- **How it works**: Utilizes a context manager (`with SessionLocal() as db: yield db`) to instantiate a session, yield it to the route handler, and close it upon completion.
- **Important details**: The context manager guarantees session cleanup even if an uncaught exception occurs during request processing.
- **Examples**: `def get_db(): with SessionLocal() as db: yield db`.

### Relational Mapping (`relationship()` & `ForeignKey`)

- **What it is**: Declarative tools used to link separate database tables together in a relational schema.
- **Why it is needed**: Connects records across tables (such as linking multiple blog posts to a single user author).
- **How it works**: `ForeignKey("users.id")` enforces relational integrity at the database level, while `relationship(back_populates=...)` links Python attributes across models.
- **Important details**: Foreign key columns should include `index=True` for faster filtering; `back_populates` links bidirectional attributes (`user.posts` and `post.author`).
- **Examples**: `posts: Mapped[list["Post"]] = relationship(back_populates="author")` defined on `User`, and `author: Mapped["User"] = relationship(back_populates="posts")` defined on `Post`.

### Nested Response Serialization (`from_attributes=True`)

- **What it is**: A Pydantic configuration setting that allows schemas to extract data directly from ORM model attributes and Python properties.
- **Why it is needed**: Converts complex SQLAlchemy ORM models and relationships directly into structured, nested JSON responses.
- **How it works**: Pydantic accesses ORM object properties (such as `post.author`) and validates them against nested schemas (`UserResponse`).
- **Important details**: Datetime fields are automatically serialized into standard ISO 8601 strings during response generation.
- **Examples**: Setting `model_config = ConfigDict(from_attributes=True)` inside `UserResponse` and `PostResponse`.

---

## 3. Step-by-Step Tutorial

### Step 1: Installing SQLAlchemy

- **What he does**: Executes `uv add sqlalchemy` in the terminal to install SQLAlchemy into the project environment.
- **Why he does it**: Installs the ORM library required to interact with databases in Python.
- **Relevant code**:
  ```bash
  uv add sqlalchemy
  ```
- **How the code works**: Downloads and installs SQLAlchemy; SQLite requires no extra driver installation because it is built into the Python standard library.
- **Result**: SQLAlchemy packages become available for import across project modules.

### Step 2: Creating Database Configuration (`database.py`)

- **What he does**: Creates `database.py` to store connection strings, engine instances, session factories, declarative bases, and the session generator function.
- **Why he does it**: Centralizes database configuration so it can be imported cleanly by `main.py` and model files.
- **Relevant code**:

  ```python
  from sqlalchemy import create_engine
  from sqlalchemy.orm import DeclarativeBase, sessionmaker

  SQLALCHEMY_DATABASE_URL = "sqlite:///./blog.db"

  engine = create_engine(
      SQLALCHEMY_DATABASE_URL,
      connect_args={"check_same_thread": False}
  )

  SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

  class Base(DeclarativeBase):
      pass

  def get_db():
      with SessionLocal() as db:
          yield db
  ```

- **How the code works**: `create_engine` establishes the database connection; `connect_args={"check_same_thread": False}` allows multi-threaded FastAPI requests on SQLite; `SessionLocal` configures transactional sessions; `get_db` yields sessions per request.
- **Result**: The database connection and session provider are ready for application integration.

### Step 3: Building SQLAlchemy Models (`models.py`)

- **What he does**: Creates `models.py` defining `User` and `Post` ORM models with primary keys, constraints, foreign keys, relationships, and a dynamic image path property.
- **Why he does it**: Establishes database table schemas and relationship mappings using SQLAlchemy v2 syntax.
- **Relevant code**:

  ```python
  from __future__ import annotations
  from datetime import datetime, timezone
  from sqlalchemy import ForeignKey, DateTime
  from sqlalchemy.orm import Mapped, mapped_column, relationship
  from database import Base

  class User(Base):
      __tablename__ = "users"

      id: Mapped[int] = mapped_column(primary_key=True)
      username: Mapped[str] = mapped_column(unique=True, nullable=False)
      email: Mapped[str] = mapped_column(unique=True, nullable=False)
      image_file: Mapped[str | None] = mapped_column(default=None)

      posts: Mapped[list[Post]] = relationship(back_populates="author")

      @property
      def image_path(self) -> str:
          if self.image_file:
              return f"/media/profile_pics/{self.image_file}"
          return "/static/profile_pics/default.jpeg"

  class Post(Base):
      __tablename__ = "posts"

      id: Mapped[int] = mapped_column(primary_key=True)
      title: Mapped[str] = mapped_column(nullable=False)
      content: Mapped[str] = mapped_column(nullable=False)
      user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
      date_posted: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          default=lambda: datetime.now(timezone.utc)
      )

      author: Mapped[User] = relationship(back_populates="posts")
  ```

- **How the code works**: `Mapped` and `mapped_column` define table columns; `ForeignKey("users.id")` links posts to users; `index=True` optimizes query speeds; `relationship()` binds relational objects; `image_path` dynamically resolves image URLs.
- **Result**: Database table schemas and ORM relationships are fully defined.

### Step 4: Updating Pydantic Schemas (`schemas.py`)

- **What he does**: Updates `schemas.py` to add `UserBase`, `UserCreate`, and `UserResponse`, and refactors `PostCreate` and `PostResponse` to support nested user serialization and ORM attribute reading.
- **Why he does it**: Aligns API response schemas with database models and enables nested JSON output.
- **Relevant code**:

  ```python
  from datetime import datetime
  from pydantic import BaseModel, ConfigDict, EmailStr, Field

  class UserBase(BaseModel):
      username: str = Field(min_length=1, max_length=50)
      email: EmailStr = Field(max_length=120)

  class UserCreate(UserBase):
      pass

  class UserResponse(UserBase):
      model_config = ConfigDict(from_attributes=True)

      id: int
      image_file: str | None
      image_path: str

  class PostBase(BaseModel):
      title: str
      content: str

  class PostCreate(PostBase):
      user_id: int

  class PostResponse(PostBase):
      model_config = ConfigDict(from_attributes=True)

      id: int
      user_id: int
      date_posted: datetime
      author: UserResponse
  ```

- **How the code works**: `EmailStr` auto-validates email formats; `from_attributes=True` allows reading ORM attributes and properties; `author: UserResponse` produces nested JSON objects.
- **Result**: API contract schemas are configured to handle relational ORM objects.

### Step 5: Updating `main.py` Imports and Table Initialization

- **What he does**: Updates imports in `main.py`, calls `Base.metadata.create_all(bind=engine)`, mounts the `/media` static directory, creates `media/profile_pics` on disk, and removes the in-memory `posts` list.
- **Why he does it**: Automatically creates database tables on application startup and prepares user upload storage.
- **Relevant code**:

  ```python
  from typing import Annotated
  from fastapi import FastAPI, Depends, HTTPException, status
  from fastapi.staticfiles import StaticFiles
  from sqlalchemy import select
  from sqlalchemy.orm import Session

  from database import Base, engine, get_db
  import models

  Base.metadata.create_all(bind=engine)

  app = FastAPI()

  app.mount("/static", StaticFiles(directory="static"), name="static")
  app.mount("/media", StaticFiles(directory="media"), name="media")
  ```

- **How the code works**: `Base.metadata.create_all()` checks for missing database tables and creates them idempotently on server startup.
- **Result**: `blog.db` is initialized on disk, and static/media folders are mounted.

### Step 6: Creating User API Endpoints (`POST /api/users` & `GET /api/users/{user_id}`)

- **What he does**: Adds user creation and lookup routes in `main.py`, implementing duplicate checks for username and email before inserting records.
- **Why he does it**: Provides endpoints to manage user accounts required for post authorship.
- **Relevant code**:

  ```python
  @app.post("/api/users", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
  def create_user(user: schemas.UserCreate, db: Annotated[Session, Depends(get_db)]):
      existing_username = db.execute(select(models.User).where(models.User.username == user.username)).scalars().first()
      if existing_username:
          raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

      existing_email = db.execute(select(models.User).where(models.User.email == user.email)).scalars().first()
      if existing_email:
          raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

      new_user = models.User(username=user.username, email=user.email)
      db.add(new_user)
      db.commit()
      db.refresh(new_user)
      return new_user

  @app.get("/api/users/{user_id}", response_model=schemas.UserResponse)
  def get_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
      user = db.execute(select(models.User).where(models.User.id == user_id)).scalars().first()
      if not user:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
      return user
  ```

- **How the code works**: `Depends(get_db)` injects database sessions; `db.execute(select(...))` queries records; `db.add()`, `db.commit()`, and `db.refresh()` persist new users.
- **Result**: Users can be created and fetched via API calls, returning 400 errors for duplicate credentials and 404 for missing IDs.

### Step 7: Refactoring Post API Endpoints for Database Persistence

- **What he does**: Refactors `GET /api/posts`, `POST /api/posts`, and `GET /api/posts/{post_id}` to query and store data in SQLite.
- **Why he does it**: Replaces in-memory operations with persistent database operations.
- **Relevant code**:

  ```python
  @app.get("/api/posts", response_model=list[schemas.PostResponse])
  def get_posts(db: Annotated[Session, Depends(get_db)]):
      return db.execute(select(models.Post)).scalars().all()

  @app.post("/api/posts", response_model=schemas.PostResponse, status_code=status.HTTP_201_CREATED)
  def create_post(post: schemas.PostCreate, db: Annotated[Session, Depends(get_db)]):
      user = db.execute(select(models.User).where(models.User.id == post.user_id)).scalars().first()
      if not user:
          raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

      new_post = models.Post(title=post.title, content=post.content, user_id=post.user_id)
      db.add(new_post)
      db.commit()
      db.refresh(new_post)
      return new_post

  @app.get("/api/posts/{post_id}", response_model=schemas.PostResponse)
  def get_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
      db_post = db.execute(select(models.Post).where(models.Post.id == post_id)).scalars().first()
      if not db_post:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
      return db_post
  ```

- **How the code works**: Validates author existence before post insertion, executes inserts, and queries posts while automatically populating nested author details.
- **Result**: Posts persist in the database across server restarts and include full author metadata.

### Step 8: Creating User Posts Endpoints (`GET /api/users/{user_id}/posts` & `GET /user/{user_id}`)

- **What he does**: Adds API and HTML routes to retrieve all posts authored by a specific user.
- **Why he does it**: Enables viewing user-specific post feeds while distinguishing between a non-existent user (404) and a user with zero posts (empty list).
- **Relevant code**:

  ```python
  @app.get("/api/users/{user_id}/posts", response_model=list[schemas.PostResponse])
  def get_user_posts(user_id: int, db: Annotated[Session, Depends(get_db)]):
      user = db.execute(select(models.User).where(models.User.id == user_id)).scalars().first()
      if not user:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
      return db.execute(select(models.Post).where(models.Post.user_id == user_id)).scalars().all()

  @app.get("/user/{user_id}", include_in_schema=False, name="user_post")
  def user_post_page(request: Request, user_id: int, db: Annotated[Session, Depends(get_db)]):
      user = db.execute(select(models.User).where(models.User.id == user_id)).scalars().first()
      if not user:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
      posts = db.execute(select(models.Post).where(models.Post.user_id == user_id)).scalars().all()
      return templates.TemplateResponse(
          request=request,
          name="user_post.html",
          context={"posts": posts, "user": user, "title": f"Posts by {user.username}"}
      )
  ```

- **How the code works**: Verifies user existence first; if valid, fetches associated posts and renders them via API or Jinja2 template.
- **Result**: Navigating to `/user/1` renders a dedicated HTML page showing posts created by that user.

### Step 9: Updating Jinja2 Templates and Date Formatting

- **What he does**: Updates `home.html` and `post.html` to reference `post.author.username` and `post.author.image_path`, formats dates using `.strftime()`, and creates `user_post.html`.
- **Why he does it**: Renders relational user data dynamically and formats raw datetime objects into readable strings.
- **Relevant code**:
  ```html
  <img
    class="rounded-circle article-img"
    src="{{ post.author.image_path }}"
    alt="Profile Picture"
  />
  <a class="mr-2" href="{{ url_for('user_post', user_id=post.author.id) }}"
    >{{ post.author.username }}</a
  >
  <small class="text-muted">{{ post.date_posted.strftime("%B %d, %Y") }}</small>
  ```
- **How the code works**: Accesses relationship attributes (`post.author.username`); invokes Python's `strftime` method directly inside Jinja2 templates to format dates as "April 20, 2024".
- **Result**: HTML pages display dynamic user avatars, hyperlinked author names, and formatted dates.

### Step 10: Running the Application and Testing via Swagger UI & Browser

- **What he does**: Launches the server using `uv run fastapi dev main.py`, verifies `blog.db` creation, creates test users and posts via `/docs`, and navigates browser pages.
- **Why he does it**: Confirms that database creation, API validation, relational data serialization, and HTML rendering work without errors.
- **Result**: Test records are stored in `blog.db` and persist across server restarts.

---

## 4. Code Examples

### Full `database.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Database URL for local SQLite storage
SQLALCHEMY_DATABASE_URL = "sqlite:///./blog.db"

# Engine setup with multi-thread checking disabled for SQLite compatibility
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Transactional session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Modern SQLAlchemy v2 Declarative Base
class Base(DeclarativeBase):
    pass

# Session provider generator for dependency injection
def get_db():
    with SessionLocal() as db:
        yield db
```

### Full `models.py`

```python
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True, nullable=False)
    email: Mapped[str] = mapped_column(unique=True, nullable=False)
    image_file: Mapped[str | None] = mapped_column(default=None)

    # One-to-Many Relationship: One user has many posts
    posts: Mapped[list[Post]] = relationship(back_populates="author")

    # Dynamic image path property
    @property
    def image_path(self) -> str:
        if self.image_file:
            return f"/media/profile_pics/{self.image_file}"
        return "/static/profile_pics/default.jpeg"

class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date_posted: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # Many-to-One Relationship: Many posts belong to one author
    author: Mapped[User] = relationship(back_populates="posts")
```

### Full `schemas.py`

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: EmailStr = Field(max_length=120)

class UserCreate(UserBase):
    pass

class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    image_file: str | None
    image_path: str

class PostBase(BaseModel):
    title: str
    content: str

class PostCreate(PostBase):
    user_id: int

class PostResponse(PostBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    date_posted: datetime
    author: UserResponse
```

---

## 5. FastAPI & Python Knowledge

- **`Annotated` Dependency Injection (`Annotated[Session, Depends(get_db)]`)**: Combines Python type hints with FastAPI's dependency injection system, instructing FastAPI to execute `get_db()`, inject the yielded session into the handler, and perform automatic cleanup.
- **Generator Functions & `yield`**: The `yield` keyword pauses `get_db()` execution to hand control and the session instance over to the route function, resuming after request processing to close the context manager.
- **Modern SQLAlchemy v2 Type Mapping (`Mapped` & `mapped_column`)**: Standardized SQLAlchemy v2 syntax providing explicit Python type annotations (`Mapped[int]`) for static analysis and IDE autocompletion.
- **Forward References & `from __future__ import annotations`**: Allows referencing classes (such as `Post`) before their definition in Python files; required on Python versions prior to 3.14.
- **Python `@property` Decorator on Models**: Computes properties dynamically on model instances; Pydantic reads these properties during serialization when `from_attributes=True` is enabled.
- **ISO 8601 Serialization vs. Frontend Formatting**: APIs return standardized ISO 8601 UTC timestamp strings, delegating human-readable date formatting to frontend templates or clients.

---

## 6. Tips & Important Details

- **SQLite Multi-Threading Config**: Setting `connect_args={"check_same_thread": False}` is required for SQLite because FastAPI handles requests across multiple threads.
- **Foreign Key Indexing**: Setting `index=True` on foreign key columns (`user_id`) speeds up read queries when filtering posts by author, accepting a minor trade-off in write speed.
- **Decoupling Database Data from Filesystems**: Storing only image filenames (e.g. `corey.jpeg`) rather than full folder paths in database columns allows reorganizing file storage structures without updating database rows.
- **Separating Static Assets and User Media**: Storing default application images in `/static` and user-uploaded media in `/media` simplifies server deployments, backups, and Git version control.
- **Idempotent Table Creation**: `Base.metadata.create_all(bind=engine)` creates missing database tables safely without modifying existing tables or overwriting data.
- **Database Reset Shortcut**: Deleting `blog.db` during development wipes out existing test data and forces FastAPI to regenerate clean, empty database tables on the next startup.

---

## 7. Errors & Pitfalls

- **Hardcoding Full File Paths in Database Columns**: Storing full folder paths in database rows creates tight coupling between storage paths and data, requiring database migrations if directories are renamed.
- **Omitting Indexes on Foreign Keys**: Leaving foreign key columns unindexed leads to full table scans when querying related records, causing performance degradation as tables grow.
- **Omitting Forward Reference Annotations on Older Python Versions**: Defining relationship types using undefined classes without importing `from __future__ import annotations` raises `NameError` exceptions on Python versions prior to 3.14.
- **Querying User Posts Without Validating User Existence**: Executing post queries directly for missing user IDs returns an empty list `[]`, making it impossible to distinguish between a non-existent user and a user who has not published any posts.
- **Template Route Name Mismatches in `url_for`**: Calling `url_for('user_post_page')` when the decorator sets `name="user_post"` raises Jinja2 rendering errors.

---

## 8. Best Practices & Trade-offs

- **Three-Layer Architecture vs. Single Model Frameworks**: Maintaining separate SQLAlchemy models and Pydantic schemas requires writing additional boilerplate code compared to unified libraries like SQLModel, but provides finer control over API payloads and aligns with industry production standards.
- **Foreign Key Indexing Trade-offs**: Adding `index=True` to foreign keys increases query read speeds at the cost of slightly slower database write operations and slightly larger storage footprints.
- **Explicit User Validation Prior to Relational Inserts**: Checking for existing records (e.g. verifying `user_id` before creating a post) in application code returns clear, custom HTTP 400 messages instead of uncaught database integrity exceptions.
- **Explicit `db.refresh()` Invocation**: While SQL Alchemy tracks generated primary key IDs automatically after `db.commit()`, calling `db.refresh(obj)` guarantees that server-side defaults and triggers are reloaded into memory.

---

## 9. Resources

- **GitHub Source Code Repository**: Downloadable source code for Part 5 is linked in the video description.
- **SQLAlchemy Documentation**: Official reference for SQLAlchemy ORM, model declarative mapping, and relationship configurations.
- **Interactive API Documentation Routes**:
  - Swagger UI: `http://localhost:8000/docs`
  - ReDoc: `http://localhost:8000/redoc`
- **SQLite Database Viewers**: External GUI tools can be used to open and inspect the generated `blog.db` database file.

---

## 10. Key Takeaways

1. Replacing in-memory lists with SQL databases ensures data persistence across server restarts.
2. SQLAlchemy ORM maps Python model classes directly to database tables.
3. SQLite is built into Python and serves as an ideal development database.
4. Changing database connection URLs allows migrating from SQLite to PostgreSQL without modifying application code.
5. Maintaining separate models, schemas, and routes aligns with production industry standards.
6. `DeclarativeBase` and `sessionmaker` establish table metadata mappings and transactional session factories.
7. `get_db()` utilizes generator `yield` logic to provide clean, isolated database sessions per request.
8. `ForeignKey("users.id")` enforces relational database integrity between posts and authors.
9. `relationship(back_populates=...)` connects bidirectional Python attributes across ORM models.
10. `index=True` on foreign keys optimizes query performance when filtering child records.
11. Pydantic schemas with `from_attributes=True` read ORM attributes and `@property` getters.
12. Nested Pydantic schemas (`author: UserResponse`) serialize relational ORM objects into nested JSON automatically.
13. `Annotated[Session, Depends(get_db)]` injects database sessions into route handlers with automatic cleanup.
14. `Base.metadata.create_all(bind=engine)` creates missing database tables on application startup.
15. Python's `.strftime()` method can be invoked directly inside Jinja2 templates to format datetime objects.

---

## 11. Quick Reference

### Command Line

```bash
# Install SQLAlchemy using uv
uv add sqlalchemy

# Run development server with auto-reload
uv run fastapi dev main.py
```

### Essential Imports

```python
from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import create_engine, select, ForeignKey, DateTime
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Mapped, mapped_column, relationship, Session
from pydantic import BaseModel, ConfigDict, EmailStr, Field
```

### Database & Dependency Setup

```python
SQLALCHEMY_DATABASE_URL = "sqlite:///./blog.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as db:
        yield db
```

### Route Injection Pattern

```python
@app.get("/api/posts", response_model=list[schemas.PostResponse])
def get_posts(db: Annotated[Session, Depends(get_db)]):
    return db.execute(select(models.Post)).scalars().all()
```

---

## 12. Mental Model

- **Data Lifecycle & Request Flow**:
  1. **HTTP Request Arrival**: An incoming HTTP request (e.g. `POST /api/posts`) hits a FastAPI route handler.
  2. **Pydantic Input Validation**: FastAPI validates the JSON payload against `schemas.PostCreate`.
  3. **Dependency Injection Gate**: FastAPI executes `get_db()`, instantiating a `SessionLocal()` transactional session, and injects it as the `db` parameter.
  4. **ORM Query & Transaction Execution**: The handler performs checks via `db.execute(select(...))`, instantiates `models.Post`, and calls `db.add()`, `db.commit()`, and `db.refresh()`.
  5. **Relational Loading & Nested Response Serialization**: Returning the model instance prompts Pydantic (`from_attributes=True`) to read ORM fields, access `post.author`, serialize author data via `UserResponse`, format timestamps to ISO 8601 strings, and output nested JSON.
  6. **Automatic Resource Cleanup**: The `get_db()` generator resumes after route execution, closing the database session automatically.
