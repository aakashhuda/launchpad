# Python FastAPI Tutorial (Part 1): Getting Started - Web App + REST API

## 1. Overview

- **What this lesson teaches**: This lesson covers the fundamentals of getting started with FastAPI. It demonstrates setting up a project workspace using `uv` (or `pip`), installing FastAPI, creating basic routes returning JSON responses, launching the development server, navigating automatic interactive documentation (`/docs` and `/redoc`), working with temporary dummy data, creating REST API endpoints, returning HTML responses using `HTMLResponse`, stacking decorators, and hiding non-API routes from schema documentation.
- **Learning objectives**:
  - Set up a FastAPI project directory using package managers (`uv` or `pip`).
  - Launch the application server with `fastapi dev` and leverage automatic reloading.
  - Build REST API routes returning Python dictionaries and lists automatically converted to JSON.
  - Inspect and test routes using built-in Swagger UI (`/docs`) and ReDoc (`/redoc`) documentation.
  - Return HTML responses from routes using `HTMLResponse` and the `response_class` decorator parameter.
  - Stack multiple route decorators on a single handler function and exclude HTML routes from API documentation using `include_in_schema=False`.
- **Why the topic matters**: FastAPI enables developers to quickly build high-performance Python web applications and REST APIs. It automatically generates interactive OpenAPI documentation and supports modern web development features out of the box.

---

## 2. Concepts

### FastAPI CLI Server Modes (`fastapi dev` vs `fastapi run`)

- **What it is**: Command-line interface commands used to serve FastAPI applications.
- **Why it is needed**: Executes the ASGI server required to host and test the web application locally or in production.
- **How it works**: Running `fastapi dev` starts the server in development mode with auto-reload enabled (restarting automatically upon code saves) and helpful debugging output. Running `fastapi run` starts the server optimized for production performance without auto-reload.
- **Important details**: In development mode, saving changes in code files triggers an automatic server restart.
- **Examples**: Running `fastapi dev` from the project terminal.

### Automatic Interactive API Documentation (`/docs` & `/redoc`)

- **What it is**: Built-in interactive documentation pages powered by Swagger UI (`/docs`) and ReDoc (`/redoc`).
- **Why it is needed**: Allows developers and API consumers to view, inspect, and interactively test API endpoints without writing documentation manually.
- **How it works**: FastAPI inspects route decorators, paths, and response types to auto-generate OpenAPI specification schemas.
- **Important details**: The Swagger UI (`/docs`) includes a "Try it out" button to execute live requests, view parameters, inspect response bodies, and obtain ready-to-use `curl` commands for terminal testing.
- **Examples**: Opening `http://localhost:8000/docs` or `http://localhost:8000/redoc` in a web browser.

### Automatic JSON Serialization

- **What it is**: The automatic transformation of Python native data structures (such as lists of dictionaries) into JSON output.
- **Why it is needed**: Eliminates manual string conversions or `json.dumps()` calls when returning REST API data.
- **How it works**: Returning a Python dictionary or list of dictionaries directly from a route handler prompts FastAPI to serialize the data into a JSON object or array.
- **Important details**: Lists of dictionaries are serialized into JSON arrays.
- **Examples**: Returning a Python `posts` list of dictionaries from a route handler returns a formatted JSON array to the client.

### HTML Responses (`HTMLResponse` & `response_class`)

- **What it is**: A dedicated response class imported from `fastapi.responses` that sends HTML strings instead of JSON responses.
- **Why it is needed**: Enables serving web pages for human browser navigation alongside programmatic JSON API routes.
- **How it works**: Passing `response_class=HTMLResponse` into the route decorator configures the endpoint headers (`Content-Type: text/html`) and renders returned HTML strings in the browser.
- **Important details**: Allows dynamic string interpolation (such as F-strings) to render HTML tags.
- **Examples**: `@app.get("/", response_class=HTMLResponse)` returning `f"<h1>{posts['title']}</h1>"`.

### Stacked Decorators

- **What it is**: Applying multiple path decorators to a single Python handler function.
- **Why it is needed**: Maps multiple URL paths to execute the same route handler logic without duplicating code.
- **How it works**: FastAPI routes requests coming to any listed path to the underlying function.
- **Important details**: Useful when aliasing routes (e.g. mapping both `/` and `/posts` to the home handler).
- **Examples**: Decorating a function with both `@app.get("/")` and `@app.get("/posts")`.

### Schema Exclusion (`include_in_schema`)

- **What it is**: A decorator parameter (`include_in_schema=False`) that controls endpoint visibility in documentation schemas.
- **Why it is needed**: Keeps API documentation clean by hiding non-API routes (such as browser HTML pages) from Swagger UI and ReDoc.
- **How it works**: Suppresses the decorated route from being published to the OpenAPI schema generated at `/docs` or `/redoc`.
- **Examples**: `@app.get("/", include_in_schema=False)`.

---

## 3. Step-by-Step Tutorial

### Step 1: Creating the Project Directory

- **What he does**: Opens the terminal on the desktop, initializes a new directory named `fastAPI_blog` using `uv init fastAPI_blog`, and changes directory into `fastAPI_blog`.
- **Why he does it**: Establishes a fresh project folder and environment structure.
- **Relevant code**:
  ```bash
  uv init fastAPI_blog
  cd fastAPI_blog
  ```
- **How the code works**: `uv init` initializes a project folder quickly using `uv`; alternatively, creating a directory manually and managing dependencies with `pip` works identically.
- **Result**: A clean project workspace directory is prepared.

### Step 2: Installing FastAPI

- **What he does**: Installs FastAPI into the project environment.
- **Why he does it**: Downloads the FastAPI framework dependencies required to build routes and launch the server.
- **Result**: FastAPI packages become available for import.

### Step 3: Building the Initial `main.py` & Hello World Route

- **What he does**: Creates `main.py`, imports `FastAPI`, instantiates `app = FastAPI()`, and writes a root route `@app.get("/")` returning a dictionary `{"message": "Hello World"}`.
- **Why he does it**: Sets up the minimal functional FastAPI REST API endpoint.
- **Relevant code**:

  ```python
  from fastapi import FastAPI

  app = FastAPI()

  @app.get("/")
  def home():
      return {"message": "Hello World"}
  ```

- **How the code works**: `app = FastAPI()` initializes the application instance. `@app.get("/")` listens for HTTP GET requests at the root path and triggers `home()`, returning JSON.
- **Result**: Navigating to `http://localhost:8000` returns the JSON response `{"message": "Hello World"}`.

### Step 4: Running the Development Server

- **What he does**: Runs `fastapi dev` in the project terminal.
- **Why he does it**: Starts the ASGI development server with auto-reload enabled.
- **Relevant code**:
  ```bash
  fastapi dev
  ```
- **How the code works**: Launches a local server at port 8000, provides debugging information, and monitors files for updates.
- **Result**: Terminal displays startup logs, and saving edits automatically restarts the server.

### Step 5: Exploring Automatic Documentation

- **What he does**: Navigates to `http://localhost:8000/docs` and `http://localhost:8000/redoc` in the web browser.
- **Why he does it**: Demonstrates the interactive Swagger UI and ReDoc documentation auto-generated from code.
- **Result**: Endpoints can be inspected, tested live via "Try it out", and exported as `curl` commands.

### Step 6: Adding Temporary Dummy Data

- **What he does**: Paste-defines a Python list of dictionaries named `posts` at the top of `main.py`, containing mock post fields (`id`, `author`, `title`, `content`, `date_posted`).
- **Why he does it**: Provides mock data to simulate database records before implementing database integration later in the series.
- **Result**: In-memory posts data becomes available for route handlers.

### Step 7: Creating the JSON API Endpoint for Posts

- **What he does**: Creates route `@app.get("/api/posts")` with handler function `get_posts()` returning the list of dictionaries.
- **Why he does it**: Builds a programmatic REST API endpoint for fetching post data.
- **Relevant code**:
  ```python
  @app.get("/api/posts")
  def get_posts():
      return posts
  ```
- **How the code works**: FastAPI converts the list of Python dictionaries into a JSON array automatically.
- **Result**: Navigating to `/api/posts` returns post records as a JSON array.

### Step 8: Configuring HTML Responses

- **What he does**: Imports `HTMLResponse` from `fastapi.responses`, sets `response_class=HTMLResponse` in the `@app.get("/")` decorator, and returns an F-string containing HTML tags (e.g. `<h1>`).
- **Why he does it**: Demonstrates rendering HTML web pages for browser clients.
- **Relevant code**:

  ```python
  from fastapi.responses import HTMLResponse

  @app.get("/", response_class=HTMLResponse)
  def home():
      return f"<h1>{posts['title']}</h1>"
  ```

- **How the code works**: `response_class=HTMLResponse` instructs FastAPI to set HTML headers and send raw string content as rendered HTML.
- **Result**: Browser displays rendered HTML heading text instead of JSON.

### Step 9: Stacking Path Decorators & Hiding HTML Routes from Schema

- **What he does**: Adds a second decorator `@app.get("/posts")` above `home()` and includes `include_in_schema=False` on both HTML route decorators.
- **Why he does it**: Routes `/` and `/posts` to the same handler function while keeping non-API HTML routes out of API documentation.
- **Relevant code**:
  ```python
  @app.get("/", response_class=HTMLResponse, include_in_schema=False)
  @app.get("/posts", response_class=HTMLResponse, include_in_schema=False)
  def home():
      return f"<h1>{posts['title']}</h1>"
  ```
- **How the code works**: Stacked decorators assign multiple paths to `home()`; `include_in_schema=False` suppresses documentation generation for those paths.
- **Result**: Both `/` and `/posts` serve the HTML page, while Swagger UI at `/docs` cleanly displays only REST API endpoints.

---

## 4. Code Examples

### Full `main.py` Example

```python
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

# Temporary dummy post data
posts = [
    {
        "id": 1,
        "author": "Corey Schafer",
        "title": "FastAPI Tutorial",
        "content": "First post content",
        "date_posted": "April 20, 2024"
    },
    {
        "id": 2,
        "author": "Jane Doe",
        "title": "FastAPI Part 2",
        "content": "Second post content",
        "date_posted": "April 21, 2024"
    }
]

# HTML page routes (hidden from API docs)
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/posts", response_class=HTMLResponse, include_in_schema=False)
def home():
    return f"<h1>{posts['title']}</h1>"

# Programmatic JSON REST API endpoint
@app.get("/api/posts")
def get_posts():
    return posts
```

### Terminal Commands

```bash
# Initialize project workspace with uv
uv init fastAPI_blog
cd fastAPI_blog

# Launch local development server with auto-reload
fastapi dev

# Test API endpoint using curl in terminal (generated via /docs)
curl -X 'GET' 'http://127.0.0.1:8000/api/posts' -H 'accept: application/json'
```

---

## 5. FastAPI & Python Knowledge

- **`FastAPI` Application Instance**: The main class imported from `fastapi` that initializes the web application instance (`app = FastAPI()`).
- **HTTP GET Route Decorator (`@app.get`)**: Maps HTTP GET requests for specific path strings to Python handler functions.
- **`HTMLResponse` Class**: Imported from `fastapi.responses`; alters the response class so FastAPI sends `Content-Type: text/html` headers instead of JSON.
- **Python F-Strings & Dictionary Access**: Used inside route handler functions to interpolate data dynamically from Python dictionaries into strings (e.g., `posts['title']`).
- **Decorator Metadata Parameters**:
  - `response_class`: Explicitly designates custom response types such as `HTMLResponse`.
  - `include_in_schema`: Boolean flag specifying whether a route should appear in the generated OpenAPI schema documentation (`/docs` and `/redoc`).

---

## 6. Tips & Important Details

- **`uv` Package Manager**: Recommended as a faster modern package manager compared to traditional `pip`, though standard `pip` workflows are fully compatible.
- **Browser JSON Formatting**: Modern browsers (such as Chrome) include built-in pretty-printing features for raw JSON responses.
- **Copying `curl` Commands**: Swagger UI (`/docs`) generates formatted `curl` commands for endpoints, which can be copied directly into terminal command lines for testing.
- **Sample Application Features**: The full application built throughout the series includes a light/dark mode switch, user profile updates, photo uploads, background task emails for password resets, dynamic pagination, and JWT authentication.
- **In-Memory Data Placeholder**: Using a list of dictionaries at the top of `main.py` serves as a simple temporary dataset before setting up SQL databases (SQLite and PostgreSQL) later in the series.

---

## 7. Errors & Pitfalls

- **Typos and Syntax Errors in `main.py`**: Introduced errors trigger auto-reload crash logs in `fastapi dev` terminal output; fixing the typo and saving the file automatically restarts the server.
- **API Documentation Pollution**: Leaving HTML web page routes visible in `/docs` clutters API schemas; resolved by setting `include_in_schema=False` on non-API routes.
- **Hardcoded HTML Strings**: Returning raw HTML strings directly inside route handler functions becomes unmaintainable for real applications; Jinja2 templates should be used instead.

---

## 8. Best Practices & Trade-offs

- **`fastapi dev` vs `fastapi run`**:
  - `fastapi dev`: Ideal for development because it enables auto-reload on file save and provides verbose debugging logs.
  - `fastapi run`: Ideal for production deployment because it is optimized for performance and stability.
- **Separating REST API Routes and HTML Routes**: Separate programmatic endpoints (e.g., `/api/posts`) from human-facing browser paths (e.g., `/`), and use `include_in_schema=False` to isolate API documentation.
- **`uv` vs `pip`**: `uv` offers speed advantages for managing packages, but standard `pip` inside standard virtual environments is completely supported.
- **Raw HTML Strings vs Jinja2 Templates**: Raw HTML strings work for quick basic examples, but template engine inheritance (Jinja2) is necessary for maintainable production web applications.

---

## 9. Resources

- **GitHub Source Code Repository**: Links to downloadable source code for each video step are provided in the video description.
- **Corey Schafer's `uv` Video**: Linked in the video description for viewers seeking more detail on using `uv`.
- **Interactive API Documentation Routes**:
  - Swagger UI: `http://localhost:8000/docs`
  - ReDoc: `http://localhost:8000/redoc`
- _Note: Specific external URL strings beyond transcript descriptions are not explicitly detailed in the provided source text._

---

## 10. Key Takeaways

1. FastAPI applications are initialized with `app = FastAPI()`.
2. `fastapi dev` executes a local development server with auto-reload upon file saving.
3. `fastapi run` serves the application optimized for production environments.
4. Interactive Swagger UI API documentation is generated automatically at `/docs`.
5. An alternative ReDoc documentation interface is generated automatically at `/redoc`.
6. Returning Python lists or dictionaries automatically serializes them into JSON output.
7. `HTMLResponse` must be imported from `fastapi.responses` to return web page HTML.
8. Set `response_class=HTMLResponse` in decorators to deliver HTML headers.
9. Multiple `@app.get()` decorators can be stacked on one function to handle multiple paths.
10. Use `include_in_schema=False` to hide non-API routes from Swagger UI and ReDoc.
11. Swagger UI produces `curl` commands for testing endpoints directly in terminals.
12. `uv` provides faster package management, while `pip` remains fully functional.
13. Temporary in-memory list datasets allow testing endpoints prior to database setup.

---

## 11. Quick Reference

### CLI Commands

```bash
# Create project using uv
uv init fastAPI_blog
cd fastAPI_blog

# Start development server (auto-reload enabled)
fastapi dev

# Start production server
fastapi run
```

### Key Imports

```python
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
```

### Common Patterns

```python
# JSON REST API Route
@app.get("/api/posts")
def get_posts():
    return posts

# HTML Web Route with Schema Exclusion & Stacked Paths
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/posts", response_class=HTMLResponse, include_in_schema=False)
def home():
    return "<h1>Hello World</h1>"
```

### Default Local URLs

- Root Application: `http://localhost:8000/`
- Swagger UI Docs: `http://localhost:8000/docs`
- ReDoc Docs: `http://localhost:8000/redoc`

---

## 12. Mental Model

- **Core Execution Flow**:
  1. The `FastAPI` app instance acts as the core router and engine.
  2. `@app.get()` decorators register specific URL path endpoints and HTTP verbs to Python handler functions.
  3. Handler function return values determine output serialization: returning Python data structures outputs JSON, while returning strings with `response_class=HTMLResponse` outputs HTML.
  4. Metadata from route definitions automatically populates OpenAPI schemas for `/docs` (Swagger UI) and `/redoc`.
  5. The `include_in_schema=False` parameter filters out presentation/HTML routes, keeping the OpenAPI documentation focused purely on the programmatic REST API interface.
