# Python FastAPI Tutorial (Part 12): File Uploads - Image Processing, Validation, and Storage

## 1. Overview

- **What this lesson teaches**: How to handle file uploads in FastAPI using `UploadFile`, validate incoming file payloads, process and optimize user images with Pillow (`PIL`), prevent main event loop blocking using `run_in_threadpool`, enforce unique file naming and safe storage on disk, implement safe order-of-operations for updating and deleting user files, fix security vulnerabilities in user update schemas, and build an interactive JavaScript frontend with image preview capabilities using `FormData` and `FileReader`.
- **Learning objectives**:
  - Understand the mechanics of receiving binary file uploads via `multipart/form-data` in FastAPI using `UploadFile`.
  - Install and configure Pillow (`PIL`) for image processing tasks (EXIF orientation correction, aspect-ratio cropping/resizing, format conversion, compression).
  - Use Starlet's `run_in_threadpool` to safely offload CPU-bound image processing out of FastAPI's async event loop.
  - Centralize file upload configuration settings (such as `max_upload_size`) using `pydantic-settings`.
  - Generate secure UUID-based filenames to prevent filename collisions, path traversal attacks, and original filename exposures.
  - Implement `PATCH` and `DELETE` endpoints for managing user profile pictures (`/api/users/{user_id}/profile-picture`).
  - Enforce the safe order-of-operations pattern (Save New File \\(\rightarrow\\) Commit DB \\(\rightarrow\\) Delete Old File) to prevent permanent data loss upon database failures.
  - Update user account deletion to cascade-delete profile image files from disk.
  - Close security gaps by removing direct `image_file` manipulation from general JSON update schemas (`UserUpdate`).
  - Connect HTML forms and client-side JavaScript to file endpoints using `FormData`, avoiding manual `Content-Type` header overrides.
- **Why the topic matters**: Allowing users to upload media files requires rigorous input validation and secure storage handling. Accepting untrusted client files without checking file size, validating actual image contents, or sanitizing filenames exposes servers to remote code execution, disk exhaustion, path traversal, and broken layout rendering due to un-rotated or huge images.

---

## 2. Concepts

### `UploadFile` vs. `bytes` / `Form` Data

- **What it is**: A FastAPI file upload wrapper class (`from fastapi import UploadFile`) backed by Python's `SpooledTemporaryFile`.
- **Why it is needed**: Reading entire large file uploads directly into memory as `bytes` can exhaust server RAM under concurrent load.
- **How it works**: Files under a memory threshold (e.g., 1 MB) are kept in memory; files exceeding that threshold are spooled to temporary disk storage. `UploadFile` exposes helpful metadata and async methods:
  - `file.filename`: Original filename sent by the client.
  - `file.content_type`: MIME type declared by the browser client (e.g., `image/png`).
  - `file.size`: Total size of the file in bytes (not always reliable prior to reading).
  - `await file.read()`: Reads binary content from the file stream.
  - `await file.seek(0)`: Resets the file stream cursor to the beginning.
- **Important details**: The client browser transmits file uploads using `multipart/form-data` instead of standard `application/json`.
- **Examples**: `async def upload_image(file: UploadFile): content = await file.read()`.

### Handling CPU-Bound Image Tasks in Async FastAPI (`run_in_threadpool`)

- **What it is**: Executing synchronous, CPU-bound functions (like Pillow image resizing) inside Starlet's underlying threadpool executor using `from starlet.concurrency import run_in_threadpool`.
- **Why it is needed**: FastAPI runs `async def` endpoints directly on the main event loop. Performing heavy CPU-bound image manipulation inside an `async def` function blocks the event loop, freezing all concurrent HTTP requests across the entire application.
- **How it works**: Wrapping a synchronous function call with `await run_in_threadpool(sync_function, *args)` offloads execution to a background worker thread. The main event loop yields control and remains free to process incoming requests until the worker thread completes.
- **Important details**: Keeps the route handler asynchronous (`async def`) so database calls can still be awaited while offloading CPU computation.
- **Examples**: `filename = await run_in_threadpool(process_profile_image, file_content)`.

### Image Processing & Optimization with Pillow (`PIL`)

- **What it is**: Python's standard imaging library (`Pillow`), imported via `from PIL import Image, ImageOps`.
- **Why it is needed**: Raw uploads from camera phones or digital devices often contain EXIF orientation metadata (causing photos to render sideways), inconsistent file formats (PNG, WebP, GIF), transparent backgrounds, and huge dimensions (4K/8K resolution).
- **How it works**:
  - **EXIF Orientation**: `ImageOps.exif_transpose(image)` inspects camera EXIF tags and rotates the image to correct upright orientation.
  - **Resizing & Cropping**: `ImageOps.fit(image, (300, 300), method=Image.Resampling.LANCZOS)` resizes and crops the image to exact 300x300 square dimensions while preserving aspect ratio.
  - **Format Normalization**: Converts `RGBA` or palette (`P`) images to standard `RGB` before exporting as compressed JPEG.
  - **Compression**: `image.save(path, "JPEG", quality=85, optimize=True)` balances visual quality and file size.
- **Examples**: Processing raw uploaded bytes using `Image.open(BytesIO(file_bytes))` and saving a 300x300 JPEG.

### Secure File Naming (`uuid.uuid4()`)

- **What it is**: Replacing user-supplied filenames with randomly generated 128-bit UUID strings (`uuid.uuid4().hex + ".jpg"`).
- **Why it is needed**: User-provided filenames can contain path traversal characters (e.g., `../../etc/passwd`), non-ASCII characters, spaces, or script extensions (`shell.php.jpg`), leading to security vulnerabilities or file collisions.
- **How it works**: The server completely discards the client's `file.filename` and generates its own random hexadecimal string.
- **Examples**: `unique_filename = f"{uuid.uuid4().hex}.jpg"`.

### Safe Order-of-Operations for File Updates

- **What it is**: A three-step database and file system transaction pattern when replacing or deleting user files:
  1. Save new file to disk.
  2. Update database record and execute `await db.commit()`.
  3. Delete old file from disk _only after_ the database commit succeeds.
- **Why it is needed**: Deleting an existing file _before_ committing database changes risks permanent data loss if the database transaction fails or throws an exception.
- **How it works**: If the database commit fails, the application rolls back, leaving the user with their existing profile picture intact. The worst-case outcome is a orphaned temporary file on disk rather than a missing user image.

### Browser `FormData` & Content-Type Headers

- **What it is**: The native browser `FormData` API used in client-side JavaScript to package files and key-value form fields for `multipart/form-data` requests.
- **Why it is needed**: JSON payloads cannot directly stream raw binary file streams.
- **How it works**: `const formData = new FormData(); formData.append("file", fileInput.files);`
- **Important details**: When sending `FormData` via `fetch()`, developers **must not** manually set the `Content-Type` header. Browsers automatically generate the correct `Content-Type: multipart/form-data; boundary=----WebKitFormBoundary...` string containing essential boundary delimiters. Overriding `Content-Type` manually corrupts the request.

---

## 3. Step-by-Step Tutorial

### Step 1: Installing Pillow and Verifying Dependencies

- **What he does**: Installs `pillow` using package manager commands (`uv add pillow` or `pip install pillow`).
- **Why he does it**: Pillow provides image manipulation capabilities.
- **Relevant code**:
  ```bash
  uv add pillow
  ```
- **How the code works**: Installs Pillow into the virtual environment. `python-multipart` is already installed as part of `fastapi[standard]`.
- **Result**: `PIL` image processing modules become available.

### Step 2: Creating Image Processing Utilities (`image_utils.py`)

- **What he does**: Creates `image_utils.py` in the project root containing `PROFILE_PICS_DIR`, `process_profile_image()`, and `delete_profile_image()`.
- **Why he does it**: Isolates file system operations and Pillow processing logic into a dedicated module to keep router files clean and reusable.
- **Relevant code**:

  ```python
  from io import BytesIO
  from pathlib import Path
  import uuid
  from PIL import Image, ImageOps

  PROFILE_PICS_DIR = Path("media/profile_pics")

  def process_profile_image(file_bytes: bytes) -> str:
      with Image.open(BytesIO(file_bytes)) as original:
          # Fix EXIF orientation (camera phone rotation tags)
          image = ImageOps.exif_transpose(original)

          # Crop and resize to exactly 300x300 using high-quality Lanczos resampling
          image = ImageOps.fit(image, (300, 300), method=Image.Resampling.LANCZOS)

          # Convert transparency/RGBA/palette formats to standard RGB
          if image.mode in ("RGBA", "P"):
              image = image.convert("RGB")

          # Generate secure UUID filename
          filename = f"{uuid.uuid4().hex}.jpg"

          # Ensure destination directory exists
          PROFILE_PICS_DIR.mkdir(parents=True, exist_ok=True)
          file_path = PROFILE_PICS_DIR / filename

          # Save compressed JPEG
          image.save(file_path, "JPEG", quality=85, optimize=True)

          return filename

  def delete_profile_image(filename: str | None) -> None:
      if filename is None:
          return
      file_path = PROFILE_PICS_DIR / filename
      file_path.unlink(missing_ok=True)
  ```

- **How the code works**:
  - `BytesIO(file_bytes)` allows Pillow to read binary stream data in memory.
  - `ImageOps.exif_transpose()` fixes sideways image orientation.
  - `ImageOps.fit()` crops images to a 300x300 square without distorting aspect ratios.
  - `uuid.uuid4().hex` creates random filenames like `4f9e31d87c2b...jpg`.
  - `unlink(missing_ok=True)` safely removes files from disk without raising errors if already missing.
- **Result**: Core image handling functions are exported.

### Step 3: Centralizing Upload Configuration (`config.py`)

- **What he does**: Updates `Settings` in `config.py` to add `max_upload_size`.
- **Why he does it**: Centralizes file upload limits in `pydantic-settings`.
- **Relevant code**:

  ```python
  class Settings(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

      secret_key: SecretString
      algorithm: str = "HS256"
      access_token_expire_minutes: int = 30
      max_upload_size: int = 5 * 1024 * 1024  # 5 MB in bytes
  ```

- **How the code works**: Sets a default limit of 5 MB (`5,242,880` bytes), which can be overridden via `.env`.
- **Result**: `settings.max_upload_size` is accessible across application routers.

### Step 4: Creating Upload and Delete Endpoints (`routers/users.py`)

- **What he does**: Adds `UploadFile`, `UnidentifiedImageError`, `run_in_threadpool`, and `image_utils` imports to `routers/users.py`, then implements `PATCH /{user_id}/profile-picture` and `DELETE /{user_id}/profile-picture`.
- **Why he does it**: Provides REST API routes for uploading and removing profile pictures.
- **Relevant code**:

  ```python
  from PIL import UnidentifiedImageError
  from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
  from starlet.concurrency import run_in_threadpool
  from image_utils import delete_profile_image, process_profile_image

  @router.patch("/{user_id}/profile-picture", response_model=schemas.UserPrivate)
  async def upload_profile_picture(
      user_id: int,
      file: UploadFile,
      current_user: CurrentUser,
      db: Annotated[AsyncSession, Depends(get_db)]
  ):
      if user_id != current_user.id:
          raise HTTPException(
              status_code=status.HTTP_403_FORBIDDEN,
              detail="Not authorized to update this profile picture"
          )

      content = await file.read()

      # Validate File Size
      if len(content) > settings.max_upload_size:
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail=f"File too large. Maximum size is {settings.max_upload_size / (1024 * 1024):.0f} MB"
          )

      # Offload CPU-Bound Image Processing to Threadpool
      try:
          new_filename = await run_in_threadpool(process_profile_image, content)
      except UnidentifiedImageError:
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="Invalid image file. Please upload a valid image (JPEG, PNG, WebP)."
          )

      # Safe Order-of-Operations
      old_filename = current_user.image_file
      current_user.image_file = new_filename

      await db.commit()
      await db.refresh(current_user)

      # Delete old image only after successful commit
      delete_profile_image(old_filename)

      return current_user

  @router.delete("/{user_id}/profile-picture", response_model=schemas.UserPrivate)
  async def delete_profile_picture(
      user_id: int,
      current_user: CurrentUser,
      db: Annotated[AsyncSession, Depends(get_db)]
  ):
      if user_id != current_user.id:
          raise HTTPException(
              status_code=status.HTTP_403_FORBIDDEN,
              detail="Not authorized to delete this profile picture"
          )

      if not current_user.image_file:
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="No profile picture to delete"
          )

      old_filename = current_user.image_file
      current_user.image_file = None

      await db.commit()
      await db.refresh(current_user)

      delete_profile_image(old_filename)

      return current_user
  ```

- **How the code works**:
  - Receives `file: UploadFile` via `multipart/form-data`.
  - Checks content length against `settings.max_upload_size`.
  - Catches `UnidentifiedImageError` if the uploaded file is not a valid image format, returning HTTP 400.
  - Uses `run_in_threadpool` to run `process_profile_image` on a background thread.
  - Assigns new filename, commits database transaction, and cleans up the old image file.
- **Result**: Backend endpoints handle file processing, validation, and storage.

### Step 5: Updating User Account Deletion Cleanup (`routers/users.py`)

- **What he does**: Modifies `delete_user` in `routers/users.py` to delete the user's profile image file from disk when their account is deleted.
- **Why he does it**: Prevents leaving orphan files on disk after account removal.
- **Relevant code**:

  ```python
  @router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
  async def delete_user(
      user_id: int,
      current_user: CurrentUser,
      db: Annotated[AsyncSession, Depends(get_db)]
  ):
      if user_id != current_user.id:
          raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

      user = (await db.execute(select(models.User).where(models.User.id == user_id))).scalars().first()
      if not user:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

      old_filename = user.image_file

      await db.delete(user)
      await db.commit()

      # Clean up profile picture file from disk after commit succeeds
      if old_filename:
          delete_profile_image(old_filename)
  ```

- **How the code works**: Captures `old_filename` prior to deletion, commits user removal, and unlinks the image file from `media/profile_pics/`.
- **Result**: Account deletion cleans up associated disk storage.

### Step 6: Closing Security Vulnerability in Schemas (`schemas.py`)

- **What he does**: Removes `image_file` from `UserUpdate` in `schemas.py` and removes `image_file` assignment logic from `update_user` in `routers/users.py`.
- **Why he does it**: Prevents users from manually setting `image_file` to arbitrary filenames via general `PATCH /api/users/{id}` JSON updates, which could allow them to point to or delete other users' files.
- **Relevant code**:
  ```python
  # In schemas.py
  class UserUpdate(BaseModel):
      username: str | None = Field(default=None, min_length=1, max_length=50)
      email: EmailStr | None = Field(default=None, max_length=120)
      # image_file REMOVED to lock down file modifications to upload endpoints
  ```
- **How the code works**: Locks down profile image changes strictly to the dedicated upload and delete endpoints.
- **Result**: Security vulnerability is eliminated.

### Step 7: Updating Frontend Account Page (`templates/account.html`)

- **What he does**: Updates `account.html` with an image upload UI section, a client-side `FileReader` image preview handler, and a JavaScript `FormData` upload form submission listener.
- **Why he does it**: Enables frontend users to preview and upload profile pictures from their account page.
- **Relevant code**:

  ```html
  <!-- Account Page HTML Form Section -->
  <div class="mb-3">
    <label for="profilePicInput" class="form-label">Profile Picture</label>
    <div id="imagePreviewContainer" class="mb-2 d-none">
      <img
        id="imagePreview"
        src=""
        alt="Preview"
        class="rounded-circle object-fit-cover"
        width="100"
        height="100"
      />
    </div>
    <input
      type="file"
      class="form-control"
      id="profilePicInput"
      accept="image/*"
    />
    <button
      type="button"
      id="uploadPicBtn"
      class="btn btn-primary btn-sm mt-2"
      disabled
    >
      Upload Picture
    </button>
    <button
      type="button"
      id="deletePicBtn"
      class="btn btn-outline-danger btn-sm mt-2 ms-1"
    >
      Remove Picture
    </button>
    <div class="form-text">
      Max file size: 5 MB. Supported formats: JPEG, PNG, WebP.
    </div>
  </div>

  <script type="module">
    import {
      getErrorMessage,
      showModal,
      hideModal,
    } from "{{ url_for('static', path='js/utils.js') }}";
    import {
      getCurrentUser,
      getToken,
      clearUserCache,
    } from "{{ url_for('static', path='js/auth.js') }}";

    const profilePicInput = document.getElementById("profilePicInput");
    const uploadPicBtn = document.getElementById("uploadPicBtn");
    const deletePicBtn = document.getElementById("deletePicBtn");
    const imagePreview = document.getElementById("imagePreview");
    const imagePreviewContainer = document.getElementById(
      "imagePreviewContainer"
    );

    // FileReader API Image Preview Handler
    profilePicInput?.addEventListener("change", (e) => {
      const file = e.target.files;
      if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
          imagePreview.src = e.target.result;
          imagePreviewContainer.classList.remove("d-none");
          uploadPicBtn.disabled = false;
        };
        reader.readAsDataURL(file);
      } else {
        imagePreviewContainer.classList.add("d-none");
        uploadPicBtn.disabled = true;
      }
    });

    // Upload Handler using FormData (PATCH)
    uploadPicBtn?.addEventListener("click", async () => {
      const token = getToken();
      const user = await getCurrentUser();
      const file = profilePicInput.files;
      if (!token || !user || !file) return;

      const formData = new FormData();
      formData.append("file", file); // 'file' matches UploadFile parameter name in FastAPI

      try {
        uploadPicBtn.disabled = true;
        uploadPicBtn.textContent = "Uploading...";

        const response = await fetch(`/api/users/${user.id}/profile-picture`, {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${token}`,
            // Note: Content-Type header MUST NOT be set manually for FormData!
          },
          body: formData,
        });

        if (response.ok) {
          clearUserCache();
          window.location.reload();
        } else {
          const errorData = await response.json();
          document.getElementById("errorMessage").textContent =
            getErrorMessage(errorData);
          showModal("errorModal");
        }
      } catch (error) {
        document.getElementById("errorMessage").textContent =
          "Network error during upload.";
        showModal("errorModal");
      } finally {
        uploadPicBtn.disabled = false;
        uploadPicBtn.textContent = "Upload Picture";
      }
    });

    // Delete Profile Picture Handler (DELETE)
    deletePicBtn?.addEventListener("click", async () => {
      const token = getToken();
      const user = await getCurrentUser();
      if (!token || !user) return;

      const response = await fetch(`/api/users/${user.id}/profile-picture`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (response.ok) {
        clearUserCache();
        window.location.reload();
      } else {
        const errorData = await response.json();
        document.getElementById("errorMessage").textContent =
          getErrorMessage(errorData);
        showModal("errorModal");
      }
    });
  </script>
  ```

- **How the code works**:
  - `FileReader.readAsDataURL()` reads the selected file and sets a Base64 data URL on `imagePreview.src` for instant UI previewing.
  - `FormData.append('file', file)` packages the raw binary file under key `"file"`.
  - Sends a `PATCH` request with `Authorization: Bearer <token>` without setting a manual `Content-Type` header.
- **Result**: Users can preview, upload, and delete profile pictures directly on their account page.

---

## 4. Code Examples

### Full Image Utilities Module (`image_utils.py`)

```python
from io import BytesIO
from pathlib import Path
import uuid
from PIL import Image, ImageOps

PROFILE_PICS_DIR = Path("media/profile_pics")

def process_profile_image(file_bytes: bytes) -> str:
    """
    Processes uploaded profile image:
    1. Fixes EXIF orientation.
    2. Crops & resizes to 300x300.
    3. Converts transparency/palette modes to RGB.
    4. Saves compressed JPEG with UUID filename.
    """
    with Image.open(BytesIO(file_bytes)) as original:
        image = ImageOps.exif_transpose(original)
        image = ImageOps.fit(image, (300, 300), method=Image.Resampling.LANCZOS)

        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        filename = f"{uuid.uuid4().hex}.jpg"
        PROFILE_PICS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = PROFILE_PICS_DIR / filename

        image.save(file_path, "JPEG", quality=85, optimize=True)
        return filename

def delete_profile_image(filename: str | None) -> None:
    """Deletes profile image from disk if it exists."""
    if filename is None:
        return
    file_path = PROFILE_PICS_DIR / filename
    file_path.unlink(missing_ok=True)
```

### Complete Profile Picture Router Endpoints (`routers/users.py`)

```python
from typing import Annotated
from PIL import UnidentifiedImageError
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlet.concurrency import run_in_threadpool

from config import settings
from database import get_db
from image_utils import delete_profile_image, process_profile_image
import schemas
from auth import CurrentUser

router = APIRouter()

@router.patch("/{user_id}/profile-picture", response_model=schemas.UserPrivate)
async def upload_profile_picture(
    user_id: int,
    file: UploadFile,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    if user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    content = await file.read()

    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {settings.max_upload_size / (1024 * 1024):.0f} MB"
        )

    try:
        new_filename = await run_in_threadpool(process_profile_image, content)
    except UnidentifiedImageError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Please upload a valid image."
        )

    old_filename = current_user.image_file
    current_user.image_file = new_filename

    await db.commit()
    await db.refresh(current_user)

    delete_profile_image(old_filename)
    return current_user

@router.delete("/{user_id}/profile-picture", response_model=schemas.UserPrivate)
async def delete_profile_picture(
    user_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    if user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    if not current_user.image_file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No profile picture to delete")

    old_filename = current_user.image_file
    current_user.image_file = None

    await db.commit()
    await db.refresh(current_user)

    delete_profile_image(old_filename)
    return current_user
```

---

## 5. FastAPI & Python Knowledge

- **`UploadFile`**: FastAPI's upload parameter class that receives files via `multipart/form-data`. Spools large files to disk automatically to prevent memory spikes.
- **`run_in_threadpool`**: A Starlet concurrency function (`from starlet.concurrency import run_in_threadpool`) that executes synchronous, CPU-intensive code inside a worker threadpool while yielding control back to FastAPI's async event loop.
- **`BytesIO`**: In-memory binary stream wrapper from Python's standard `io` module (`from io import BytesIO`) that allows libraries like Pillow to process raw `bytes` without writing them to disk first.
- **`Path` (`pathlib`)**: Modern Python object-oriented file system module (`from pathlib import Path`). Methods include `.mkdir(parents=True, exist_ok=True)` and `.unlink(missing_ok=True)`.
- **Pillow Image Operations**:
  - `ImageOps.exif_transpose()`: Fixes EXIF-based camera rotation.
  - `ImageOps.fit()`: Crops and resizes images to exact dimensions.
  - `UnidentifiedImageError`: Exception raised by Pillow when attempting to open a non-image file or corrupted image stream.
- **JavaScript `FileReader` API**: Browser API (`new FileReader()`) used to read client files asynchronously as Base64 data URLs (`reader.readAsDataURL(file)`), enabling instant client-side image previews.

---

## 6. Tips & Important Details

- **Do Not Rely on Client MIME Types**: Clients can easily spoof `file.content_type` (e.g. sending an executable file with `Content-Type: image/jpeg`). Always validate files by attempting to open and process them with Pillow (`UnidentifiedImageError`).
- **Never Set Manual `Content-Type` Headers for `FormData`**: Setting `'Content-Type': 'multipart/form-data'` manually in JavaScript `fetch()` omits the browser's auto-generated boundary string, causing FastAPI to fail parsing request bodies.
- **Length Validation over `file.size`**: `file.size` is not always populated or accurate prior to reading stream data. Check file size using `len(content)` after calling `await file.read()`.
- **Pillow Lanczos Resampling**: Use `Image.Resampling.LANCZOS` inside `ImageOps.fit()` for high-quality downscaling results.
- **Production Storage Note**: Local disk storage works for development, but production applications deployed across multiple container instances require object storage (such as Amazon S3 or Google Cloud Storage) behind a CDN.

---

## 7. Errors & Pitfalls

- **Blocking the Event Loop with Pillow**: Executing `Image.open()` or `image.save()` directly inside an `async def` function blocks the main event loop. Always wrap CPU-bound image functions in `run_in_threadpool`.
- **Deleting Files Before DB Commit**: Deleting the old profile image _before_ committing the database transaction leaves the user without an image if the database commit fails. Always commit first, then delete.
- **Security Vulnerability via `UserUpdate` Schema**: Allowing `image_file` to be updated in general JSON schemas lets users point their profile picture to arbitrary filenames or delete files belonging to other users.
- **Manually Overriding `Content-Type` in Fetch Calls**: Adding `'Content-Type': 'multipart/form-data'` to `fetch()` options strips the boundary string delimiter, causing backend parsing errors.
- **Ignoring EXIF Orientation Tags**: Photos uploaded from smartphones render sideways or upside down unless processed with `ImageOps.exif_transpose()`.

---

## 8. Best Practices & Trade-offs

- **Safe Order-of-Operations Pattern**:
  - _Best Practice_: Save new file \\(\rightarrow\\) Commit database transaction \\(\rightarrow\\) Delete old file. Guarantees data integrity over disk cleanup if a database failure occurs.
- **Offloading Heavy CPU Work**:
  - _Best Practice_: Use `run_in_threadpool` for local synchronous CPU tasks. For heavy high-volume video or image processing at scale, delegate work to background task queues like Celery or Redis Queue.
- **UUID Filenames vs. Original Filenames**:
  - _Best Practice_: Discard original filenames and assign UUIDs to eliminate path traversal attacks, file collisions, and encoding issues.

---

## 9. Resources

- **GitHub Source Code Repository**: Companion code repository for Part 12 linked in the video description.
- **FastAPI Official File Uploads Documentation**: Reference for `UploadFile` and `File`.
- **Pillow (`PIL`) Documentation**: Official documentation for `Image`, `ImageOps`, and `UnidentifiedImageError`.
- **MDN `FormData` & `FileReader` API Documentation**: JavaScript references for handling files in browsers.

---

## 10. Key Takeaways

1. Use `UploadFile` to handle file uploads efficiently in FastAPI.
2. File uploads use `multipart/form-data` encoding instead of `application/json`.
3. Image processing is CPU-bound and must be offloaded using `run_in_threadpool` to prevent blocking the event loop.
4. Pillow (`PIL`) handles image processing, format conversion, and thumbnail resizing.
5. `ImageOps.exif_transpose()` corrects phone camera orientation metadata.
6. `ImageOps.fit()` resizes and crops images to exact square dimensions (e.g., 300x300).
7. Generate random UUID filenames (`uuid.uuid4().hex`) to prevent collisions and security vulnerabilities.
8. Validate file size using `len(content)` against central settings (`max_upload_size`).
9. Validate image contents by catching `UnidentifiedImageError` when Pillow opens the bytes stream.
10. Follow the safe order of operations: Save new file \\(\rightarrow\\) Commit DB \\(\rightarrow\\) Delete old file.
11. Clean up profile picture files from disk upon user account deletion.
12. Remove `image_file` from general user update schemas to prevent unauthorized file manipulation.
13. Use JavaScript `FormData` to send file uploads from frontend forms.
14. Do not manually set `Content-Type` headers when sending `FormData` via `fetch()`.
15. Use the JavaScript `FileReader` API to render instant image previews on client forms.

---

## 11. Quick Reference

### Command Line

```bash
# Install Pillow for image processing
uv add pillow
```

### Essential Imports

```python
from io import BytesIO
from pathlib import Path
import uuid
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import UploadFile
from starlet.concurrency import run_in_threadpool
```

### Async Route Image Upload Pattern

```python
@router.patch("/profile-picture")
async def upload_picture(file: UploadFile, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    content = await file.read()

    # Size check
    if len(content) > settings.max_upload_size:
        raise HTTPException(status_code=400, detail="File too large")

    # Process CPU task on threadpool
    try:
        new_filename = await run_in_threadpool(process_profile_image, content)
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="Invalid image file")

    # Order of operations
    old_filename = current_user.image_file
    current_user.image_file = new_filename
    await db.commit()

    delete_profile_image(old_filename)
    return current_user
```

### Client JavaScript Fetch with `FormData`

```javascript
const formData = new FormData();
formData.append("file", fileInput.files);

const response = await fetch("/api/users/me/profile-picture", {
  method: "PATCH",
  headers: {
    Authorization: `Bearer ${token}`,
    // DO NOT set Content-Type header manually!
  },
  body: formData,
});
```

---

## 12. Mental Model

- **File Upload Processing Architecture**:
  1. **HTTP Client Request**: Browser packages file in `FormData` \\(\rightarrow\\) Sends `PATCH` request with `multipart/form-data` encoding and `Authorization: Bearer <token>` header.
  2. **FastAPI Receiving Layer**: `UploadFile` receives file stream \\(\rightarrow\\) Performs authentication check \\(\rightarrow\\) Reads binary content into memory (`await file.read()`) \\(\rightarrow\\) Validates `len(content) <= settings.max_upload_size`.
  3. **Concurrency Offloading (`run_in_threadpool`)**: Main event loop yields execution \\(\rightarrow\\) Wraps `process_profile_image(content)` in a background threadpool thread.
  4. **Pillow Image Pipeline**: `BytesIO` stream \\(\rightarrow\\) `ImageOps.exif_transpose()` fixes orientation \\(\rightarrow\\) `ImageOps.fit()` resizes to 300x300 \\(\rightarrow\\) Converts RGBA to RGB \\(\rightarrow\\) Generates UUID filename \\(\rightarrow\\) Saves compressed JPEG to `media/profile_pics/`.
  5. **Database Transaction & Disk Cleanup**: Handler records `old_filename` \\(\rightarrow\\) Updates `user.image_file = new_filename` \\(\rightarrow\\) Commits database transaction (`await db.commit()`) \\(\rightarrow\\) Executes `delete_profile_image(old_filename)` to delete old file from disk.
  6. **Response & Frontend UI Update**: FastAPI returns updated `UserPrivate` object \\(\rightarrow\\) Frontend JavaScript clears user cache, updates profile picture source URL, and reloads view.
