# Python FastAPI Tutorial (Part 11): Authorization - Protecting Routes and Verifying Current User

## 1. Overview

- **What this lesson teaches**: This lesson completes the security architecture of a FastAPI application by implementing server-side authorization and access control. It covers creating a reusable `get_current_user` dependency and `CurrentUser` type alias, eliminating user spoofing by removing client-supplied `user_id` fields from request schemas, enforcing resource ownership checks across update (`PUT`/`PATCH`) and deletion (`DELETE`) endpoints, distinguishing between HTTP 401 Unauthorized and HTTP 403 Forbidden status codes, attaching JWT Bearer tokens to frontend `fetch` requests, replacing temporary `user_id = 1` client scaffolding with real token identity, and building a user account page (`/account`) for profile management, logout, and cascading account deletion.
- **Learning objectives**:
  - Distinguish between **authentication** (verifying _who_ a user is) and **authorization** (verifying _what_ an authenticated user is permitted to do).
  - Build a reusable `get_current_user` dependency in `auth.py` that parses tokens, verifies claims, queries the database, and returns the authenticated `User` ORM instance.
  - Define a `CurrentUser` type alias using `Annotated` to create clean, expressive route signatures.
  - Refactor `PostCreate` schema to remove client-supplied `user_id` fields, deriving post authorship strictly from trusted, server-signed JWT tokens.
  - Enforce resource ownership checks (`if post.user_id != current_user.id: raise HTTPException(status_code=403, ...)`) across `PUT`, `PATCH`, and `DELETE` endpoints.
  - Refactor `GET /api/users/me` using the `CurrentUser` dependency to reduce endpoint logic from 30 lines down to 3 lines.
  - Differentiate between HTTP 401 Unauthorized (missing or invalid authentication credentials) and HTTP 403 Forbidden (authenticated user lacks permission for the requested resource).
  - Update client-side frontend scripts (`layout.html`, `post.html`, `auth.js`) to attach `Authorization: Bearer <token>` headers, handle 401/403 status codes, and toggle UI controls dynamically based on ownership.
  - Construct a user account route (`/account`) and template (`account.html`) providing profile updates, logout, and account deletion workflows.
- **Why the topic matters**: Authentication without authorization is incomplete security. Without server-side authorization checks, authenticated users can manipulate JSON request bodies or send requests to modify or delete resources belonging to other users. Enforcing server-side authorization guarantees data integrity, privacy, and true multi-user security across web browsers, mobile applications, and REST API clients.

---

## 2. Concepts

### Authentication vs. Authorization Recap

- **What it is**: The two foundational layers of application security:
  - **Authentication**: Verifying identity ("Who are you?"). Solved in Part 10 using credentials, password hashing, and JWT issuance.
  - **Authorization**: Enforcing permissions ("What are you allowed to do?"). Focus of Part 11.
- **Why it is needed**: Knowing _who_ a user is does not automatically restrict them from performing unauthorized actions. An application must verify whether an authenticated user owns or has permission to modify a specific database resource.
- **How it works**: Authentication validates credentials and issues a signed token. Authorization inspects the claims within that token on subsequent HTTP requests, looking up the authenticated user and checking their permissions against the target resource before executing requested mutations.
- **Important details**: Authorization must **always** be enforced on the server. Client-side checks (such as hiding buttons in HTML templates) exist purely for user experience (UX) convenience and do not constitute security.

### Reusable `get_current_user` Dependency & `CurrentUser` Type Alias

- **What it is**: A centralized FastAPI dependency function that extracts a Bearer token from the HTTP `Authorization` header, decodes and verifies the token, queries the database for the corresponding user, and returns the full `models.User` ORM instance.
- **Why it is needed**: Prevents duplicating token extraction, signature verification, error handling, and database lookup boilerplate across dozens of protected API routes.
- **How it works**: Combines `OAuth2PasswordBearer` (token extraction), `verify_access_token` (token validation), and `AsyncSession` (database lookup). If the token is missing, invalid, expired, or refers to a non-existent/deleted user, it immediately raises an HTTP 401 Unauthorized exception before the route handler function executes.
- **Important details**: Defining a type alias `CurrentUser = Annotated[models.User, Depends(get_current_user)]` simplifies handler parameter signatures across application routes.
- **Examples**: Declaring `current_user: CurrentUser` in a route signature automatically protects the endpoint and provides direct access to the authenticated user object.

### Eliminating Request Body Impersonation (`PostCreate` Refactoring)

- **What it is**: Removing the client-supplied `user_id` field from the `PostCreate` schema so that `PostCreate` contains only `title` and `content`.
- **Why it is needed**: When `user_id` is included in a request body schema, malicious clients can pass any arbitrary user ID (e.g., `{"title": "Test", "content": "Text", "user_id": 2}`) to create posts under another user's name.
- **How it works**: The client transmits only title and content. The server extracts the trusted user ID from the verified JWT token (`current_user.id`) and assigns it during ORM model instantiation (`models.Post(..., user_id=current_user.id)`).
- **Examples**: `new_post = models.Post(title=post.title, content=post.content, user_id=current_user.id)`.

### HTTP 401 Unauthorized vs. HTTP 403 Forbidden

- **What it is**: Two distinct HTTP error status codes with specific semantic meanings in REST APIs:
  - **HTTP 401 Unauthorized**: The request lacks valid authentication credentials (token is missing, invalid, tampered with, or expired).
  - **HTTP 403 Forbidden**: The request is authenticated with a valid token, but the authenticated user does not have permission to access or modify the requested resource.
- **Why it is needed**: Providing explicit status codes tells API clients and frontend scripts how to react appropriately.
- **How it works**:
  - On a `401 Unauthorized` response, frontend clients redirect the user to the `/login` page or clear stale tokens.
  - On a `403 Forbidden` response, frontend clients display a permission error modal ("You are not authorized to edit this post") while keeping the user logged in.
- **Examples**: `raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this post")`.

### Server-Side Security vs. Client-Side UX Guards (The `/account` Pattern)

- **What it is**: The architectural separation between client-side user experience guards and server-side security enforcement.
- **Why it is needed**: Web browsers store JWT access tokens in `localStorage`, which is accessible to client-side JavaScript but not automatically transmitted during standard HTML page navigation requests (`GET /account`).
- **How it works**:
  - **Client-side guard**: When a user navigates to `/account`, the browser requests the page without a Bearer header. Server-side rendering generates the static template shell. Client-side JavaScript checks `localStorage` on page load; if no token exists, it redirects the browser to `/login`.
  - **Server-side security**: When the account page script calls `PATCH /api/users/{id}` or `DELETE /api/users/{id}`, the request attaches the Bearer token. The API validates the token and enforces ownership checks on the server. If an attacker disables JavaScript or bypasses the frontend, the backend API still blocks unauthorized attempts with 401 or 403 status codes.

---

## 3. Step-by-Step Tutorial

### Step 1: Creating the Reusable `get_current_user` Dependency (`auth.py`)

- **What he does**: Opens `auth.py`, adds required imports (`Annotated`, `Depends`, `HTTPException`, `status`, `select`, `AsyncSession`, `get_db`, `models`), defines `get_current_user()`, and creates the `CurrentUser` type alias.
- **Why he does it**: Establishes a single, reusable dependency that handles token verification and user loading across all protected routes.
- **Relevant code**:

  ```python
  from typing import Annotated
  from fastapi import Depends, HTTPException, status
  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession

  from database import get_db
  import models

  # Reusable dependency that returns the authenticated User instance
  async def get_current_user(
      token: Annotated[str, Depends(oauth2_scheme)],
      db: Annotated[AsyncSession, Depends(get_db)],
  ) -> models.User:
      credentials_exception = HTTPException(
          status_code=status.HTTP_401_UNAUTHORIZED,
          detail="Could not validate credentials",
          headers={"WWW-Authenticate": "Bearer"},
      )

      user_id = verify_access_token(token)
      if user_id is None:
          raise credentials_exception

      user = (
          await db.execute(select(models.User).where(models.User.id == user_id))
      ).scalars().first()

      if user is None:
          raise credentials_exception

      return user

  # Type alias for clean route parameter signatures
  CurrentUser = Annotated[models.User, Depends(get_current_user)]
  ```

- **How the code works**:
  - `oauth2_scheme` extracts the Bearer token from the `Authorization` header.
  - `verify_access_token(token)` decodes the token and extracts the `sub` claim (user ID).
  - Queries the database for the matching `models.User` row.
  - Raises HTTP 401 if token decoding fails or if the user record no longer exists in the database.
  - `CurrentUser` creates a type alias combining `models.User` with `Depends(get_current_user)`.
- **Result**: `CurrentUser` is available to protect any route and inject the authenticated user instance.

### Step 2: Refactoring `PostCreate` Schema (`schemas.py`)

- **What he does**: Opens `schemas.py` and simplifies `PostCreate` so it inherits directly from `PostBase` without adding `user_id`.
- **Why he does it**: Removes `user_id` from the client-submitted request payload to prevent user spoofing.
- **Relevant code**:

  ```python
  class PostBase(BaseModel):
      title: str
      content: str

  class PostCreate(PostBase):
      pass  # user_id removed; derived on the server from the JWT token
  ```

- **How the code works**: Clients submit only `title` and `content`. Ownership assignment moves entirely to server-side route logic.
- **Result**: `PostCreate` schema no longer accepts client-supplied `user_id` fields.

### Step 3: Protecting Post Creation (`routers/posts.py`)

- **What he does**: Imports `CurrentUser` in `routers/posts.py`, adds `current_user: CurrentUser` to `create_post`, removes manual user existence checks, and sets `user_id=current_user.id`.
- **Why he does it**: Secures post creation so that posts are automatically assigned to the authenticated user identified by the JWT token.
- **Relevant code**:

  ```python
  from auth import CurrentUser

  @router.post("", response_model=schemas.PostResponse, status_code=status.HTTP_201_CREATED)
  async def create_post(
      post: schemas.PostCreate,
      current_user: CurrentUser,
      db: Annotated[AsyncSession, Depends(get_db)]
  ):
      new_post = models.Post(
          title=post.title,
          content=post.content,
          user_id=current_user.id
      )
      db.add(new_post)
      await db.commit()
      await db.refresh(new_post, attribute_names=["author"])
      return new_post
  ```

- **How the code works**: Adding `current_user: CurrentUser` forces FastAPI to execute `get_current_user` before running the handler. If authentication fails, FastAPI returns an HTTP 401 response automatically. Assigns `user_id=current_user.id` directly from the token-derived user instance.
- **Result**: `POST /api/posts` requires authentication and assigns post authorship securely.

### Step 4: Adding Ownership Checks to Post Update and Delete Routes (`routers/posts.py`)

- **What he does**: Refactors `PUT /api/posts/{post_id}`, `PATCH /api/posts/{post_id}`, and `DELETE /api/posts/{post_id}` to include `current_user: CurrentUser` and enforce ownership validation (`if post.user_id != current_user.id`).
- **Why he does it**: Prevents authenticated users from updating or deleting posts authored by other users.
- **Relevant code**:

  ```python
  # Full Update Post (PUT)
  @router.put("/{post_id}", response_model=schemas.PostResponse)
  async def update_post_full(
      post_id: int,
      post_data: schemas.PostCreate,
      current_user: CurrentUser,
      db: Annotated[AsyncSession, Depends(get_db)]
  ):
      stmt = select(models.Post).where(models.Post.id == post_id)
      result = await db.execute(stmt)
      post = result.scalars().first()
      if not post:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

      # Ownership Check
      if post.user_id != current_user.id:
          raise HTTPException(
              status_code=status.HTTP_403_FORBIDDEN,
              detail="Not authorized to update this post"
          )

      post.title = post_data.title
      post.content = post_data.content
      # Note: post.user_id is NOT updated; ownership is immutable

      await db.commit()
      await db.refresh(post, attribute_names=["author"])
      return post

  # Partial Update Post (PATCH)
  @router.patch("/{post_id}", response_model=schemas.PostResponse)
  async def update_post_partial(
      post_id: int,
      post_data: schemas.PostUpdate,
      current_user: CurrentUser,
      db: Annotated[AsyncSession, Depends(get_db)]
  ):
      stmt = select(models.Post).where(models.Post.id == post_id)
      result = await db.execute(stmt)
      post = result.scalars().first()
      if not post:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

      # Ownership Check
      if post.user_id != current_user.id:
          raise HTTPException(
              status_code=status.HTTP_403_FORBIDDEN,
              detail="Not authorized to update this post"
          )

      update_data = post_data.model_dump(exclude_unset=True)
      for field, value in update_data.items():
          setattr(post, field, value)

      await db.commit()
      await db.refresh(post, attribute_names=["author"])
      return post

  # Delete Post (DELETE)
  @router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
  async def delete_post(
      post_id: int,
      current_user: CurrentUser,
      db: Annotated[AsyncSession, Depends(get_db)]
  ):
      stmt = select(models.Post).where(models.Post.id == post_id)
      result = await db.execute(stmt)
      post = result.scalars().first()
      if not post:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

      # Ownership Check
      if post.user_id != current_user.id:
          raise HTTPException(
              status_code=status.HTTP_403_FORBIDDEN,
              detail="Not authorized to delete this post"
          )

      await db.delete(post)
      await db.commit()
  ```

- **How the code works**: Queries the target post by ID. Compares `post.user_id` against `current_user.id`. If they do not match, raises an HTTP 403 Forbidden exception with detail `"Not authorized to update/delete this post"`.
- **Result**: Users can only modify or delete posts that they authored.

### Step 5: Refactoring `GET /api/users/me` and User Routes (`routers/users.py`)

- **What he does**: Refactors `GET /api/users/me` to use `current_user: CurrentUser`, reducing handler logic down to returning `current_user`. Adds ownership checks to `PATCH /api/users/{user_id}` and `DELETE /api/users/{user_id}`.
- **Why he does it**: Simplifies the `/me` endpoint and prevents users from updating or deleting other users' accounts.
- **Relevant code**:

  ```python
  from auth import CurrentUser

  # Refactored /me endpoint (reduced from ~30 lines to 3 lines)
  @router.get("/me", response_model=schemas.UserPrivate)
  async def get_current_user_info(current_user: CurrentUser):
      return current_user

  # Protected User Profile Update
  @router.patch("/{user_id}", response_model=schemas.UserPrivate)
  async def update_user(
      user_id: int,
      user_update: schemas.UserUpdate,
      current_user: CurrentUser,
      db: Annotated[AsyncSession, Depends(get_db)]
  ):
      if user_id != current_user.id:
          raise HTTPException(
              status_code=status.HTTP_403_FORBIDDEN,
              detail="Not authorized to update this user"
          )

      user = (
          await db.execute(select(models.User).where(models.User.id == user_id))
      ).scalars().first()
      if not user:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

      if user_update.username is not None and user_update.username != user.username:
          existing_username = (
              await db.execute(select(models.User).where(func.lower(models.User.username) == user_update.username.lower()))
          ).scalars().first()
          if existing_username:
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already in use")

      if user_update.email is not None and user_update.email != user.email:
          existing_email = (
              await db.execute(select(models.User).where(func.lower(models.User.email) == user_update.email.lower()))
          ).scalars().first()
          if existing_email:
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use")

      if user_update.username is not None:
          user.username = user_update.username
      if user_update.email is not None:
          user.email = user_update.email.lower()
      if user_update.image_file is not None:
          user.image_file = user_update.image_file

      await db.commit()
      await db.refresh(user)
      return user

  # Protected User Account Deletion
  @router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
  async def delete_user(
      user_id: int,
      current_user: CurrentUser,
      db: Annotated[AsyncSession, Depends(get_db)]
  ):
      if user_id != current_user.id:
          raise HTTPException(
              status_code=status.HTTP_403_FORBIDDEN,
              detail="Not authorized to delete this user"
          )

      user = (
          await db.execute(select(models.User).where(models.User.id == user_id))
      ).scalars().first()
      if not user:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

      await db.delete(user)
      await db.commit()
  ```

- **How the code works**:
  - `get_current_user_info` relies entirely on `CurrentUser` dependency resolution, returning `current_user` directly.
  - Profile updates and account deletions check `if user_id != current_user.id`, raising HTTP 403 Forbidden if a user attempts to alter or delete another user's profile.
- **Result**: User management endpoints enforce self-service profile ownership controls.

### Step 6: Testing API Protection in Swagger UI (`/docs`)

- **What he does**: Resets the database (`rm blog.db`), starts the server, creates two users (`CoreyMS` and `TestUser`), creates a post as `CoreyMS`, logs in as `TestUser`, and attempts to edit/delete `CoreyMS`'s post.
- **Why he does it**: Verifies backend permission enforcement independently of frontend code.
- **Result**:
  - Unauthenticated `POST /api/posts` returns `401 Unauthorized`.
  - `POST /api/posts` as an authorized user creates a post associated with that user's token.
  - Attempting `PATCH /api/posts/1` while logged in as `TestUser` returns `403 Forbidden` with detail `"Not authorized to update this post"`.

### Step 7: Updating Frontend Navbar & Create Post Script (`layout.html`)

- **What he does**: Replaces the navbar username text display with a link to `/account`. Updates the `createPostForm` submit listener in `templates/layout.html` to import `getToken` from `auth.js`, remove hardcoded `user_id = 1`, attach `Authorization: Bearer <token>` headers, and handle 401 redirects.
- **Why he does it**: Connects post creation on the frontend to backend token authentication.
- **Relevant code**:

  ```javascript
  // In layout.html script block
  import {
    getErrorMessage,
    showModal,
    hideModal,
  } from "{{ url_for('static', path='js/utils.js') }}";
  import { getToken } from "{{ url_for('static', path='js/auth.js') }}";

  const createPostForm = document.getElementById("createPostForm");
  if (createPostForm) {
    createPostForm.addEventListener("submit", async (event) => {
      event.preventDefault();

      const token = getToken();
      if (!token) {
        window.location.href = "/login";
        return;
      }

      const formData = new FormData(createPostForm);
      const postData = Object.fromEntries(formData.entries());
      // Hardcoded user_id = 1 removed!

      try {
        const response = await fetch("/api/posts", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(postData),
        });

        if (response.status === 401) {
          window.location.href = "/login";
          return;
        }

        if (response.ok) {
          document.getElementById("successMessage").textContent =
            "Post created successfully!";
          hideModal("createPostModal");
          showModal("successModal");
          createPostForm.reset();

          const successModalElement = document.getElementById("successModal");
          successModalElement.addEventListener(
            "hidden.bs.modal",
            () => {
              window.location.reload();
            },
            { once: true }
          );
        } else {
          const errorData = await response.json();
          const message = getErrorMessage(errorData);
          document.getElementById("errorMessage").textContent = message;
          hideModal("createPostModal");
          showModal("errorModal");
        }
      } catch (error) {
        document.getElementById("errorMessage").textContent =
          "Network error. Please try again.";
        hideModal("createPostModal");
        showModal("errorModal");
      }
    });
  }
  ```

- **How the code works**: `getToken()` retrieves the stored access token from `localStorage`. If absent or if the server returns 401, the user is redirected to `/login`. Attaches `Authorization: Bearer ${token}` to the request headers.
- **Result**: Frontend post creation uses token authentication.

### Step 8: Updating Post Page Controls and Script (`templates/post.html`)

- **What he does**: Removes Jinja2 template wrappers (`{% if post.user_id == 1 %}`) from `templates/post.html`, replacing them with an element container (`<div id="postActions" style="display: none;">`). Replaces the bottom script block with ownership checking logic and Bearer header requests.
- **Why he does it**: Evaluates post ownership dynamically in client-side JavaScript using `getCurrentUser()` and attaches Bearer tokens to edit (`PATCH`) and delete (`DELETE`) requests.
- **Relevant code**:

  ```html
  <!-- HTML markup in templates/post.html -->
  <div id="postActions" class="mt-2" style="display: none;">
    <button
      type="button"
      class="btn btn-secondary btn-sm me-1"
      data-bs-toggle="modal"
      data-bs-target="#editPostModal"
    >
      Edit
    </button>
    <button
      type="button"
      class="btn btn-danger btn-sm"
      data-bs-toggle="modal"
      data-bs-target="#deletePostModal"
    >
      Delete
    </button>
  </div>

  {% block scripts %}
  <script type="module">
    import {
      getErrorMessage,
      showModal,
      hideModal,
    } from "{{ url_for('static', path='js/utils.js') }}";
    import {
      getCurrentUser,
      getToken,
    } from "{{ url_for('static', path='js/auth.js') }}";

    const postId = "{{ post.id }}";
    const postUserId = parseInt("{{ post.user_id }}");

    // Dynamic ownership check on page load
    async function checkOwnership() {
      const currentUser = await getCurrentUser();
      if (currentUser && currentUser.id === postUserId) {
        const postActions = document.getElementById("postActions");
        if (postActions) {
          postActions.style.display = "block";
        }
      }
    }

    // Handle Edit Post Submission (PATCH)
    const editPostForm = document.getElementById("editPostForm");
    if (editPostForm) {
      editPostForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const token = getToken();
        if (!token) {
          window.location.href = "/login";
          return;
        }

        const formData = new FormData(editPostForm);
        const updateData = Object.fromEntries(formData.entries());
        delete updateData.post_id;

        try {
          const response = await fetch(`/api/posts/${postId}`, {
            method: "PATCH",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify(updateData),
          });

          if (response.status === 401) {
            window.location.href = "/login";
            return;
          }

          if (response.status === 403) {
            document.getElementById("errorMessage").textContent =
              "You are not authorized to edit this post.";
            hideModal("editPostModal");
            showModal("errorModal");
            return;
          }

          if (response.ok) {
            document.getElementById("successMessage").textContent =
              "Post updated successfully!";
            hideModal("editPostModal");
            showModal("successModal");
            const successModalElement = document.getElementById("successModal");
            successModalElement.addEventListener(
              "hidden.bs.modal",
              () => {
                window.location.reload();
              },
              { once: true }
            );
          } else {
            const errorData = await response.json();
            document.getElementById("errorMessage").textContent =
              getErrorMessage(errorData);
            hideModal("editPostModal");
            showModal("errorModal");
          }
        } catch (error) {
          document.getElementById("errorMessage").textContent =
            "Network error. Please try again.";
          hideModal("editPostModal");
          showModal("errorModal");
        }
      });
    }

    // Handle Delete Post Confirmation (DELETE)
    const confirmDeleteBtn = document.getElementById("confirmDelete");
    if (confirmDeleteBtn) {
      confirmDeleteBtn.addEventListener("click", async () => {
        const token = getToken();
        if (!token) {
          window.location.href = "/login";
          return;
        }

        try {
          const response = await fetch(`/api/posts/${postId}`, {
            method: "DELETE",
            headers: {
              Authorization: `Bearer ${token}`,
            },
          });

          if (response.status === 401) {
            window.location.href = "/login";
            return;
          }

          if (response.status === 403) {
            document.getElementById("errorMessage").textContent =
              "You are not authorized to delete this post.";
            hideModal("deletePostModal");
            showModal("errorModal");
            return;
          }

          if (response.status === 204) {
            hideModal("deletePostModal");
            window.location.href = "/";
          } else {
            const errorData = await response.json();
            document.getElementById("errorMessage").textContent =
              getErrorMessage(errorData);
            hideModal("deletePostModal");
            showModal("errorModal");
          }
        } catch (error) {
          document.getElementById("errorMessage").textContent =
            "Network error. Please try again.";
          hideModal("deletePostModal");
          showModal("errorModal");
        }
      });
    }

    checkOwnership();
  </script>
  {% endblock scripts %}
  ```

- **How the code works**:
  - `checkOwnership()` compares `currentUser.id` against `postUserId`. If they match, unhides `#postActions`.
  - `PATCH` and `DELETE` fetch calls attach `Authorization: Bearer ${token}`.
  - Handles HTTP 401 by redirecting to `/login` and HTTP 403 by displaying a permission error modal.
- **Result**: Single post views display edit and delete options exclusively to the author and execute authorized API calls.

### Step 9: Creating the User Account Page Route and Template

- **What he does**: Adds an `@app.get("/account", include_in_schema=False)` template route in `main.py` and creates `templates/account.html`.
- **Why he does it**: Provides a frontend page where users can view profile details, update account credentials, log out, or delete their account.
- **Relevant code**:

  ```python
  # In main.py
  @app.get("/account", include_in_schema=False, name="account")
  async def account_page(request: Request):
      return templates.TemplateResponse(
          request=request,
          name="account.html",
          context={"title": "Account"}
      )
  ```

  ```html
  <!-- Key JS inside templates/account.html -->
  <script type="module">
    import {
      getErrorMessage,
      showModal,
      hideModal,
    } from "{{ url_for('static', path='js/utils.js') }}";
    import {
      getCurrentUser,
      getToken,
      logout,
      clearUserCache,
    } from "{{ url_for('static', path='js/auth.js') }}";

    let currentUserData = null;

    async function loadUserData() {
      currentUserData = await getCurrentUser();
      if (!currentUserData) {
        window.location.href = "/login";
        return;
      }

      document.getElementById("accountUsername").textContent =
        currentUserData.username;
      document.getElementById("accountEmail").textContent =
        currentUserData.email;
      document.getElementById("inputUsername").value = currentUserData.username;
      document.getElementById("inputEmail").value = currentUserData.email;
      document.getElementById("profilePic").src = currentUserData.image_path;
    }

    // Profile Update Listener (PATCH /api/users/{id})
    document
      .getElementById("updateProfileForm")
      ?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const token = getToken();
        if (!token || !currentUserData) return;

        const formData = new FormData(e.target);
        const updateData = Object.fromEntries(formData.entries());

        const response = await fetch(`/api/users/${currentUserData.id}`, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(updateData),
        });

        if (response.ok) {
          clearUserCache(); // Force auth.js to refetch updated user data
          window.location.reload();
        } else {
          const errorData = await response.json();
          document.getElementById("errorMessage").textContent =
            getErrorMessage(errorData);
          showModal("errorModal");
        }
      });

    // Logout Listener
    document.getElementById("logoutBtn")?.addEventListener("click", logout);

    // Account Deletion Listener (DELETE /api/users/{id})
    document
      .getElementById("confirmDeleteAccountBtn")
      ?.addEventListener("click", async () => {
        const token = getToken();
        if (!token || !currentUserData) return;

        const response = await fetch(`/api/users/${currentUserData.id}`, {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (response.status === 204) {
          logout(); // Clears local storage token and redirects to '/'
        } else {
          const errorData = await response.json();
          document.getElementById("errorMessage").textContent =
            getErrorMessage(errorData);
          showModal("errorModal");
        }
      });

    loadUserData();
  </script>
  ```

- **How the code works**:
  - Client guard: `loadUserData()` fetches `getCurrentUser()`. If unauthenticated, redirects to `/login`.
  - Form updates: Transmits `PATCH /api/users/{id}` with Bearer header. Upon success, calls `clearUserCache()` so `auth.js` reloads updated username details into navbar elements.
  - Account deletion: Transmits `DELETE /api/users/{id}` with Bearer header. SQLAlchemy's `cascade="all, delete-orphan"` rule automatically deletes associated posts. Clears local storage and redirects to `/`.
- **Result**: Users can manage profile details, log out, or delete their account.

### Step 10: End-to-End Testing

- **What he does**: Executes a complete user workflow test in the browser:
  1. Registers two accounts (`CoreyMS` and `TestUser`).
  2. Creates posts as `CoreyMS`.
  3. Logs in as `TestUser` and creates posts.
  4. Navigates to `CoreyMS`'s post while logged in as `TestUser` — verifies edit/delete buttons are hidden.
  5. Navigates to `TestUser`'s post — verifies edit/delete buttons are displayed, updates a post, and deletes another post.
  6. Navigates to `/account`, updates username, and verifies navbar updates instantly.
  7. Clicks "Delete Account" in the Danger Zone — confirms account deletion, automatic logout, and removal of associated posts from the homepage feed.
- **Why he does it**: Confirms that authentication, authorization, token headers, ownership checks, cascading deletions, and client UI updates function seamlessly.
- **Result**: Full end-to-end multi-user security is verified.

---

## 4. Code Examples

### Reusable Dependency and Type Alias (`auth.py`)

```python
from typing import Annotated
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
import models

# Reusable get_current_user dependency
async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user_id = verify_access_token(token)
    if user_id is None:
        raise credentials_exception

    user = (
        await db.execute(select(models.User).where(models.User.id == user_id))
    ).scalars().first()

    if user is None:
        raise credentials_exception

    return user

# Convenient Type Alias
CurrentUser = Annotated[models.User, Depends(get_current_user)]
```

### Protected Post Routes (`routers/posts.py`)

```python
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
import models
import schemas
from auth import CurrentUser

router = APIRouter()

@router.post("", response_model=schemas.PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    post: schemas.PostCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    new_post = models.Post(
        title=post.title,
        content=post.content,
        user_id=current_user.id
    )
    db.add(new_post)
    await db.commit()
    await db.refresh(new_post, attribute_names=["author"])
    return new_post

@router.patch("/{post_id}", response_model=schemas.PostResponse)
async def update_post_partial(
    post_id: int,
    post_data: schemas.PostUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = select(models.Post).where(models.Post.id == post_id)
    result = await db.execute(stmt)
    post = result.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    # Server-Side Ownership Check
    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this post"
        )

    update_data = post_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(post, field, value)

    await db.commit()
    await db.refresh(post, attribute_names=["author"])
    return post

@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = select(models.Post).where(models.Post.id == post_id)
    result = await db.execute(stmt)
    post = result.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    # Server-Side Ownership Check
    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this post"
        )

    await db.delete(post)
    await db.commit()
```

### Simplified `/me` and Protected User Routes (`routers/users.py`)

```python
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
import models
import schemas
from auth import CurrentUser

router = APIRouter()

# Refactored /me endpoint
@router.get("/me", response_model=schemas.UserPrivate)
async def get_current_user_info(current_user: CurrentUser):
    return current_user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this user"
        )

    user = (
        await db.execute(select(models.User).where(models.User.id == user_id))
    ).scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await db.delete(user)
    await db.commit()
```

---

## 5. FastAPI & Python Knowledge

- **Type Aliases (`CurrentUser = Annotated[...]`)**: Defining `CurrentUser = Annotated[models.User, Depends(get_current_user)]` combines the expected return type (`models.User`) with dependency metadata (`Depends(get_current_user)`). This allows cleaner parameter declarations across handlers.
- **Chained Dependency Injection**: Dependencies can consume other dependencies. `get_current_user` depends on `oauth2_scheme` (token extraction) and `get_db` (database session creation). FastAPI resolves dependency trees automatically.
- **HTTP Status Code Semantics**:
  - `401 Unauthorized`: Token missing, invalid, expired, or user not found. Client action: Log in.
  - `403 Forbidden`: Authenticated, but user lacks permission. Client action: Display permission warning.
- **Header Format Standards**: Bearer tokens are transmitted in the HTTP `Authorization` header using the format `Authorization: Bearer <token>`.
- **Database Cascading Deletion Verification**: When an account is deleted via `db.delete(user)`, SQLAlchemy's `cascade="all, delete-orphan"` configuration on `User.posts` automatically issues SQL deletion statements for all child posts authored by that user.

---

## 6. Tips & Important Details

- **Code Reduction via Dependencies**: Creating `CurrentUser` reduced `routers/posts.py` and `routers/users.py` by dozens of lines by eliminating manual user lookup code blocks across every route handler.
- **Immutability of Ownership**: When executing full updates (`PUT /api/posts/{id}`), `post.user_id` should not be modified. Resource ownership is immutable once assigned upon creation.
- **Clearing Client User Cache**: Calling `clearUserCache()` in `auth.js` after profile updates forces `getCurrentUser()` to clear its cached promise and refetch fresh user data from `/api/users/me`, updating navbar text instantly.
- **Single Page App Navbar Flicker**: Because browser pages check `localStorage` asynchronously via JavaScript after DOM rendering, a split-second flicker may occur as the navbar transitions from logged-out to logged-in state. This trade-off is common in stateless JWT architectures.
- **Server-Side Security Imperative**: Hiding edit/delete buttons in templates via JavaScript provides user guidance, but server-side authorization checks on API routes deliver actual security.

---

## 7. Errors & Pitfalls

- **Accepting `user_id` in Request Payloads**: Accepting `user_id` in `PostCreate` schemas allows clients to spoof post authorship. Always derive user identity from trusted JWT tokens on the server.
- **Misusing Status Codes (401 vs. 403)**: Returning 401 when an authenticated user attempts to modify another user's post misleads clients into prompting a login. Use 403 Forbidden for permission failures.
- **Omitting `Authorization` Headers in Fetch Requests**: Forgetting to attach `'Authorization': 'Bearer ' + token` in client `fetch()` calls causes FastAPI to reject requests with 401 Unauthorized responses.
- **Relying on Client-Side Code for Security**: Hiding buttons or adding client-side JS redirects without enforcing server-side route checks leaves endpoints vulnerable to unauthorized direct API calls.
- **Modifying Parameter Names in Type Aliases**: When using type aliases like `CurrentUser`, route handlers inherit the underlying dependency logic intact. Parameter names inside route signatures do not alter dependency behavior.

---

## 8. Best Practices & Trade-offs

- **Server-Side Ownership Validation**:
  - _Best Practice_: Always check `resource.user_id == current_user.id` on the server before applying mutations (`PUT`, `PATCH`, `DELETE`).
- **Reusable Type Aliases (`CurrentUser`)**:
  - _Pros_: Keeps route parameter lists concise, prevents code duplication, and simplifies security updates across route handlers.
- **Client-Side UX Guards vs. Server Enforcement**:
  - Client-side JS guards improve user experience by hiding invalid actions. Server-side route checks provide security.

---

## 9. Resources

- **GitHub Source Code Repository**: Companion code repository for Part 11 linked in the video description.
- **FastAPI Security Documentation**: Official documentation covering OAuth2, scopes, and dependency injection patterns.
- **MDN HTTP Status Codes**: Official specifications for HTTP 401 Unauthorized and HTTP 403 Forbidden.

---

## 10. Key Takeaways

1. Authorization enforces access permissions ("What are you allowed to do?").
2. Server-side authorization checks must be applied to every protected mutation endpoint.
3. `get_current_user` combines token verification and database lookup into a single reusable dependency.
4. `CurrentUser = Annotated[models.User, Depends(get_current_user)]` creates a clean type alias for route parameters.
5. Remove `user_id` from `PostCreate` schemas to prevent client identity spoofing.
6. Derive post authorship directly from `current_user.id` on the server.
7. HTTP 401 Unauthorized signifies missing or invalid authentication credentials.
8. HTTP 403 Forbidden signifies that an authenticated user lacks permission for the requested resource.
9. Validate resource ownership (`if post.user_id != current_user.id`) before executing updates or deletions.
10. `GET /api/users/me` requires only `current_user: CurrentUser` and `return current_user`.
11. Attach `Authorization: Bearer <token>` headers to client `fetch()` requests.
12. Handle 401 responses on the frontend by redirecting to `/login`.
13. Handle 403 responses on the frontend by displaying permission warning modals.
14. Show or hide UI edit/delete buttons dynamically by comparing `currentUser.id === post.user_id`.
15. Client-side navigation guards improve user experience, but true security resides entirely on backend API routes.

---

## 11. Quick Reference

### Reusable Dependency and Type Alias Setup

```python
from typing import Annotated
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
import models

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> models.User:
    user_id = verify_access_token(token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = (await db.execute(select(models.User).where(models.User.id == user_id))).scalars().first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

CurrentUser = Annotated[models.User, Depends(get_current_user)]
```

### Route Protection and Ownership Pattern

```python
@router.patch("/{post_id}", response_model=schemas.PostResponse)
async def update_post(
    post_id: int,
    post_data: schemas.PostUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    post = (await db.execute(select(models.Post).where(models.Post.id == post_id))).scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    # Server-Side Ownership Enforcement
    if post.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Execute update...
    await db.commit()
    return post
```

### Client Fetch with Bearer Header

```javascript
const response = await fetch(`/api/posts/${postId}`, {
  method: "PATCH",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  },
  body: JSON.stringify(updateData),
});
```

---

## 12. Mental Model

- **Complete Authorization Data Flow**:
  1. **HTTP Request Arrival**: Client initiates an API request (e.g., `PATCH /api/posts/1`) with header `Authorization: Bearer <token>`.
  2. **Dependency Resolution (`CurrentUser`)**:
     - `oauth2_scheme` extracts the token string.
     - `verify_access_token()` decodes the JWT and verifies its signature and expiration.
     - `get_current_user()` queries the database for `User` where `id == user_id`.
     - If validation fails at any point, FastAPI halts execution and returns `401 Unauthorized`.
  3. **Route Handler Execution**: FastAPI injects the resolved `models.User` instance into the handler as `current_user`.
  4. **Resource Query & Ownership Gate**:
     - Route handler queries target resource (`Post`). If missing, raises `404 Not Found`.
     - Handler compares `post.user_id` against `current_user.id`.
     - If IDs do not match, handler halts execution and returns `403 Forbidden`.
  5. **State Mutation & Response**: If ownership checks pass, database changes are committed and the updated resource is returned (`200 OK` / `204 No Content`).
