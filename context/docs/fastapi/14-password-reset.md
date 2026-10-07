# Python FastAPI Tutorial (Part 14): Password Reset - Email, Tokens, and Background Tasks

## 1. Overview

- **What this lesson teaches**: How to build a secure, asynchronous, end-to-end password reset and password change workflow in a FastAPI application. It covers asynchronous email delivery with `aio-smtp-lib`, non-blocking background task execution using FastAPI's `BackgroundTasks`, generating high-entropy URL-safe reset tokens, storing SHA-256 token hashes in a database table, preventing email enumeration attacks with HTTP 202 Accepted status codes, setting security response headers (`Referrer-Policy`), handling SQLite timezone quirks, and creating frontend HTML email templates, web reset pages, and authenticated password update forms.
- **Learning objectives**:
  - Understand why synchronous email sending (`smtplib`) blocks FastAPI's async event loop and how `aio-smtp-lib` resolves it.
  - Offload email delivery out of the HTTP request-response cycle using FastAPI's `BackgroundTasks`.
  - Securely configure SMTP settings using `pydantic-settings`, `SecretString`, and Mailtrap sandbox for development.
  - Generate cryptographically secure, single-use, URL-safe tokens with `secrets.token_urlsafe(32)` and store 64-character SHA-256 hashes in the database.
  - Mitigate email enumeration attacks by returning generic HTTP 202 Accepted responses regardless of whether an email exists in the database.
  - Mitigate Host Header Injection vulnerabilities by hardcoding `frontend_url` in application configuration settings.
  - Build three API endpoints: `POST /api/users/forgot-password`, `POST /api/users/reset-password`, and `PATCH /api/users/me/pass`.
  - Design HTML email templates with inline CSS and table-based layouts using Jinja2 rendering engines without `Request` objects.
  - Resolve SQLite naive datetime comparison errors using `.replace(tzinfo=timezone.utc)`.
- **Why the topic matters**: Password recovery is a mandatory feature for user management systems, but implementing it improperly introduces critical security vulnerabilities. Vulnerabilities include exposing whether specific emails exist in the system, allowing attackers to brute-force reset links, blocking the event loop while waiting for SMTP servers, leaking reset tokens via HTTP Referer headers, or allowing stolen tokens to be reused indefinitely.

---

## 2. Concepts

### Async Email Delivery (`aio-smtp-lib`) vs. Synchronous `smtplib`

- **What it is**: An asynchronous Python SMTP client library (`aio-smtp-lib`) built for `asyncio`.
- **Why it is needed**: Python's standard `smtplib` library is synchronous. Calling synchronous network IO functions inside FastAPI `async def` endpoints blocks the main event loop, freezing all concurrent incoming HTTP requests across the entire application while waiting for remote email server responses.
- **How it works**: Uses `await aiosmtplib.send()` to transmit email messages asynchronously, yielding control back to the event loop during network socket communication.
- **Important details**: Communicates over standard TLS/STARTTLS ports (such as port 587) using application configuration credentials.
- **Examples**: `await aiosmtplib.send(message, hostname=settings.mail_server, port=settings.mail_port, username=settings.mail_username, password=settings.mail_password.get_secret_value(), start_tls=settings.mail_use_tls)`

### FastAPI `BackgroundTasks`

- **What it is**: A built-in FastAPI dependency class (`from fastapi import BackgroundTasks`) that executes worker functions in the background _after_ the HTTP response has been sent to the client.
- **Why it is needed**: Network calls to external SMTP servers take time. Returning an HTTP response immediately while sending the email in the background ensures the user is not left waiting on a loading spinner.
- **How it works**: Declaring `background_tasks: BackgroundTasks` in an endpoint signature allows calling `background_tasks.add_task(func, *args, **kwargs)`. FastAPI finishes delivering the HTTP response payload to the browser and then invokes `func(*args, **kwargs)`.
- **Important details**:
  - `BackgroundTasks` executes in-memory on the server. If the application server crashes or restarts before the task completes, pending background tasks are lost.
  - For critical operations (such as payment processing), a dedicated task queue (like Celery with Redis) is preferred. For password reset emails, `BackgroundTasks` is appropriate because users can simply request a new reset link if an email fails to arrive.
  - Always pass simple primitive data types (such as strings or integers) to background tasks rather than active database sessions (`AsyncSession`), as database sessions are closed when the HTTP response completes.

### Secure Single-Use Tokens & Database Hashing (SHA-256 vs. Argon2)

- **What it is**: Generating unguessable Base64 token strings using `secrets.token_urlsafe(32)` and storing their 64-character SHA-256 hex digests in a database table (`PasswordResetToken`).
- **Why it is needed**:
  - **Why not JWTs?**: JSON Web Tokens cannot be invalidated before their expiration timestamp without maintaining a database blacklist, which defeats the stateless purpose of JWTs. Database-stored tokens provide true single-use enforcement (the database record is deleted upon reset) and allow instant invalidation of old tokens whenever a user requests a new one.
  - **Why SHA-256 instead of Argon2?**: User-created passwords can be short and weak, requiring a computationally expensive hashing algorithm like Argon2 to prevent brute-force attacks. In contrast, 32-byte `token_urlsafe` tokens contain 256 bits of entropy and are mathematically unguessable, making fast SHA-256 hashing secure. Storing SHA-256 hashes ensures that if the database is leaked, attackers gain only useless hashes rather than valid password reset links.
- **How it works**: The raw token is sent to the user in the email link (`https://example.com/reset-password?token=<raw_token>`). When the user submits a new password, the server hashes the incoming token with SHA-256 and looks up the matching hash in the database.

### Mitigating Email Enumeration (HTTP 202 Accepted)

- **What it is**: Returning an identical HTTP 202 Accepted response with a generic message regardless of whether the requested email exists in the database.
- **Why it is needed**: If an endpoint returns HTTP 404 ("Email not found") for unregistered emails and HTTP 200 ("Email sent") for registered emails, an attacker can automate queries against the endpoint to compile a list of registered user accounts (email enumeration attack).
- **How it works**: The endpoint executes database lookups silently. If the email exists, it schedules the background email task; if not, it skips email creation. In both cases, it returns: `HTTP 202 Accepted` with `{"detail": "If an account exists with this email, you will receive password reset instructions."}`.

### Hardcoded `frontend_url` vs. Request Header Building

- **What it is**: Constructing password reset links using a configured base URL (`settings.frontend_url`) rather than extracting host information from the incoming HTTP `Request` object.
- **Why it is needed**: Relying on incoming request headers (like `request.base_url` or `Host`) allows attackers to send forged `Host` or `X-Forwarded-Host` headers (Host Header Injection / Password Reset Poisoning). If built from request headers, the server could generate a reset link pointing to `https://attacker.com/reset-password?token=<valid_token>`, stealing the user's token when clicked.

### Security Response Headers (`Referrer-Policy: no-referrer`)

- **What it is**: Setting `Referrer-Policy: no-referrer` on response headers for reset password web pages.
- **Why it is needed**: Password reset URLs contain sensitive raw reset tokens as query parameters (`?token=...`). If a user on the reset page clicks an external outbound link (e.g., a link in a footer or header), the browser normally sends the full current page URL in the HTTP `Referer` header to the external site, exposing the valid reset token in external server logs.

---

## 3. Step-by-Step Tutorial

### Step 1: Installing Async SMTP Dependency

- **What he does**: Executes `uv add aio-smtp-lib` (or `pip install aio-smtp-lib`) in the terminal.
- **Why he does it**: Installs the asynchronous SMTP library required for non-blocking email delivery.
- **Relevant command**:
  ```bash
  uv add aio-smtp-lib
  ```
- **How the code works**: Adds `aio-smtp-lib` to the project's virtual environment dependencies. (Note: `email-validator` is already included via `fastapi[standard]`).
- **Result**: `aiosmtplib` is available for importing.

### Step 2: Configuring Email Settings (`config.py` & `.env`)

- **What he does**: Updates `Settings` in `config.py` to include email and token configuration fields, and adds corresponding variable definitions in `.env`.
- **Why he does it**: Centralizes email configuration and hides sensitive credentials like SMTP passwords inside `.env`.
- **Relevant code**:

  ```python
  # In config.py
  class Settings(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

      secret_key: SecretString
      algorithm: str = "HS256"
      access_token_expire_minutes: int = 30

      # Password Reset & Email Configuration
      reset_token_expire_minutes: int = 60
      mail_server: str = "sandbox.smtp.mailtrap.io"
      mail_port: int = 587
      mail_username: str = ""
      mail_password: SecretString = SecretString("")
      mail_from: str = "noreply@fastapiblog.com"
      mail_use_tls: bool = True
      frontend_url: str = "http://localhost:8000"
  ```

  ```ini
  # In .env
  MAIL_USERNAME=your_mailtrap_username
  MAIL_PASSWORD=your_mailtrap_password
  ```

- **How the code works**: Maps uppercase environment variables (`MAIL_USERNAME`, `MAIL_PASSWORD`) to settings attributes. `SecretString` masks the SMTP password from accidental logging. `frontend_url` hardcodes the trusted base URL for password reset links.
- **Result**: Email configuration is loaded and validated on application startup.

### Step 3: Setting Up Mailtrap Sandbox

- **What he does**: Creates a free account on Mailtrap, sets up an Email Sandbox inbox named `fastapi-blog`, and copies the generated SMTP username and password credentials into `.env`.
- **Why he does it**: Mailtrap captures outgoing test emails in a virtual inbox during development, preventing test emails from hitting real email addresses while testing HTML rendering and reset links safely.
- **Result**: Outgoing development emails are caught safely inside Mailtrap.

### Step 4: Creating Email Utility Functions (`email_utils.py`)

- **What he does**: Creates `email_utils.py` containing `send_email()` (a general async email dispatcher using `EmailMessage` and `aiosmtplib.send`) and `send_password_reset_email()` (a specialized helper that constructs reset links, renders Jinja2 templates, and calls `send_email`).
- **Why he does it**: Encapsulates email construction, MIME alternative formatting, Jinja2 template rendering, and SMTP sending into reusable utility functions.
- **Relevant code**:

  ```python
  from email.message import EmailMessage
  import aiosmtplib
  from fastapi.templating import Jinja2Templates

  from config import settings

  # Initialize Jinja2 templates for email rendering
  templates = Jinja2Templates(directory="templates")

  async def send_email(
      to_email: str,
      subject: str,
      body_text: str,
      body_html: str | None = None
  ) -> None:
      message = EmailMessage()
      message["From"] = settings.mail_from
      message["To"] = to_email
      message["Subject"] = subject
      message.set_content(body_text)

      if body_html:
          message.add_alternative(body_html, subtype="html")

      await aiosmtplib.send(
          message,
          hostname=settings.mail_server,
          port=settings.mail_port,
          username=settings.mail_username,
          password=settings.mail_password.get_secret_value(),
          start_tls=settings.mail_use_tls,
      )

  async def send_password_reset_email(
      to_email: str,
      username: str,
      token: str
  ) -> None:
      reset_url = f"{settings.frontend_url}/reset-password?token={token}"

      # Render HTML template without requiring a Request object
      template = templates.env.get_template("email/password_reset.html")
      body_html = template.render(
          reset_url=reset_url,
          username=username
      )

      body_text = (
          f"Hi {username},\n\n"
          f"You requested to reset your password. Please click the link below to reset it:\n"
          f"{reset_url}\n\n"
          f"This link will expire in {settings.reset_token_expire_minutes} minutes.\n\n"
          f"If you did not request this, please ignore this email."
      )

      await send_email(
          to_email=to_email,
          subject="Password Reset Request",
          body_text=body_text,
          body_html=body_html,
      )
  ```

- **How the code works**:
  - `EmailMessage`: Standard Python library for email construction. `set_content()` sets plain-text fallback; `add_alternative(..., subtype="html")` appends rich HTML.
  - `templates.env.get_template("email/password_reset.html").render(...)`: Accesses Jinja2's underlying environment to render a template into a raw string without needing a web `Request` object.
  - `settings.mail_password.get_secret_value()`: Unwraps the `SecretString` to pass the raw password string to `aiosmtplib.send()`.
- **Result**: Email sending utilities are defined and ready for background invocation.

### Step 5: Designing the HTML Email Template (`templates/email/password_reset.html`)

- **What he does**: Creates a subdirectory `templates/email/` and adds `password_reset.html`.
- **Why he does it**: HTML emails require special formatting conventions: inline CSS (style tags are often stripped by email clients), simple table-based layouts (for cross-client compatibility), and no JavaScript.
- **Relevant code**:
  ```html
  <!DOCTYPE html>
  <html>
    <head>
      <meta charset="utf-8" />
    </head>
    <body
      style="font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px;"
    >
      <table
        width="100%"
        cellpadding="0"
        cellspacing="0"
        style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 5px; overflow: hidden;"
      >
        <tr>
          <td
            style="padding: 20px; background-color: #007bff; color: #ffffff; text-align: center;"
          >
            <h1 style="margin: 0; font-size: 24px;">FastAPI Blog</h1>
          </td>
        </tr>
        <tr>
          <td style="padding: 30px;">
            <p style="font-size: 16px; color: #333333;">Hi {{ username }},</p>
            <p style="font-size: 16px; color: #333333;">
              You requested to reset your password. Click the button below to
              set a new password:
            </p>
            <table cellpadding="0" cellspacing="0" style="margin: 30px 0;">
              <tr>
                <td
                  align="center"
                  style="background-color: #007bff; border-radius: 5px;"
                >
                  <a
                    href="{{ reset_url }}"
                    style="display: inline-block; padding: 12px 25px; color: #ffffff; text-decoration: none; font-weight: bold;"
                    >Reset Password</a
                  >
                </td>
              </tr>
            </table>
            <p style="font-size: 14px; color: #666666;">
              This link will expire in 1 hour. If you did not request a password
              reset, please ignore this email.
            </p>
            <hr
              style="border: none; border-top: 1px solid #eeeeee; margin: 20px 0;"
            />
            <p style="font-size: 12px; color: #999999;">
              If the button above doesn't work, copy and paste this link into
              your browser:
            </p>
            <p style="font-size: 12px; color: #007bff; word-break: break-all;">
              {{ reset_url }}
            </p>
          </td>
        </tr>
      </table>
    </body>
  </html>
  ```
- **How the code works**: Uses inline CSS attributes and nested `<table>` elements to ensure consistent rendering across email clients (Gmail, Outlook, Apple Mail).
- **Result**: An HTML email template is ready for rendering.

### Step 6: Creating the `PasswordResetToken` Database Model (`models.py`)

- **What he does**: Opens `models.py` and adds the `PasswordResetToken` model class. Adds a `reset_tokens` relationship to `User` with cascading deletion.
- **Why he does it**: Establishes database storage for hashed reset tokens, user associations, and expiration timestamps.
- **Relevant code**:

  ```python
  class PasswordResetToken(Base):
      __tablename__ = "password_reset_tokens"

      id: Mapped[int] = mapped_column(primary_key=True)
      user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
      hash: Mapped[str] = mapped_column(String(64), nullable=False)
      expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          default=lambda: datetime.now(timezone.utc)
      )

      user: Mapped["User"] = relationship(back_populates="reset_tokens")

  # Inside class User(Base):
  reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
      back_populates="user",
      cascade="all, delete-orphan"
  )
  ```

- **How the code works**: `hash` stores the 64-character SHA-256 hex string. `expires_at` tracks expiration time. `cascade="all, delete-orphan"` on `User.reset_tokens` ensures that deleting a user account automatically cleans up associated reset tokens.
- **Result**: The ORM model for storing token hashes is defined.

### Step 7: Adding Token Utilities (`auth.py`)

- **What he does**: Adds `generate_reset_token()` and `hash_reset_token()` to `auth.py` using standard library modules `secrets` and `hashlib`.
- **Why he does it**: Provides secure functions for generating Base64 URL-safe random tokens and calculating SHA-256 hashes.
- **Relevant code**:

  ```python
  import hashlib
  import secrets

  def generate_reset_token() -> str:
      return secrets.token_urlsafe(32)

  def hash_reset_token(token: str) -> str:
      return hashlib.sha256(token.encode()).hexdigest()
  ```

- **How the code works**:
  - `secrets.token_urlsafe(32)` uses system entropy to return a random 43-character URL-safe string.
  - `hashlib.sha256(token.encode()).hexdigest()` returns a deterministic 64-character hexadecimal hash digest.
- **Result**: Cryptographic token generation and hashing utilities are created.

### Step 8: Creating Request Schemas (`schemas.py`)

- **What he does**: Adds `ForgotPasswordRequest`, `ResetPasswordRequest`, and `ChangePasswordRequest` Pydantic models to `schemas.py`.
- **Why he does it**: Validates input payloads for requesting resets, submitting new passwords with tokens, and changing passwords from authenticated account pages.
- **Relevant code**:

  ```python
  class ForgotPasswordRequest(BaseModel):
      email: EmailStr

  class ResetPasswordRequest(BaseModel):
      token: str
      new_password: str = Field(min_length=8)

  class ChangePasswordRequest(BaseModel):
      current_password: str
      new_password: str = Field(min_length=8)
  ```

- **Result**: Request validation schemas are ready for endpoint integration.

### Step 9: Implementing API Endpoints (`routers/users.py`)

- **What he does**: Adds three API endpoints to `routers/users.py`:
  1. `POST /api/users/forgot-password`
  2. `POST /api/users/reset-password`
  3. `PATCH /api/users/me/pass`
- **Why he does it**: Executes password reset requests, token validation/password resets, and authenticated password updates.
- **Relevant code**:

  ```python
  from datetime import datetime, timedelta, timezone
  from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
  from sqlalchemy import delete as sql_delete, func, select
  from sqlalchemy.ext.asyncio import AsyncSession

  from auth import (
      CurrentUser,
      generate_reset_token,
      hash_password,
      hash_reset_token,
      verify_password,
  )
  from config import settings
  from email_utils import send_password_reset_email
  import models
  import schemas

  router = APIRouter()

  # 1. Forgot Password Endpoint (Request Reset Link)
  @router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
  async def forgot_password(
      request_data: schemas.ForgotPasswordRequest,
      background_tasks: BackgroundTasks,
      db: Annotated[AsyncSession, Depends(get_db)],
  ):
      user = (
          await db.execute(
              select(models.User).where(func.lower(models.User.email) == request_data.email.lower())
          )
      ).scalars().first()

      if user:
          # Invalidate existing reset tokens for this user
          await db.execute(
              sql_delete(models.PasswordResetToken).where(models.PasswordResetToken.user_id == user.id)
          )

          # Generate new token, calculate hash, set expiration
          raw_token = generate_reset_token()
          token_hash = hash_reset_token(raw_token)
          expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.reset_token_expire_minutes)

          # Store hashed token in database
          reset_token = models.PasswordResetToken(
              user_id=user.id,
              hash=token_hash,
              expires_at=expires_at,
          )
          db.add(reset_token)
          await db.commit()

          # Schedule email background task using unhashed token
          background_tasks.add_task(
              send_password_reset_email,
              to_email=user.email,
              username=user.username,
              token=raw_token,
          )

      # Always return 202 Accepted with generic message to prevent email enumeration
      return {
          "detail": "If an account exists with this email, you will receive password reset instructions."
      }

  # 2. Reset Password Endpoint (Submit Token + New Password)
  @router.post("/reset-password", status_code=status.HTTP_200_OK)
  async def reset_password(
      request_data: schemas.ResetPasswordRequest,
      db: Annotated[AsyncSession, Depends(get_db)],
  ):
      token_hash = hash_reset_token(request_data.token)

      token_record = (
          await db.execute(
              select(models.PasswordResetToken).where(models.PasswordResetToken.hash == token_hash)
          )
      ).scalars().first()

      if not token_record:
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="Invalid or expired reset token",
          )

      # SQLite Workaround: Re-add UTC timezone info stripped by SQLite
      expires_at = token_record.expires_at.replace(tzinfo=timezone.utc)
      if expires_at < datetime.now(timezone.utc):
          await db.delete(token_record)
          await db.commit()
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="Invalid or expired reset token",
          )

      user = (
          await db.execute(
              select(models.User).where(models.User.id == token_record.user_id)
          )
      ).scalars().first()

      if not user:
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="Invalid or expired reset token",
          )

      # Update user password
      user.password_hash = hash_password(request_data.new_password)

      # Invalidate ALL reset tokens for this user
      await db.execute(
          sql_delete(models.PasswordResetToken).where(models.PasswordResetToken.user_id == user.id)
      )
      await db.commit()

      return {"detail": "Password has been reset successfully. You can now log in with your new password."}

  # 3. Authenticated Change Password Endpoint
  @router.patch("/me/pass", status_code=status.HTTP_200_OK)
  async def change_password(
      request_data: schemas.ChangePasswordRequest,
      current_user: CurrentUser,
      db: Annotated[AsyncSession, Depends(get_db)],
  ):
      if not verify_password(request_data.current_password, current_user.password_hash):
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="Current password is incorrect",
          )

      current_user.password_hash = hash_password(request_data.new_password)

      # Invalidate any outstanding reset tokens for this user
      await db.execute(
          sql_delete(models.PasswordResetToken).where(models.PasswordResetToken.user_id == current_user.id)
      )
      await db.commit()

      return {"detail": "Password updated successfully."}
  ```

- **How the code works**:
  - `/forgot-password`: Deletes pre-existing user reset tokens, generates a raw token and hash, saves the hash to `password_reset_tokens`, schedules `send_password_reset_email` via `background_tasks.add_task(...)`, and returns HTTP 202 Accepted.
  - `/reset-password`: Hashes submitted token, fetches record, fixes SQLite naive timezone via `.replace(tzinfo=timezone.utc)`, verifies expiration, updates `user.password_hash`, deletes all user reset tokens, and returns success message.
  - `/me/pass`: Authenticated route using `CurrentUser`. Validates `current_password` via `verify_password()`, updates `password_hash`, and deletes outstanding reset tokens.
- **Result**: All password reset and password change API endpoints are operational.

### Step 10: Adding Frontend Web Routes (`main.py`)

- **What he does**: Adds `/forgot-password` and `/reset-password` template routes in `main.py`.
- **Why he does it**: Renders HTML pages for forgotten password requests and token resets, attaching `Referrer-Policy: no-referrer` to the reset password route.
- **Relevant code**:

  ```python
  @app.get("/forgot-password", include_in_schema=False, name="forgot_password")
  async def forgot_password_page(request: Request):
      return templates.TemplateResponse(
          request=request, name="forgot_password.html", context={"title": "Forgot Password"}
      )

  @app.get("/reset-password", include_in_schema=False, name="reset_password")
  async def reset_password_page(request: Request):
      response = templates.TemplateResponse(
          request=request, name="reset_password.html", context={"title": "Reset Password"}
      )
      # Security header: Prevents reset token from leaking in Referer headers on link clicks
      response.headers["Referrer-Policy"] = "no-referrer"
      return response
  ```

- **Result**: Web routes render frontend templates and enforce referrer security.

### Step 11: Creating Frontend Templates and Forms

- **What he does**: Creates `forgot_password.html` and `reset_password.html` in `templates/`, adds a "Forgot Password?" link to `login.html`, and replaces the placeholder password form in `account.html` with a working form and JavaScript handler targeting `PATCH /api/users/me/pass`.
- **Why he does it**: Provides interactive web interfaces for all password management flows.
- **Relevant code**:

  ```javascript
  // Key JavaScript in reset_password.html
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get("token");

  if (!token) {
    document.getElementById("errorMessage").textContent =
      "Invalid or missing reset token.";
    showModal("errorModal");
    document.getElementById("resetPasswordBtn").disabled = true;
  }

  document
    .getElementById("resetPasswordForm")
    ?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const newPassword = document.getElementById("newPassword").value;
      const confirmPassword = document.getElementById("confirmPassword").value;

      if (newPassword !== confirmPassword) {
        document.getElementById("errorMessage").textContent =
          "Passwords do not match.";
        showModal("errorModal");
        return;
      }

      const response = await fetch("/api/users/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: token, new_password: newPassword }),
      });

      if (response.ok) {
        window.location.href = "/login";
      } else {
        const errorData = await response.json();
        document.getElementById("errorMessage").textContent =
          getErrorMessage(errorData);
        showModal("errorModal");
      }
    });
  ```

- **Result**: Complete web interface for password reset and account password changes.

---

## 4. Code Examples

### Full Email Utilities Module (`email_utils.py`)

```python
from email.message import EmailMessage
import aiosmtplib
from fastapi.templating import Jinja2Templates

from config import settings

templates = Jinja2Templates(directory="templates")

async def send_email(
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None
) -> None:
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body_text)

    if body_html:
        message.add_alternative(body_html, subtype="html")

    await aiosmtplib.send(
        message,
        hostname=settings.mail_server,
        port=settings.mail_port,
        username=settings.mail_username,
        password=settings.mail_password.get_secret_value(),
        start_tls=settings.mail_use_tls,
    )

async def send_password_reset_email(
    to_email: str,
    username: str,
    token: str
) -> None:
    reset_url = f"{settings.frontend_url}/reset-password?token={token}"

    template = templates.env.get_template("email/password_reset.html")
    body_html = template.render(
        reset_url=reset_url,
        username=username
    )

    body_text = (
        f"Hi {username},\n\n"
        f"You requested to reset your password. Click the link below to reset it:\n"
        f"{reset_url}\n\n"
        f"This link will expire in {settings.reset_token_expire_minutes} minutes.\n\n"
        f"If you did not request this, please ignore this email."
    )

    await send_email(
        to_email=to_email,
        subject="Password Reset Request",
        body_text=body_text,
        body_html=body_html,
    )
```

### Password Reset Token Model (`models.py`)

```python
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="reset_tokens")
```

---

## 5. FastAPI & Python Knowledge

- **`aiosmtplib` vs. `smtplib`**: `aiosmtplib` is an asynchronous SMTP client for Python's `asyncio`. Standard `smtplib` blocks execution threads during network IO; using `aiosmtplib` keeps FastAPI's event loop non-blocking.
- **FastAPI `BackgroundTasks`**: Dependency class that schedules tasks to execute after an HTTP response is delivered to the client. Tasks run in-memory within the server process.
- **`templates.env.get_template().render()`**: Rendering Jinja2 templates via `templates.env.get_template("path.html").render(key=value)` returns raw HTML strings without requiring a FastAPI `Request` object (unlike `templates.TemplateResponse`).
- **`secrets.token_urlsafe(32)`**: Generates a random, URL-safe Base64 text string with 32 bytes of entropy from the operating system's cryptographic random source.
- **`hashlib.sha256(data).hexdigest()`**: Calculates a deterministic 256-bit hash, returning a 64-character hexadecimal string.
- **SQLite Naive Datetime Fix (`.replace(tzinfo=timezone.utc)`)**: SQLite stores `DATETIME` columns without timezone metadata. When reading `expires_at` back from SQLite, Python interprets it as a naive datetime object. Calling `.replace(tzinfo=timezone.utc)` explicitly assigns UTC timezone information before comparing against `datetime.now(timezone.utc)`.

---

## 6. Tips & Important Details

- **Hardcode `frontend_url`**: Always configure static frontend domain URLs in settings to prevent Host Header Injection attacks.
- **Pass Primitives to Background Tasks**: Pass strings or integers (unhashed token, email, username) to `BackgroundTasks`, never database session objects (`AsyncSession`), as database sessions are closed when the HTTP response completes.
- **Delete Previous Tokens on Request**: Delete any existing reset tokens for a user before creating a new one, ensuring only one valid reset token exists per user at a time.
- **Single-Use Token Enforcement**: Delete all outstanding reset tokens for a user upon successful password reset or password change.
- **Self-Operation Route Convention (`/me/pass`)**: Use `PATCH /api/users/me/pass` for logged-in password changes to eliminate the need for user ID parameters or extra authorization checks.
- **Require Manual Login After Reset**: Best practice requires users to manually log in with their new password after a reset rather than auto-issuing a JWT access token, reducing security complexity.
- **Testing Token Expiration**: To test token expiration quickly, temporarily set `RESET_TOKEN_EXPIRE_MINUTES=1` in `.env`, wait 60 seconds, and submit the token.

---

## 7. Errors & Pitfalls

- **Email Enumeration Vulnerability**: Returning different HTTP status codes or message bodies depending on whether an email exists allows attackers to compile lists of registered users. Always return generic HTTP 202 Accepted responses.
- **Host Header Injection / Poison Links**: Building reset links using incoming request headers allows attackers to spoof `Host` headers and capture reset tokens on rogue servers.
- **Blocking the Event Loop with `smtplib`**: Using Python's built-in synchronous `smtplib` inside `async def` endpoints blocks all concurrent incoming requests during email transmission.
- **Stale Token Reuse**: Failing to delete reset tokens after a password change allows attackers to reuse intercepted token links.
- **Passing Database Sessions to `BackgroundTasks`**: Passing active `AsyncSession` instances to background tasks causes closed session errors because FastAPI closes session dependencies when the HTTP response completes.
- **Token Exposure in `Referer` Headers**: Clicking external links on a reset password page can send the token URL in `Referer` headers. Set `Referrer-Policy: no-referrer` on the response.
- **SQLite Naive Datetime Comparison Error**: Comparing SQLite naive datetimes against aware `datetime.now(timezone.utc)` triggers Python TypeError exceptions. Fix with `.replace(tzinfo=timezone.utc)`.

---

## 8. Best Practices & Trade-offs

- **SHA-256 vs. Argon2 for Reset Tokens**:
  - _Best Practice_: Use SHA-256 for random, high-entropy tokens (fast and mathematically unguessable). Use Argon2 for user-chosen passwords (slow to prevent brute-force attacks).
- **Database-Stored Single-Use Tokens vs. JWTs**:
  - _Best Practice_: Database-stored tokens allow true single-use enforcement and instant invalidation. Stateless JWTs cannot be revoked without maintaining a database blacklist.
- **`BackgroundTasks` vs. Celery/Redis**:
  - _Trade-off_: `BackgroundTasks` is built into FastAPI, lightweight, and requires no extra infrastructure (ideal for password reset emails). Celery with Redis provides persistent queues across server restarts (ideal for critical tasks).
- **Self-Service Password Changes (`PATCH /api/users/me/pass`)**:
  - _Best Practice_: Require verification of `current_password` before allowing password updates to prevent unauthorized changes if an active session is left unattended.

---

## 9. Resources

- **GitHub Source Code Repository**: Companion code repository for Part 14 linked in the video description.
- **FastAPI Background Tasks Documentation**: Official guide for executing non-blocking background tasks.
- **`aio-smtp-lib` Documentation**: Official reference for asynchronous SMTP client operations.
- **Mailtrap Email Sandbox**: Cloud-based email testing sandbox for developers.

---

## 10. Key Takeaways

1. Use `aio-smtp-lib` for non-blocking asynchronous email transmission in FastAPI.
2. Use `BackgroundTasks` to offload email delivery out of the HTTP request-response cycle.
3. Store SMTP secrets securely using `pydantic-settings` and `SecretString`.
4. Hardcode `frontend_url` in settings to prevent Host Header Injection attacks.
5. Generate unguessable reset tokens using `secrets.token_urlsafe(32)`.
6. Hash reset tokens with SHA-256 (`hashlib.sha256`) before storing them in the database.
7. Return generic HTTP 202 Accepted responses to prevent email enumeration attacks.
8. Delete existing reset tokens when generating a new token or completing a password change.
9. Render HTML emails using Jinja2 templates via `templates.env.get_template().render()`.
10. Use inline CSS and table-based layouts in HTML email templates for cross-client compatibility.
11. Fix SQLite naive datetime comparison errors using `.replace(tzinfo=timezone.utc)`.
12. Use `Referrer-Policy: no-referrer` headers on reset password pages to protect tokens.
13. Require current password verification on authenticated password change routes (`PATCH /api/users/me/pass`).
14. Require manual user login after completing a password reset flow.
15. Pass simple primitive data types (strings, ints) to `BackgroundTasks`, never database sessions.

---

## 11. Quick Reference

### Command Line

```bash
# Install async SMTP library
uv add aio-smtp-lib
```

### Essential Imports

```python
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import aiosmtplib
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
```

### Scheduling Background Email Task

```python
@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    request_data: schemas.ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    # Lookup user, generate token, save token hash to DB...
    background_tasks.add_task(
        send_password_reset_email,
        to_email=user.email,
        username=user.username,
        token=raw_token
    )
    return {"detail": "If an account exists with this email, you will receive password reset instructions."}
```

### SQLite Timezone Fix

```python
# Re-add UTC timezone stripped by SQLite storage
expires_at = token_record.expires_at.replace(tzinfo=timezone.utc)
if expires_at < datetime.now(timezone.utc):
    raise HTTPException(status_code=400, detail="Invalid or expired reset token")
```

---

## 12. Mental Model

- **Password Reset Architecture & Data Flow**:
  1. **User Request (`POST /api/users/forgot-password`)**: Client submits email \\(\rightarrow\\) Server performs case-insensitive database lookup.
  2. **Token Generation & DB Storage**: Server deletes old reset tokens for user \\(\rightarrow\\) Generates `raw_token` via `secrets.token_urlsafe(32)` \\(\rightarrow\\) Hashes token via `hashlib.sha256()` \\(\rightarrow\\) Saves `token_hash` and `expires_at` to `password_reset_tokens` table.
  3. **Background Email Task Scheduling**: Server schedules `send_password_reset_email(to_email, username, raw_token)` via `background_tasks.add_task()` \\(\rightarrow\\) Server immediately returns `HTTP 202 Accepted` with generic response.
  4. **Async Email Delivery**: Background worker renders `email/password_reset.html` using Jinja2 \\(\rightarrow\\) `aiosmtplib.send()` delivers email to Mailtrap sandbox asynchronously.
  5. **User Reset Link Interaction (`GET /reset-password?token=<raw_token>`)**: User clicks email button \\(\rightarrow\\) Browser lands on reset page \\(\rightarrow\\) Response sets `Referrer-Policy: no-referrer`.
  6. **Password Submission (`POST /api/users/reset-password`)**: JS extracts `token` from URL query params \\(\rightarrow\\) Submits `token` and `new_password` \\(\rightarrow\\) Server hashes incoming token with SHA-256 \\(\rightarrow\\) Fetches database record by hash \\(\rightarrow\\) Verifies `expires_at` \\(\rightarrow\\) Updates `user.password_hash` \\(\rightarrow\\) Deletes all user reset tokens \\(\rightarrow\\) Returns HTTP 200 success.
  7. **User Login**: User navigates to `/login` and authenticates using their new password.

---

💡 _I have generated detailed developer study notes covering Part 14 of Corey Schafer's FastAPI series on Password Reset with Email, Tokens, and Background Tasks. All notes follow clean Markdown formatting without citation brackets, exactly as requested!_
