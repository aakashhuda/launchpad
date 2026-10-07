# Python FastAPI Tutorial (Part 10): Authentication - Registration and Login with JWT

## 1. Overview

- **What this lesson teaches**: This lesson demonstrates how to build the backend authentication infrastructure and frontend authentication forms for a FastAPI application. It covers installing modern Python security libraries (`pwdlib` with `argon2` and `pyjwt`), centralizing application configuration using `pydantic-settings`, adding password hashing to database models, splitting user response schemas for data privacy, generating and verifying JSON Web Tokens (JWT), building registration and login endpoints, adding a `/api/users/me` route to fetch the authenticated user, wire up client-side JavaScript for `localStorage` token management, and creating an auth-aware navigation bar.
- **Learning objectives**:
  - Distinguish between **authentication** ("who are you?") and **authorization** ("what are you allowed to do?").
  - Implement password hashing using `pwdlib` with Argon2 as a modern, GPU-crack-resistant alternative to bcrypt.
  - Manage sensitive secrets and environment variables using `pydantic-settings` and `SecretString`.
  - Refactor Pydantic schemas to separate public user data (`UserPublic`) from private user data (`UserPrivate`) to avoid exposing user email addresses in public feeds.
  - Construct and sign JSON Web Tokens (JWT) using `pyjwt` with explicit expiration times.
  - Implement an OAuth2-compliant login endpoint (`/api/users/token`) using `OAuth2PasswordRequestForm`.
  - Implement a current user validation endpoint (`/api/users/me`) using `OAuth2PasswordBearer`.
  - Enable Swagger UI's global **Authorize** button for testing protected endpoints directly in `/docs`.
  - Store JWT access tokens in browser `localStorage` and build a client-side state manager (`auth.js`) with request caching.
- **Why the topic matters**: Storing plain-text passwords or leaving routes unprotected exposes applications to complete data compromise. Implementing strong password hashing (Argon2), centralized secret validation, signed JWT tokens, and strict privacy schemas creates an industry-standard security baseline. Separating authentication (identity verification) from authorization (permission checks) establishes a scalable security layer that works seamlessly across web browsers, mobile apps, and third-party API clients.

---

## 2. Concepts

### Authentication vs. Authorization

- **What it is**: The two distinct pillars of application security:
  - **Authentication**: Verifying the identity of a user or client ("Who are you?").
  - **Authorization**: Determining the permissions and resource access rights of an authenticated user ("What are you allowed to do?").
- **Why it is needed**: Applications must identify who is making a request before deciding whether that user has permission to view, edit, or delete a specific resource.
- **How it works**: Authentication validates credentials (email/password) and issues an identity token (JWT). Authorization inspects that token on subsequent requests to enforce ownership or role checks.
- **Important details**: This lesson focuses entirely on authentication (registration, login, password hashing, and token issuance). Authorization (protecting routes and replacing hardcoded `user_id = 1` scaffolding) is covered in Part 11.

### Password Hashing with Argon2 & `pwdlib`

- **What it is**: Transforming plain-text passwords into fixed-length, cryptographically secure hash strings using `pwdlib` initialized with the `argon2` algorithm extra.
- **Why it is needed**: Databases must **never** store plain-text passwords. If a database is leaked or stolen, irreversible hashes prevent attackers from recovering raw user passwords. Argon2 is the modern industry best practice because it is highly resistant to GPU-based cracking attacks compared to older algorithms like bcrypt.
- **How it works**: Argon2 incorporates a unique, randomly generated salt into every hash calculation. As a result, hashing the exact same password multiple times produces completely different hash strings every time, rendering precomputed rainbow table attacks useless.
- **Important details**: `PasswordHash.recommended()` provides secure default memory and iteration parameters without requiring manual cryptographic configuration.
- **Examples**: Hashing `"testpassword1!"` outputs an Argon2 string like `$argon2id$v=19$m=65536,t=3,p=4$...`.

### Secret Management with `pydantic-settings` & `SecretString`

- **What it is**: A settings management package (`pydantic-settings`) that loads environment variables into typed Python objects from system environments or `.env` files.
- **Why it is needed**: Centralizes configuration, validates data types automatically, fails fast on startup if required secrets are missing, and prevents accidental secret exposure.
- **How it works**: Subclassing `BaseSettings` defines typed configuration attributes. Wrapping sensitive string fields in `SecretString` masks their values (rendering `SecretString('**********')`) if printed or logged. The underlying raw string is retrieved explicitly using `.get_secret_value()`.
- **Important details**: Attribute names map case-insensitively to environment variable names (e.g., `secret_key` reads `SECRET_KEY` from `.env`). Priority order: system environment variables override `.env` file values, which override class default values.

### JSON Web Tokens (JWT) & `PyJWT`

- **What it is**: An open, compact standard (RFC 7519) for securely transmitting claims between parties as a JSON object signed with a secret key.
- **Why it is needed**: Provides stateless authentication. The server signs the token upon login; subsequent requests transmit the token in the HTTP header, allowing the server to verify the user's identity without querying session tables in a database on every request.
- **How it works**: A JWT consists of three Base64URL-encoded parts separated by dots (`header.payload.signature`):
  1. **Header**: Specifies the token type and signing algorithm (e.g., `HS256`).
  2. **Payload**: Contains claims such as subject (`sub`: user ID) and expiration timestamp (`exp`).
  3. **Signature**: Formed by hashing the encoded header, payload, and server secret key. If a client tampers with the payload, the signature verification fails.
- **Important details**: `PyJWT` is the library recommended in current FastAPI documentation due to its clean, focused API.

### OAuth2 Password Flow & `OAuth2PasswordRequestForm`

- **What it is**: A standard OAuth2 authentication specification flow where clients submit credentials to a token endpoint to receive an access token.
- **Why it is needed**: Establishes a standardized form payload structure for client logins and enables automatic integration with FastAPI's OpenAPI documentation (`/docs`).
- **How it works**: FastAPI provides `OAuth2PasswordRequestForm` as a dependency class that automatically parses incoming `application/x-www-form-urlencoded` form data containing `username` and `password` fields.
- **Important details**: The OAuth2 spec strictly names the credential field `username`. In applications that use email for login, the form's `username` field carries the user's email address.

### Client-Side Token Storage in `localStorage`

- **What it is**: Saving the received JWT access token in the browser's `window.localStorage` under the key `'access_token'`.
- **Why it is needed**: Persists the user's authentication state across browser tabs and page reloads.
- **How it works**: Upon a successful login response, JavaScript executes `localStorage.setItem('access_token', data.access_token)`. Subsequent API requests attach this token to the request headers as `Authorization: Bearer <token>`.
- **Important details**: `localStorage` is accessible across all client types (web, mobile, CLI tools). However, it is vulnerable to Cross-Site Scripting (XSS) attacks. Limiting token expiration times (e.g., 30 minutes) reduces security exposure.

### User Privacy & Schema Splitting (`UserPublic` vs. `UserPrivate`)

- **What it is**: Replacing a single `UserResponse` schema with two distinct Pydantic schemas: `UserPublic` and `UserPrivate`.
- **Why it is needed**: Exposing a user's email address in public API responses (such as blog post author details) is a severe privacy flaw.
- **How it works**:
  - `UserPublic`: Contains only non-sensitive author fields (`id`, `username`, `image_file`, `image_path`). Used when rendering public blog feeds or public user profiles.
  - `UserPrivate`: Inherits from `UserPublic` and adds private fields (`email`). Used exclusively when returning data to the authenticated user themselves (e.g., upon registration, account update, or `/api/users/me`).

---

## 3. Step-by-Step Tutorial

### Step 1: Installing Required Dependencies

- **What he does**: Installs three security and configuration packages using `uv add` (or `pip install`): `pwdlib[argon2]`, `pyjwt`, and `pydantic-settings`.
- **Why he does it**: `pwdlib[argon2]` provides password hashing; `pyjwt` handles JWT encoding and decoding; `pydantic-settings` handles configuration loading and validation.
- **Relevant code**:
  ```bash
  uv add "pwdlib[argon2]" pyjwt pydantic-settings
  ```
- **How the code works**: Downloads and registers the packages in the local virtual environment. Brackets around `argon2` specify the Argon2 backend extra for `pwdlib`.
- **Result**: Cryptographic hashing, token manipulation, and settings validation libraries are ready for application import.

### Step 2: Resetting the Development Database

- **What he does**: Deletes the existing SQLite database file (`blog.db`) from the project directory.
- **Why he does it**: Adding a non-nullable column (`password_hash`) to an existing SQLite table in development causes schema conflicts. Deleting `blog.db` allows SQLAlchemy to recreate clean tables on application startup.
- **Relevant code**:
  ```bash
  rm blog.db
  ```
- **How the code works**: Wipes out old test records so new model definitions take effect immediately. In production environments, schema changes are handled via Alembic database migrations.
- **Result**: The local SQLite database file is removed.

### Step 3: Updating the Database Model (`models.py`)

- **What he does**: Opens `models.py` and adds a non-nullable `password_hash` column to the `User` ORM class.
- **Why he does it**: Establishes persistent storage for password hashes.
- **Relevant code**:

  ```python
  class User(Base):
      __tablename__ = "users"

      id: Mapped[int] = mapped_column(primary_key=True)
      username: Mapped[str] = mapped_column(unique=True, nullable=False)
      email: Mapped[str] = mapped_column(unique=True, nullable=False)
      password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
      image_file: Mapped[str | None] = mapped_column(default=None)
      ...
  ```

- **How the code works**: Declares `password_hash` as a 200-character non-nullable string column, providing ample storage for long Argon2 hash strings.
- **Result**: The `User` database model is configured to store password hashes.

### Step 4: Refactoring Schemas for Privacy and Tokens (`schemas.py`)

- **What he does**: Modifies `schemas.py` to add `password` validation to `UserCreate`, replaces `UserResponse` with `UserPublic` and `UserPrivate`, updates `PostResponse`, and adds a `Token` schema.
- **Why he does it**: Enforces minimum password lengths during registration, prevents user email leakage in public responses, and defines the JWT login response structure.
- **Relevant code**:

  ```python
  class UserCreate(UserBase):
      password: str = Field(min_length=8)

  class UserPublic(BaseModel):
      model_config = ConfigDict(from_attributes=True)

      id: int
      username: str
      image_file: str | None
      image_path: str

  class UserPrivate(UserPublic):
      email: EmailStr

  class Token(BaseModel):
      access_token: str
      token_type: str

  class PostResponse(PostBase):
      model_config = ConfigDict(from_attributes=True)

      id: int
      user_id: int
      date_posted: datetime
      author: UserPublic  # Privacy fix: Uses UserPublic instead of UserResponse
  ```

- **How the code works**:
  - `UserCreate` mandates an 8-character minimum password length.
  - `UserPublic` excludes `email`.
  - `UserPrivate` inherits from `UserPublic` and includes `email`.
  - `PostResponse.author` uses `UserPublic`, hiding post authors' email addresses from public feeds.
- **Result**: API response schemas guarantee user privacy and establish a standard token response layout.

### Step 5: Setting Up Centralized Configuration (`config.py`)

- **What he does**: Creates `config.py` defining a `Settings` class inheriting from `BaseSettings`.
- **Why he does it**: Manages environment variables cleanly with built-in type validation and automatic masking of secret keys.
- **Relevant code**:

  ```python
  from pydantic import SecretString
  from pydantic_settings import BaseSettings, SettingsConfigDict

  class Settings(BaseSettings):
      model_config = SettingsConfigDict(
          env_file=".env",
          env_file_encoding="utf-8"
      )

      secret_key: SecretString
      algorithm: str = "HS256"
      access_token_expire_minutes: int = 30

  settings = Settings()  # type: ignore[call-arg]
  ```

- **How the code works**:
  - `env_file=".env"` tells `pydantic-settings` to load values from a local `.env` file.
  - `secret_key: SecretString` enforces that `SECRET_KEY` must be provided (since no default value is assigned) and masks its value when printed.
  - `settings = Settings()` instantiates a global settings object available for application-wide import.
- **Result**: Application settings are loaded and validated on startup.

### Step 6: Generating Secret Keys & Creating `.env`

- **What he does**: Generates a 32-byte random hex key in the terminal and saves it inside a new `.env` file. Verifies `.env` is listed in `.gitignore`.
- **Why he does it**: JWT signatures require a strong secret key, which must never be committed to source control.
- **Relevant code**:
  ```bash
  # Generate secret key in terminal
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
  ```ini
  # Content of .env file
  SECRET_KEY=9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b
  ```
- **How the code works**: `secrets.token_hex(32)` outputs a cryptographically secure 64-character random string. `pydantic-settings` maps `SECRET_KEY` in `.env` to `settings.secret_key`.
- **Result**: The secret key is loaded securely into the application.

### Step 7: Creating Cryptographic & Token Utilities (`auth.py`)

- **What he does**: Creates `auth.py` containing password hashing helpers (`hash_password`, `verify_password`), OAuth2 schemes (`oauth2_scheme`), and JWT token utilities (`create_access_token`, `verify_access_token`).
- **Why he does it**: Centralizes authentication logic into reusable utility functions.
- **Relevant code**:

  ```python
  from datetime import datetime, timedelta, timezone
  import jwt
  from fastapi.security import OAuth2PasswordBearer
  from pwdlib import PasswordHash
  from config import settings

  password_hash = PasswordHash.recommended()
  oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/users/token")

  def hash_password(password: str) -> str:
      return password_hash.hash(password)

  def verify_password(plain_password: str, hashed_password: str) -> bool:
      return password_hash.verify(plain_password, hashed_password)

  def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
      to_encode = data.copy()
      expire = datetime.now(timezone.utc) + (
          expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
      )
      to_encode.update({"exp": expire})
      return jwt.encode(
          to_encode,
          settings.secret_key.get_secret_value(),
          algorithm=settings.algorithm
      )

  def verify_access_token(token: str) -> int | None:
      try:
          payload = jwt.decode(
              token,
              settings.secret_key.get_secret_value(),
              algorithms=[settings.algorithm]
          )
          user_id: str | None = payload.get("sub")
          if user_id is None:
              return None
          return int(user_id)
      except jwt.InvalidTokenError:
          return None
  ```

- **How the code works**:
  - `PasswordHash.recommended()` hashes and verifies passwords using Argon2.
  - `OAuth2PasswordBearer(tokenUrl="api/users/token")` configures Swagger UI's authorization behavior and extracts tokens from `Authorization: Bearer <token>` headers.
  - `create_access_token()` attaches an `exp` claim and encodes the payload into a signed JWT string using `settings.secret_key.get_secret_value()`.
  - `verify_access_token()` decodes the JWT string, extracts the `sub` claim (user ID), handles invalid or expired tokens gracefully, and returns an integer user ID or `None`.
- **Result**: Cryptographic operations and token handling functions are ready for use.

### Step 8: Updating User Routes & Adding Auth Endpoints (`routers/users.py`)

- **What he does**: Updates `create_user` to hash passwords and use case-insensitive checks; adds the login endpoint (`POST /api/users/token`) and current user endpoint (`GET /api/users/me`).
- **Why he does it**: Exposes endpoints for account registration, credential verification, token generation, and token validation.
- **Relevant code**:

  ```python
  from datetime import timedelta
  from typing import Annotated
  from fastapi import APIRouter, Depends, HTTPException, status
  from fastapi.security import OAuth2PasswordRequestForm
  from sqlalchemy import func, select
  from sqlalchemy.ext.asyncio import AsyncSession

  from database import get_db
  import models
  import schemas
  from auth import (
      create_access_token,
      hash_password,
      oauth2_scheme,
      verify_access_token,
      verify_password,
  )
  from config import settings

  router = APIRouter()

  # Registration Endpoint
  @router.post("", response_model=schemas.UserPrivate, status_code=status.HTTP_201_CREATED)
  async def create_user(user: schemas.UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
      existing_username = (
          await db.execute(select(models.User).where(func.lower(models.User.username) == user.username.lower()))
      ).scalars().first()
      if existing_username:
          raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

      existing_email = (
          await db.execute(select(models.User).where(func.lower(models.User.email) == user.email.lower()))
      ).scalars().first()
      if existing_email:
          raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

      hashed_pwd = hash_password(user.password)
      new_user = models.User(
          username=user.username,
          email=user.email.lower(),
          password_hash=hashed_pwd
      )
      db.add(new_user)
      await db.commit()
      await db.refresh(new_user)
      return new_user

  # Login Token Endpoint
  @router.post("/token", response_model=schemas.Token)
  async def login_for_access_token(
      form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
      db: Annotated[AsyncSession, Depends(get_db)],
  ):
      # OAuth2 form field 'username' is used to carry the user's email address
      user = (
          await db.execute(select(models.User).where(func.lower(models.User.email) == form_data.username.lower()))
      ).scalars().first()

      # Generic error response prevents account enumeration attacks
      if not user or not verify_password(form_data.password, user.password_hash):
          raise HTTPException(
              status_code=status.HTTP_401_UNAUTHORIZED,
              detail="Incorrect email or password",
              headers={"WWW-Authenticate": "Bearer"},
          )

      access_token = create_access_token(data={"sub": str(user.id)})
      return schemas.Token(access_token=access_token, token_type="bearer")

  # Current Authenticated User Endpoint (MUST be placed before /{user_id})
  @router.get("/me", response_model=schemas.UserPrivate)
  async def get_current_user(
      token: Annotated[str, Depends(oauth2_scheme)],
      db: Annotated[AsyncSession, Depends(get_db)],
  ):
      user_id = verify_access_token(token)
      if user_id is None:
          raise HTTPException(
              status_code=status.HTTP_401_UNAUTHORIZED,
              detail="Could not validate credentials",
              headers={"WWW-Authenticate": "Bearer"},
          )

      user = (
          await db.execute(select(models.User).where(models.User.id == user_id))
      ).scalars().first()
      if user is None:
          raise HTTPException(
              status_code=status.HTTP_401_UNAUTHORIZED,
              detail="User not found",
              headers={"WWW-Authenticate": "Bearer"},
          )

      return user
  ```

- **How the code works**:
  - `create_user`: Performs case-insensitive checks via `func.lower()`, hashes the password with `hash_password()`, stores the lowercased email, and returns `UserPrivate`.
  - `login_for_access_token`: Accepts `OAuth2PasswordRequestForm`. Matches `form_data.username` against user emails case-insensitively, verifies the password hash, and returns a signed JWT containing `sub=str(user.id)`.
  - `get_current_user`: Placed _before_ `/{user_id}` to prevent route matching collisions. Uses `oauth2_scheme` to extract the Bearer token, verifies it, queries the user by ID, and returns `UserPrivate`.
- **Result**: Backend authentication routes are live and fully testable.

### Step 9: Testing Auth API in Swagger UI (`/docs`)

- **What he does**: Launches the server (`uv run fastapi dev main.py`), opens `/docs`, registers a user, logs in via `/api/users/token`, copies the token, clicks the global **Authorize** button, inputs credentials, and tests `/api/users/me`.
- **Why he does it**: Validates that password hashing, token issuance, Swagger header authorization, and token decoding function correctly.
- **Result**: Swagger UI unlocks protected endpoints using the generated Bearer token.

### Step 10: Building HTML Frontend Forms (`login.html` & `register.html`)

- **What he does**: Adds `/login` and `/register` template routes in `main.py` (`include_in_schema=False`) and creates `register.html` and `login.html` in `templates/`.
- **Why he does it**: Provides user interfaces for account creation and login.
- **Relevant code**:

  ```html
  <!-- Key JS in register.html -->
  <script type="module">
    const registerForm = document.getElementById("registerForm");
    registerForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = new FormData(registerForm);
      const userData = Object.fromEntries(formData.entries());

      const response = await fetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(userData),
      });
      if (response.ok) {
        window.location.href = "/login";
      }
    });
  </script>
  ```

  ```html
  <!-- Key JS in login.html -->
  <script type="module">
    const loginForm = document.getElementById("loginForm");
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = new FormData(loginForm);

      // OAuth2PasswordRequestForm expects form-encoded data, NOT JSON
      const response = await fetch("/api/users/token", {
        method: "POST",
        body: formData,
      });
      if (response.ok) {
        const data = await response.json();
        localStorage.setItem("access_token", data.access_token);
        window.location.href = "/";
      }
    });
  </script>
  ```

- **How the code works**:
  - `register.html`: Client JS validates password matching, sends JSON to `POST /api/users`, and redirects to `/login` upon success.
  - `login.html`: Input field is labeled "Email" but named `username`. Sends `FormData` directly (URL-encoded form format required by `OAuth2PasswordRequestForm`), receives the token, stores it in `localStorage.setItem('access_token', ...)` and redirects to `/`.
- **Result**: Registration and login web forms operate against the backend API.

### Step 11: Implementing Client-Side Auth Module (`static/js/auth.js`)

- **What he does**: Creates `static/js/auth.js` to manage client-side authentication state, token caching, and logout logic.
- **Why he does it**: Centralizes user session checking, prevents duplicate network calls to `/api/users/me`, and handles token expiration cleanly.
- **Relevant code**:

  ```javascript
  let currentUser = null;
  let fetchPromise = null;

  export async function getCurrentUser() {
    if (currentUser) return currentUser;
    if (fetchPromise) return fetchPromise;

    const token = localStorage.getItem("access_token");
    if (!token) return null;

    fetchPromise = (async () => {
      try {
        const response = await fetch("/api/users/me", {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (response.ok) {
          currentUser = await response.json();
          return currentUser;
        } else {
          localStorage.removeItem("access_token");
          return null;
        }
      } catch (error) {
        return null;
      } finally {
        fetchPromise = null;
      }
    })();

    return fetchPromise;
  }

  export function logout() {
    localStorage.removeItem("access_token");
    currentUser = null;
    fetchPromise = null;
    window.location.href = "/";
  }
  ```

- **How the code works**:
  - Request Caching: If `currentUser` is already cached or a `fetchPromise` is currently in flight, `getCurrentUser()` returns the existing reference, preventing duplicate network calls when multiple UI elements request user state simultaneously.
  - If `/api/users/me` returns a 401 error (expired/invalid token), `localStorage.removeItem('access_token')` clears the stale token.
- **Result**: Client-side authentication state is handled cleanly across page reloads.

### Step 12: Updating the Global Navbar & Layout (`layout.html`)

- **What he does**: Modifies `templates/layout.html` to import `getCurrentUser` and `logout` from `auth.js`, dynamically toggling navigation bar elements based on login state.
- **Why he does it**: Displays user details, "New Post", and "Logout" buttons when logged in, or "Login" and "Register" links when logged out.
- **Relevant code**:

  ```html
  <!-- Right Navbar Section in layout.html -->
  <div id="loggedInNav" class="d-none align-items-center">
    <button
      type="button"
      class="btn btn-outline-light me-2"
      data-bs-toggle="modal"
      data-bs-target="#createPostModal"
    >
      New Post
    </button>
    <span id="userEmailDisplay" class="text-light me-3"></span>
    <button id="logoutBtn" class="btn btn-outline-warning btn-sm">
      Logout
    </button>
  </div>
  <div id="loggedOutNav" class="d-none align-items-center">
    <a class="nav-link" href="{{ url_for('login') }}">Login</a>
    <a class="nav-link" href="{{ url_for('register') }}">Register</a>
  </div>

  <script type="module">
    import {
      getCurrentUser,
      logout,
    } from "{{ url_for('static', path='js/auth.js') }}";

    async function updateAuthUI() {
      const user = await getCurrentUser();
      const loggedInNav = document.getElementById("loggedInNav");
      const loggedOutNav = document.getElementById("loggedOutNav");
      const userEmailDisplay = document.getElementById("userEmailDisplay");

      if (user) {
        userEmailDisplay.textContent = user.email;
        loggedInNav.classList.remove("d-none");
        loggedInNav.classList.add("d-flex");
        loggedOutNav.classList.add("d-none");
      } else {
        loggedOutNav.classList.remove("d-none");
        loggedOutNav.classList.add("d-flex");
        loggedInNav.classList.add("d-none");
      }
    }

    document.getElementById("logoutBtn")?.addEventListener("click", logout);
    updateAuthUI();
  </script>
  ```

- **How the code works**:
  - Uses Bootstrap utility classes (`d-none`, `d-flex`) to toggle navigation visibility cleanly without inline styles.
  - `updateAuthUI()` queries `getCurrentUser()` on page load, displaying the authenticated user's email address in the navbar.
- **Result**: The UI reflects authentication state dynamically across page transitions.

---

## 4. Code Examples

### Full Configuration Module (`config.py`)

```python
from pydantic import SecretString
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

    secret_key: SecretString
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

# Instantiated globally; loads from .env automatically
settings = Settings()  # type: ignore[call-arg]
```

### Full Cryptographic & Token Module (`auth.py`)

```python
from datetime import datetime, timedelta, timezone
import jwt
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from config import settings

# Initialize Argon2 password hasher and OAuth2 scheme
password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/users/token")

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode,
        settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm
    )

def verify_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm]
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            return None
        return int(user_id)
    except jwt.InvalidTokenError:
        return None
```

### Updated Privacy & Authentication Schemas (`schemas.py`)

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: EmailStr = Field(max_length=120)

class UserCreate(UserBase):
    password: str = Field(min_length=8)

class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    image_file: str | None
    image_path: str

class UserPrivate(UserPublic):
    email: EmailStr

class Token(BaseModel):
    access_token: str
    token_type: str

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
    author: UserPublic  # Prevents exposing post author email addresses
```

---

## 5. FastAPI & Python Knowledge

- **`SecretString` & `.get_secret_value()`**: Pydantic's `SecretString` type wraps sensitive configuration fields. Printing or logging a `SecretString` outputs `SecretString('**********')` to prevent credential leakage. Calling `.get_secret_value()` explicitly unwraps the underlying string when performing cryptographic operations.
- **`OAuth2PasswordBearer` & `tokenUrl`**: A FastAPI security utility that configures OpenAPI/Swagger UI header authorization mechanics. Setting `tokenUrl="api/users/token"` instructs Swagger UI where to submit login credentials when clicking the **Authorize** button.
- **`OAuth2PasswordRequestForm` Dependency**: A form dependency class that parses `application/x-www-form-urlencoded` payloads. Per the OAuth2 specification, incoming credential fields are named `username` and `password`.
- **Case-Insensitive Database Queries (`sqlalchemy.func.lower`)**: Wrapping ORM columns in `func.lower()` (e.g., `func.lower(models.User.email) == email.lower()`) enforces case-insensitive database matching, preventing duplicate registrations like `User@example.com` and `user@example.com`.
- **Executing Single-Line Commands via `python -c`**: Using `python -c "import secrets; print(secrets.token_hex(32))"` runs inline Python statements in the terminal without opening an interactive REPL session.
- **Client-Side Promise Caching**: Storing an active `fetchPromise` inside `static/js/auth.js` ensures that multiple concurrent calls to `getCurrentUser()` wait on the same network request rather than making duplicate API calls.

---

## 6. Tips & Important Details

- **`pwdlib[argon2]` over `bcrypt`**: Argon2 is the modern cryptographic recommendation for password hashing due to its higher resistance to GPU cracking attacks.
- **`pyjwt` Recommendation**: `pyjwt` is the library explicitly recommended in current FastAPI documentation due to its simple, focused API.
- **Preventing Account Enumeration Attacks**: Returning generic 401 error messages (`"Incorrect email or password"`) for both missing accounts and incorrect passwords prevents attackers from discovering registered user emails.
- **Normalizing Email Addresses**: Always store email addresses as lowercased strings (`user.email.lower()`) because email addresses are case-insensitive by specification. Preserving original display casing for `username` while lowercasing it during uniqueness checks provides a better user experience.
- **Swagger UI Authorize Integration**: Setting up `OAuth2PasswordBearer` automatically unlocks the global **Authorize** button in `/docs`, streamlining interactive endpoint testing.
- **Route Matching Order Warning**: Specific routes like `GET /api/users/me` **must** be defined before parameterized routes like `GET /api/users/{user_id}` in router modules to prevent path matching collisions.

---

## 7. Errors & Pitfalls

- **Storing Plain-Text Passwords**: Storing unhashed passwords in a database is a critical security violation.
- **Committing `.env` Secrets to Source Control**: Forgetting to add `.env` to `.gitignore` exposes secret keys, API credentials, and database passwords on public repositories.
- **Leaking Emails in Public Response Schemas**: Using a single response schema that includes email addresses across public blog post routes leaks user contact information.
- **Using JSON Body Payloads for `OAuth2PasswordRequestForm`**: Sending `application/json` payloads to an endpoint using `OAuth2PasswordRequestForm` causes HTTP 422 validation errors. The endpoint requires form-encoded data (`FormData`).
- **Path Collision Bug (`/me` vs. `/{user_id}`)**: Defining `GET /api/users/{user_id}` above `GET /api/users/me` causes FastAPI to treat `"me"` as an integer path parameter string, triggering validation errors.
- **Missing `.get_secret_value()` Call**: Passing a `SecretString` directly to `jwt.encode()` or `jwt.decode()` without calling `.get_secret_value()` causes cryptographic typing errors.

---

## 8. Best Practices & Trade-offs

- **`pydantic-settings` vs. `python-dotenv`**:
  - `pydantic-settings`: Provides central configuration, strict type checking, fast startup failure, and `SecretString` masking.
  - `python-dotenv`: Simple and lightweight, but lacks built-in schema validation and secret masking.
- **`localStorage` vs. `HTTPOnly` Cookies**:
  - `localStorage`: Works across all client types (web, mobile apps, desktop apps, CLI tools) and aligns with standard Bearer token header conventions. Trade-off: vulnerable to XSS attacks.
  - `HTTPOnly` Cookies: Protected against client-side XSS script reading, but restricted primarily to browser clients and subject to Cross-Site Request Forgery (CSRF) concerns.
- **Centralized Client Auth Caching**: Caching user state in `auth.js` prevents network request spamming when multiple UI components render on page load.

---

## 9. Resources

- **GitHub Source Code Repository**: Companion code repository for Part 10 linked in the video description.
- **FastAPI Official Security Documentation**: Official reference for OAuth2, `OAuth2PasswordBearer`, and JWT handling.
- **PyJWT Documentation**: Reference for `jwt.encode` and `jwt.decode` claim validation.
- **Argon2 / `pwdlib` Documentation**: Cryptographic specifications for Argon2 password hashing.

---

## 10. Key Takeaways

1. Authentication answers "Who are you?"; authorization answers "What are you allowed to do?".
2. Never store plain-text passwords; hash passwords using `pwdlib` with Argon2.
3. Argon2 uses random salts per hash, preventing precomputed rainbow table attacks.
4. Manage environment configuration using `pydantic-settings` and `SecretString`.
5. Use `python -c "import secrets; print(secrets.token_hex(32))"` to generate strong secret keys.
6. Always include `.env` in `.gitignore` to protect application secrets.
7. Separate public user schemas (`UserPublic`) from private schemas (`UserPrivate`) to protect user email addresses.
8. JSON Web Tokens (JWT) contain three parts: header, payload, and signature.
9. `OAuth2PasswordRequestForm` expects form-encoded data with `username` carrying the login credential.
10. Return generic 401 error messages (`"Incorrect email or password"`) to prevent account enumeration.
11. Define specific routes (`/api/users/me`) before path parameters (`/api/users/{user_id}`).
12. `OAuth2PasswordBearer(tokenUrl="...")` unlocks the global **Authorize** button in Swagger UI (`/docs`).
13. Store JWT access tokens in `localStorage` for multi-client API compatibility.
14. Short token expiration times (e.g., 30 minutes) limit security exposure.
15. Cache client-side user fetch promises (`auth.js`) to prevent duplicate network calls on page load.

---

## 11. Quick Reference

### Command Line

```bash
# Install security dependencies
uv add "pwdlib[argon2]" pyjwt pydantic-settings

# Generate secret key in terminal
python -c "import secrets; print(secrets.token_hex(32))"
```

### Essential Security Imports

```python
from pydantic import SecretString
from pydantic_settings import BaseSettings, SettingsConfigDict
from pwdlib import PasswordHash
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
```

### Password Hashing Pattern

```python
password_hash = PasswordHash.recommended()

hashed_pwd = password_hash.hash(plain_password)
is_valid = password_hash.verify(plain_password, hashed_pwd)
```

### JWT Encoding & Decoding Pattern

```python
# Encoding
token = jwt.encode(
    {"sub": str(user_id), "exp": expire_dt},
    settings.secret_key.get_secret_value(),
    algorithm="HS256"
)

# Decoding
payload = jwt.decode(
    token,
    settings.secret_key.get_secret_value(),
    algorithms=["HS256"]
)
```

---

## 12. Mental Model

- **Authentication Architecture & Data Flow**:
  1. **Registration (`POST /api/users`)**: Client submits user data \\(\rightarrow\\) `UserCreate` validates password length \\(\rightarrow\\) `hash_password()` hashes password with Argon2 \\(\rightarrow\\) User saved to database \\(\rightarrow\\) Returns `UserPrivate` (including email, omitting password).
  2. **Login (`POST /api/users/token`)**: Client submits `FormData` (`username` = email, `password`) \\(\rightarrow\\) Backend fetches user case-insensitively via `func.lower()` \\(\rightarrow\\) `verify_password()` compares plain password against stored hash \\(\rightarrow\\) If valid, `create_access_token()` encodes `sub=user_id` into signed JWT \\(\rightarrow\\) Returns `{ "access_token": "...", "token_type": "bearer" }`.
  3. **Token Storage**: Client receives token \\(\rightarrow\\) Stores in `localStorage.setItem('access_token', token)`.
  4. **Identity Verification (`GET /api/users/me`)**: Client sends `Authorization: Bearer <token>` header \\(\rightarrow\\) `oauth2_scheme` extracts token string \\(\rightarrow\\) `verify_access_token()` decodes JWT signature via `settings.secret_key` \\(\rightarrow\\) User fetched by ID \\(\rightarrow\\) Returns `UserPrivate` to populate frontend UI state.

---

💡 _I have generated detailed developer study notes covering Part 10 of Corey Schafer's FastAPI series on Registration and Login with JWT. The notes capture all concepts, tutorial steps, code structures, best practices, and security guidelines directly grounded in the source video. Let me know if you would like to move on to Part 11 to cover Authorization and route protection!_
