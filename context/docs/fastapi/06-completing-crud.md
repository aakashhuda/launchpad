# Python FastAPI Tutorial (Part 6): Completing CRUD - Update and Delete (PUT, PATCH, DELETE)

## 1. Overview

- **What this lesson teaches**: This lesson completes the CRUD (Create, Read, Update, Delete) cycle for a FastAPI application with a SQLAlchemy database backend. It covers implementing full updates using HTTP `PUT`, partial updates using HTTP `PATCH`, and resource deletions using HTTP `DELETE`. It demonstrates how to build Pydantic schemas with optional fields using `model_dump(exclude_unset=True)`, dynamically update ORM instance attributes with `setattr()`, return proper HTTP status codes (such as `204 No Content`), configure SQLAlchemy cascade deletions (`cascade="all, delete-orphan"`), and update profile picture metadata to render updated user media on the frontend.
- **Learning objectives**:
  - Understand the architectural and semantic differences between HTTP `PUT` (full replacement) and HTTP `PATCH` (partial update).
  - Construct Pydantic schemas with optional fields (`str | None = None`) for partial updates while maintaining field validation.
  - Use `model_dump(exclude_unset=True)` to extract only the parameters explicitly provided in a request payload.
  - Dynamically update SQLAlchemy ORM attributes using `setattr()` inside dictionary iteration loops.
  - Implement HTTP `DELETE` endpoints returning `204 No Content` status codes without a response body.
  - Standardize API HTTP status codes (`200`, `201`, `204`, `400`, `404`, `422`) across all endpoints.
  - Configure SQLAlchemy relationship cascade deletions (`cascade="all, delete-orphan"`) to clean up child records automatically when a parent record is deleted.
  - Update user avatar file metadata to test dynamic media resolution on the HTML frontend.
- **Why the topic matters**: Complete CRUD functionality is fundamental to web application and REST API development. Correctly differentiating between `PUT` and `PATCH` ensures clients are not forced to transmit entire resource objects just to modify a single field. Implementing cascade deletions prevents orphan records and database integrity errors, while returning accurate HTTP status codes creates predictable, production-grade API contracts.

---

## 2. Concepts

### PUT vs. PATCH HTTP Update Verbs

- **What it is**: Two distinct HTTP methods used in REST APIs to update existing database resources.
- **Why it is needed**: APIs must provide clear contracts for whether a client is completely replacing a resource or selectively updating specific fields.
- **How it works**:
  - **`PUT` (Full Replacement)**: Expects the client to send _all_ fields required to construct the resource. The target record is effectively replaced with the newly supplied payload.
  - **`PATCH` (Partial Update)**: Expects the client to send _only_ the fields that have changed. Any field omitted from the request payload remains untouched in the database.
- **Important details**: `PATCH` is generally more practical and widely used in APIs because it spares clients from having to read, preserve, and re-transmit unchanged fields.
- **Examples**: Sending `{"title": "Updated Title"}` via `PATCH` updates only the title; sending the same payload via `PUT` would fail validation if required fields like `content` or `user_id` are missing.

### Partial Updates with Pydantic (`model_dump(exclude_unset=True)`)

- **What it is**: A Pydantic v2 model method that exports model fields into a Python dictionary, filtering out any field that was not explicitly provided in the request payload.
- **Why it is needed**: When Pydantic schemas declare optional fields with default values of `None`, converting the schema via standard `model_dump()` returns a dictionary containing `{"content": None}` for omitted fields. Writing those `None` values to the database would overwrite existing valid data.
- **How it works**: Passing `exclude_unset=True` instructs Pydantic to inspect the raw request JSON and include _only_ the keys explicitly sent by the client.
- **Important details**: Differentiates between a field that was left out of the request payload versus a field explicitly set to `null` by the client.
- **Examples**: `update_data = post_data.model_dump(exclude_unset=True)`.

### Dynamic Attribute Assignment (`setattr()`)

- **What it is**: A built-in Python function (`setattr(object, name, value)`) that sets a named attribute on a given object dynamically at runtime.
- **Why it is needed**: Avoids writing repetitive conditional checks (`if post_data.title is not None: post.title = post_data.title`) when applying partial updates across multiple model attributes.
- **How it works**: Iterates over key-value pairs from the `update_data` dictionary and assigns each value directly to the corresponding attribute on the SQLAlchemy ORM instance.
- **Important details**: Works seamlessly alongside `model_dump(exclude_unset=True)` because the dictionary contains only valid, client-provided attributes.
- **Examples**: `for field, value in update_data.items(): setattr(post, field, value)`.

### Cascade Deletion (`cascade="all, delete-orphan"`)

- **What it is**: A SQLAlchemy relationship configuration that automatically deletes dependent child records when their parent record is deleted.
- **Why it is needed**: Deleting a parent row (e.g., a `User`) that is referenced by child rows (e.g., `Post` entries with foreign keys pointing to `user.id`) will trigger database foreign key constraint errors or leave unreferenced orphan rows in the database.
- **How it works**: Setting `cascade="all, delete-orphan"` on `relationship()` instructs SQLAlchemy to issue `DELETE` statements for all associated child objects whenever the parent object is passed to `db.delete()`.
- **Important details**: `delete-orphan` ensures that if a child record is removed from a parent's relationship collection (e.g., `user.posts.remove(post)`), SQLAlchemy automatically deletes the orphaned child row from the database.
- **Examples**: `posts: Mapped[list[Post]] = relationship(back_populates="author", cascade="all, delete-orphan")` defined in `models.User`.

### HTTP Status Code 204 No Content

- **What it is**: An HTTP status code (`204`) indicating that an operation succeeded and that the server is returning no message body in the response.
- **Why it is needed**: Standardizes API responses for deletion operations where returning the deleted object is unnecessary.
- **How it works**: Decorating a route with `status_code=status.HTTP_204_NO_CONTENT` and omitting `response_model` tells FastAPI to send an empty HTTP body with a `204` status header.
- **Important details**: Returning a value from a 204 route will cause an error or violate HTTP specifications; the handler function should complete its work and return `None` or implicitly end.
- **Examples**: `@app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)`.

---

## 3. Step-by-Step Tutorial

### Step 1: Creating the `PostUpdate` Partial Schema (`schemas.py`)

- **What he does**: Defines `PostUpdate(BaseModel)` in `schemas.py`, making `title` and `content` optional fields with default values of `None`, while retaining string length validations.
- **Why he does it**: Provides a schema specifically for `PATCH` operations where clients can submit any combination of fields without supplying a full payload.
- **Relevant code**:
  ```python
  class PostUpdate(BaseModel):
      title: str | None = Field(default=None, min_length=1, max_length=100)
      content: str | None = Field(default=None, min_length=1)
  ```
- **How the code works**: `str | None = Field(default=None, ...)` allows the field to be omitted or set to `None`. If a value is provided, Pydantic still enforces `min_length` and `max_length` rules. `user_id` is deliberately excluded so post ownership cannot be altered via partial updates.
- **Result**: `PostUpdate` is ready to validate partial post updates.

### Step 2: Implementing the Full Update Endpoint (`PUT /api/posts/{post_id}`)

- **What he does**: Adds a `PUT` endpoint in `main.py` using `schemas.PostCreate` to require all post fields (`title`, `content`, `user_id`).
- **Why he does it**: Implements full resource replacement semantics according to REST standards.
- **Relevant code**:

  ```python
  @app.put("/api/posts/{post_id}", response_model=schemas.PostResponse)
  def update_post_full(
      post_id: int,
      post_data: schemas.PostCreate,
      db: Annotated[Session, Depends(get_db)]
  ):
      post = db.execute(select(models.Post).where(models.Post.id == post_id)).scalars().first()
      if not post:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

      if post_data.user_id != post.user_id:
          user = db.execute(select(models.User).where(models.User.id == post_data.user_id)).scalars().first()
          if not user:
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

      post.title = post_data.title
      post.content = post_data.content
      post.user_id = post_data.user_id

      db.commit()
      db.refresh(post)
      return post
  ```

- **How the code works**: Verifies the target post exists (raising 404 if missing). If the payload changes the author `user_id`, it checks whether the new user exists (raising 400 if invalid) before updating fields. Overwrites `title`, `content`, and `user_id`, commits changes, refreshes the instance, and returns the updated post.
- **Result**: `PUT` requests replace all post fields in the database.

### Step 3: Testing `PUT` in Interactive Documentation

- **What he does**: Launches the application server (`fastapi dev`), navigates to `/docs`, and executes a `PUT` request on post ID `1`.
- **Why he does it**: Confirms that full updates succeed when all required fields are provided and tests changing author ownership to Jane Doe (`user_id = 2`).
- **Result**: The endpoint returns an HTTP 200 status code with updated title, content, and owner.

### Step 4: Implementing the Partial Update Endpoint (`PATCH /api/posts/{post_id}`)

- **What he does**: Creates a `PATCH` endpoint using `schemas.PostUpdate`, `model_dump(exclude_unset=True)`, and `setattr()`.
- **Why he does it**: Allows clients to update individual post fields without overwriting omitted fields with `None`.
- **Relevant code**:

  ```python
  @app.patch("/api/posts/{post_id}", response_model=schemas.PostResponse)
  def update_post_partial(
      post_id: int,
      post_data: schemas.PostUpdate,
      db: Annotated[Session, Depends(get_db)]
  ):
      post = db.execute(select(models.Post).where(models.Post.id == post_id)).scalars().first()
      if not post:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

      update_data = post_data.model_dump(exclude_unset=True)

      for field, value in update_data.items():
          setattr(post, field, value)

      db.commit()
      db.refresh(post)
      return post
  ```

- **How the code works**: Retrieves the post record. Calls `model_dump(exclude_unset=True)` to extract only client-supplied fields into a dictionary. Iterates over the dictionary using `setattr(post, field, value)` to update only the provided attributes before committing and refreshing.
- **Result**: Partial updates modify specified fields while leaving unmentioned fields untouched.

### Step 5: Testing `PATCH` in Interactive Documentation

- **What he does**: Executes a `PATCH` request on post ID `1` containing only a new `title` (`"partially updated title"`), leaving `content` out of the JSON request.
- **Why he does it**: Verifies that `exclude_unset=True` prevents `content` from being overwritten with `None`.
- **Result**: Returns an HTTP 200 status code showing the updated title alongside the preserved original content.

### Step 6: Implementing the Delete Post Endpoint (`DELETE /api/posts/{post_id}`)

- **What he does**: Adds a `DELETE` endpoint decorated with `status_code=status.HTTP_204_NO_CONTENT`.
- **Why he does it**: Provides a route to remove individual post records from the database.
- **Relevant code**:

  ```python
  @app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
  def delete_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
      post = db.execute(select(models.Post).where(models.Post.id == post_id)).scalars().first()
      if not post:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

      db.delete(post)
      db.commit()
  ```

- **How the code works**: Looks up the post ID (raising 404 if not found). Calls `db.delete(post)` followed by `db.commit()` to remove the row from the database.
- **Result**: Deletes post ID `1` and returns an HTTP `204 No Content` response. Subsequent GET requests for post `1` return 404.

### Step 7: Reviewing API HTTP Status Codes

- **What he does**: Pauses coding to review standard HTTP status codes used across the API:
  - `200 OK`: Successful `GET`, `PUT`, or `PATCH` operations.
  - `201 Created`: Successful `POST` operations.
  - `204 No Content`: Successful `DELETE` operations.
  - `400 Bad Request`: Business rule violations (e.g., duplicate username/email).
  - `404 Not Found`: Non-existent resources.
  - `422 Unprocessable Content`: Automatic Pydantic input validation failures.
- **Why he does it**: Emphasizes that returning correct status codes creates a predictable REST API contract for client applications.

### Step 8: Creating the `UserUpdate` Schema (`schemas.py`)

- **What he does**: Adds `UserUpdate(BaseModel)` to `schemas.py` with optional `username`, `email`, and `image_file` fields.
- **Why he does it**: Enables partial updates for user profile information, including updating profile picture filenames.
- **Relevant code**:
  ```python
  class UserUpdate(BaseModel):
      username: str | None = Field(default=None, min_length=1, max_length=50)
      email: EmailStr | None = Field(default=None, max_length=120)
      image_file: str | None = Field(default=None, min_length=1, max_length=200)
  ```
- **How the code works**: All fields default to `None`. `image_file` accepts a profile image filename (e.g., `"Corey.png"`), leaving path resolution to the `User.image_path` property.
- **Result**: `UserUpdate` schema is defined.

### Step 9: Implementing the User Partial Update Endpoint (`PATCH /api/users/{user_id}`)

- **What he does**: Creates a `PATCH` route for users in `main.py` that validates unique usernames and emails before updating. Demonstrates explicit `if val is not None` checks as a manual alternative to `setattr()`.
- **Why he does it**: Prevents users from updating their profile to a username or email already registered by another account.
- **Relevant code**:

  ```python
  @app.patch("/api/users/{user_id}", response_model=schemas.UserResponse)
  def update_user(
      user_id: int,
      user_update: schemas.UserUpdate,
      db: Annotated[Session, Depends(get_db)]
  ):
      user = db.execute(select(models.User).where(models.User.id == user_id)).scalars().first()
      if not user:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

      if user_update.username is not None and user_update.username != user.username:
          existing_username = db.execute(
              select(models.User).where(models.User.username == user_update.username)
          ).scalars().first()
          if existing_username:
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already in use")

      if user_update.email is not None and user_update.email != user.email:
          existing_email = db.execute(
              select(models.User).where(models.User.email == user_update.email)
          ).scalars().first()
          if existing_email:
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use")

      if user_update.username is not None:
          user.username = user_update.username
      if user_update.email is not None:
          user.email = user_update.email
      if user_update.image_file is not None:
          user.image_file = user_update.image_file

      db.commit()
      db.refresh(user)
      return user
  ```

- **How the code works**: Retrieves the user record. If `username` or `email` is supplied and differs from current values, it checks for database duplicates (raising 400 if taken). Updates explicitly provided fields manually, commits, refreshes, and returns the updated user.
- **Result**: Users can update profile fields safely without violating uniqueness constraints.

### Step 10: Configuring Cascade Delete in SQLAlchemy Models (`models.py`)

- **What he does**: Opens `models.py` and updates `User.posts` relationship to include `cascade="all, delete-orphan"`.
- **Why he does it**: Ensures that deleting a user account automatically deletes all associated blog posts written by that user.
- **Relevant code**:
  ```python
  class User(Base):
      __tablename__ = "users"
      ...
      posts: Mapped[list[Post]] = relationship(
          back_populates="author",
          cascade="all, delete-orphan"
      )
  ```
- **How the code works**: Configures SQLAlchemy's ORM unit of work to cascade deletion operations down to associated `Post` child records.
- **Result**: Deleting a user row automatically cleans up all associated post rows.

### Step 11: Implementing the Delete User Endpoint & Testing Cascade Delete

- **What he does**: Implements `DELETE /api/users/{user_id}` returning `204 No Content`. Creates a test post for Jane Doe (`user_id = 2`), deletes user `2`, and verifies that Jane Doe's posts are automatically deleted.
- **Why he does it**: Tests that cascade deletion functions as intended during account deletion.
- **Relevant code**:

  ```python
  @app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
  def delete_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
      user = db.execute(select(models.User).where(models.User.id == user_id)).scalars().first()
      if not user:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

      db.delete(user)
      db.commit()
  ```

- **How the code works**: Deleting the user instance triggers SQLAlchemy's cascade rules, executing `DELETE` operations for user `2` and all posts where `user_id == 2`.
- **Result**: User `2` is deleted with HTTP 204. Querying `GET /api/posts` confirms Jane Doe's posts have been completely removed from the database.

### Step 12: Updating Profile Pictures and Frontend Verification

- **What he does**: Manually places an image file (`Corey.png`) into `media/profile_pics/`, submits a `PATCH` request to user `1` setting `image_file="Corey.png"`, and reloads the HTML homepage.
- **Why he does it**: Demonstrates updating profile image metadata and verifying that the model's `image_path` property correctly renders the updated avatar image on the frontend.
- **Result**: User `1`'s profile picture updates from `default.jpeg` to `Corey.png`, rendering the new avatar on the frontend web view.

---

## 4. Code Examples

### Full `schemas.py`

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

# User Base Schemas
class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: EmailStr = Field(max_length=120)

class UserCreate(UserBase):
    pass

class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=50)
    email: EmailStr | None = Field(default=None, max_length=120)
    image_file: str | None = Field(default=None, min_length=1, max_length=200)

class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    image_file: str | None
    image_path: str

# Post Base Schemas
class PostBase(BaseModel):
    title: str
    content: str

class PostCreate(PostBase):
    user_id: int

class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    content: str | None = Field(default=None, min_length=1)

class PostResponse(PostBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    date_posted: datetime
    author: UserResponse
```

### Cascade Delete Configuration in `models.py`

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

    # Relationship configured with cascade deletion
    posts: Mapped[list[Post]] = relationship(
        back_populates="author",
        cascade="all, delete-orphan"
    )

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

### Complete CRUD Endpoints in `main.py`

```python
# Full Update Post (PUT)
@app.put("/api/posts/{post_id}", response_model=schemas.PostResponse)
def update_post_full(
    post_id: int,
    post_data: schemas.PostCreate,
    db: Annotated[Session, Depends(get_db)]
):
    post = db.execute(select(models.Post).where(models.Post.id == post_id)).scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if post_data.user_id != post.user_id:
        user = db.execute(select(models.User).where(models.User.id == post_data.user_id)).scalars().first()
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

    post.title = post_data.title
    post.content = post_data.content
    post.user_id = post_data.user_id

    db.commit()
    db.refresh(post)
    return post

# Partial Update Post (PATCH)
@app.patch("/api/posts/{post_id}", response_model=schemas.PostResponse)
def update_post_partial(
    post_id: int,
    post_data: schemas.PostUpdate,
    db: Annotated[Session, Depends(get_db)]
):
    post = db.execute(select(models.Post).where(models.Post.id == post_id)).scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    update_data = post_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(post, field, value)

    db.commit()
    db.refresh(post)
    return post

# Delete Post (DELETE)
@app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    post = db.execute(select(models.Post).where(models.Post.id == post_id)).scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    db.delete(post)
    db.commit()

# Delete User with Cascade (DELETE)
@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    user = db.execute(select(models.User).where(models.User.id == user_id)).scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    db.delete(user)
    db.commit()
```

---

## 5. FastAPI & Python Knowledge

- **`model_dump(exclude_unset=True)`**: A Pydantic v2 method that exports model fields into a Python dictionary, filtering out any field that was not explicitly set in the request JSON.
- **`setattr(obj, name, value)`**: A Python built-in function that dynamically sets an attribute on an object instance at runtime.
- **Python Optional Types (`str | None = None`)**: Modern Python 3.10+ syntax declaring a type that can be either a string or `None`, defaulting to `None` when omitted.
- **HTTP `204 No Content` Semantics**: Specifies that a request succeeded but carries no HTTP body. The handler must not attempt to return serialized JSON data.
- **`db.delete(instance)`**: A SQLAlchemy session method that marks an ORM instance for deletion in the current transaction, executing an SQL `DELETE` statement upon `db.commit()`.
- **SQLAlchemy `cascade="all, delete-orphan"`**: Instructs the ORM unit of work to automatically issue `DELETE` statements for child objects when a parent object is deleted or disassociated.
- **Dictionary Iteration (`.items()`)**: Standard Python method returning key-value tuples from a dictionary, enabling dynamic iteration over update payloads.

---

## 6. Tips & Important Details

- **Excluding `user_id` from Partial Post Updates**: Ownership changes should generally be disallowed in partial update schemas (`PostUpdate`) to prevent accidental resource reassignment. Ownership transfers are better handled via dedicated endpoints or `PUT` requests.
- **Pre-checking Foreign Key Constraints**: Validating that a new `user_id` exists in the database prior to applying a post update returns a clean HTTP 400 response rather than letting an uncaught database integrity exception crash the request.
- **Storing Filenames vs. Full File Paths**: Storing only image filenames (e.g., `"Corey.png"`) in database columns keeps data decoupled from directory layouts. The `@property` method (`image_path`) dynamically prepends folder locations (`/media/profile_pics/Corey.png`).
- **`model_dump(exclude_unset=True)` vs. Explicit Null Checks**: Use `exclude_unset=True` with `setattr()` for models with many attributes. Manual `if field is not None` checks are acceptable for smaller models with few fields.
- **Warning on Cascade Deletion Safety**: Cascade deletions are powerful and irreversible. Production applications should require explicit user confirmation before executing account deletions.

---

## 7. Errors & Pitfalls

- **Overwriting Omitted Fields with `None` during PATCH Requests**: Calling standard `model_dump()` without `exclude_unset=True` includes unset default fields (`field=None`), overwriting existing database fields with `None`.
- **Bypassing Foreign Key Checks on Ownership Changes**: Changing `user_id` on a post to a non-existent user ID causes database foreign key constraint failures.
- **Allowing Duplicate Usernames or Emails on User Updates**: Failing to check whether a requested new username or email is already taken by another account causes unique constraint database crashes.
- **Returning Data on `204 No Content` Routes**: Returning an object from a route configured with `status_code=status.HTTP_204_NO_CONTENT` violates HTTP protocols.
- **Orphaned Rows from Missing Cascade Settings**: Deleting a parent user without setting up `cascade="all, delete-orphan"` leaves unreferenced child rows or causes foreign key violations.

---

## 8. Best Practices & Trade-offs

- **`PUT` vs. `PATCH` Preference**: `PUT` guarantees complete resource replacement, but `PATCH` is usually preferable in APIs because it allows clients to modify selective fields without transmitting full objects.
- **Dynamic `setattr()` Iteration vs. Manual Field Checking**:
  - `setattr()` + `exclude_unset=True`: Scalable, reduces boilerplate code, and handles large schemas cleanly.
  - Manual `if field is not None` checks: Offers fine-grained control for extra field-level validations (e.g., uniqueness checks) on smaller models.
- **Preventing Account Deletion vs. Cascade Deletion**:
  - Preventing deletion: Prevents accidental data loss by blocking account deletion if child records exist.
  - Cascade deletion (`cascade="all, delete-orphan"`): Provides cleaner user account teardowns matching real-world applications, provided warning steps exist.
- **Storing Filenames vs. Absolute Paths**: Storing simple filenames in database columns enables easy file relocation or cloud storage migrations without modifying database records.

---

## 9. Resources

- **GitHub Source Code Repository**: Companion code repository for Part 6 linked in the video description.
- **FastAPI Official Documentation**: Reference guide for path parameters, status codes, and response handling.
- **Pydantic v2 Documentation**: Reference for `BaseModel`, `Field`, and `model_dump(exclude_unset=True)`.
- **SQLAlchemy ORM Documentation**: Reference for `relationship()`, `cascade`, and `db.delete()`.
- **Interactive API Documentation Routes**:
  - Swagger UI: `http://localhost:8000/docs`
  - ReDoc: `http://localhost:8000/redoc`

---

## 10. Key Takeaways

1. `PUT` represents full resource replacement; `PATCH` represents partial update.
2. `PATCH` is generally more flexible and useful in REST APIs than `PUT`.
3. Optional schema fields are defined using `str | None = Field(default=None, ...)`.
4. `model_dump(exclude_unset=True)` extracts only fields explicitly sent in a request.
5. `setattr(obj, field, value)` dynamically assigns attributes during dictionary iteration.
6. Exclude ownership fields (`user_id`) from partial update schemas to prevent unauthorized reassignments.
7. HTTP `DELETE` routes return `204 No Content` without a response body.
8. Check that new foreign key IDs exist before committing record updates.
9. Check username and email uniqueness when updating user profiles.
10. Standard HTTP status codes (`200`, `201`, `204`, `400`, `404`, `422`) establish clear API contracts.
11. `cascade="all, delete-orphan"` automatically deletes dependent child records when a parent record is removed.
12. `delete-orphan` cleans up disassociated child objects automatically.
13. Store filenames rather than full storage paths in database columns.
14. Use ORM `@property` getters (`image_path`) to generate dynamic asset URLs for frontends.
15. Cascade account deletion mirrors real-world production account removal workflows.

---

## 11. Quick Reference

### Command Line

```bash
# Launch server in development mode with auto-reload
fastapi dev
```

### Essential Imports

```python
from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session, Mapped, mapped_column, relationship
```

### Partial Update Pattern (`PATCH`)

```python
@app.patch("/api/posts/{post_id}", response_model=schemas.PostResponse)
def update_post_partial(
    post_id: int,
    post_data: schemas.PostUpdate,
    db: Annotated[Session, Depends(get_db)]
):
    post = db.execute(select(models.Post).where(models.Post.id == post_id)).scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    update_data = post_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(post, field, value)

    db.commit()
    db.refresh(post)
    return post
```

### Deletion Pattern (`DELETE`)

```python
@app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    post = db.execute(select(models.Post).where(models.Post.id == post_id)).scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    db.delete(post)
    db.commit()
```

### Cascade Relationship Pattern

```python
posts: Mapped[list[Post]] = relationship(
    back_populates="author",
    cascade="all, delete-orphan"
)
```

---

## 12. Mental Model

- **Complete CRUD Lifecycle Architecture**:
  1. **Schema Layer (`schemas.py`)**: Defines input/output data contracts. `PostCreate` requires all fields for `POST` and `PUT`; `PostUpdate` makes fields optional for `PATCH`.
  2. **Route Layer (`main.py`)**: Receives HTTP requests, validates payloads against Pydantic schemas, and injects a database session (`Depends(get_db)`).
  3. **Validation & Query Execution**: Verifies resource existence (raising 404 if missing) and checks foreign keys or unique constraints (raising 400 on violations).
  4. **State Mutation**:
     - **Full Update (`PUT`)**: Replaces all attributes directly on the ORM object.
     - **Partial Update (`PATCH`)**: Uses `model_dump(exclude_unset=True)` and `setattr()` to modify only client-provided fields.
     - **Deletion (`DELETE`)**: Passes the ORM instance to `db.delete(instance)`.
  5. **ORM Unit of Work & Cascade Execution**: `db.commit()` flushes SQL updates to SQLite/PostgreSQL. If a user is deleted, SQLAlchemy's `cascade="all, delete-orphan"` rule automatically issues `DELETE` statements for all associated posts.
  6. **Response Generation**: `PUT` and `PATCH` routes refresh and return the updated ORM object as JSON (`200 OK`); `DELETE` routes complete without a response body (`204 No Content`).

---

💡 _I have generated detailed developer study notes covering Part 6 of Corey Schafer's FastAPI series, completing the full CRUD operations across both Pydantic schemas and SQLAlchemy ORM models. Let me know if you would like to explore setting up async/await routes or reorganizing main.py with API Routers!_
