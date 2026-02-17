# Fiverr coding task implementation

### Run

Start docker with the command
```bash
docker compose up -d
```

Run the python server
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Configure

Configuration is managed through `app/config.py` using **Pydantic Settings** (`BaseSettings`), which reads values from environment variables or a `.env` file in the project root.

| Variable | Type | Default | Description |
|---|---|---|---|
| `EARNING_PER_CLICK` | `Decimal` | `0.05` | Revenue per valid click |
| `ALLOWED_DOMAINS` | `list[str]` | `[]` (all allowed) | Domain whitelist for target URLs |

Create a `.env` file in the project root to override defaults:

```env
EARNING_PER_CLICK=0.10
ALLOWED_DOMAINS=["example.com","mysite.org"]
```

When `ALLOWED_DOMAINS` is empty (the default), any domain is accepted. When populated, only URLs whose hostname exactly matches an entry in the list are allowed — subdomains must be listed explicitly.

### Architecture

The application is a FastAPI-based URL shortener with click tracking, fraud detection, and per-link earnings reporting.

#### Project layout

```
app/
  main.py           # FastAPI app entry point
  lifespan.py       # Startup/shutdown lifecycle — wires dependencies into app.state
  routes.py         # API endpoints (link creation, redirect, stats)
  config.py         # Pydantic Settings — env-driven configuration
  schemas.py        # Request/response models (Pydantic via SQLModel)
  fraud.py          # FraudDetector ABC + RandomFraudDetector implementation
  short_code.py     # ShortCodeGenerator ABC + Sha256ShortCodeGenerator implementation
  db/
    models.py       # SQLModel ORM models (ShortLink, ClickEvent)
    session.py      # Async SQLAlchemy engine and session factory
tests/
  conftest.py       # Shared fixtures (in-memory SQLite, test client, detector stubs)
  test_short_code.py
  test_routes.py
```

#### Strategy pattern and dependency injection

Pluggable behaviors are modeled as abstract base classes with swappable concrete implementations:

- **`FraudDetector`** (`fraud.py`) — Abstract async `detect()` method. The bundled `RandomFraudDetector` simulates an external service with configurable delay and threshold. Swap it for a real API-backed detector without touching route code.
- **`ShortCodeGenerator`** (`short_code.py`) — Abstract `generate(url)` method. The bundled `Sha256ShortCodeGenerator` produces deterministic codes via truncated SHA-256. Replace it with UUID-based, base62, or any custom scheme.

Both are instantiated in the **FastAPI lifespan** (`lifespan.py`) and attached to `app.state`, making them available to any request handler via `request.app.state`. This avoids global singletons for service-layer dependencies and makes testing trivial — tests inject stubs (e.g. `AlwaysLegitFraudDetector`) without patching internals.

#### Configuration

`config.py` uses **Pydantic Settings** (`BaseSettings`) to load configuration from environment variables or a `.env` file:

| Variable | Type | Default | Description |
|---|---|---|---|
| `EARNING_PER_CLICK` | `Decimal` | `0.05` | Revenue per valid click |
| `ALLOWED_DOMAINS` | `list[str]` | `[]` (all allowed) | Domain whitelist for target URLs |

#### Data model

Built with **SQLModel** (SQLAlchemy + Pydantic hybrid):

- **`ShortLink`** — Stores the target URL, generated short code, denormalized redirect count, and creation timestamp.
- **`ClickEvent`** — Records each valid (non-fraudulent) click with a foreign key to `ShortLink` and a UTC timestamp. Used for monthly earnings aggregation in the stats endpoint.

Both timestamp columns use `TIMESTAMP WITH TIME ZONE` for correct timezone handling with asyncpg.

#### Request flow

1. **`POST /links`** — Validates the target URL against the domain allowlist, checks for duplicates, generates a short code via the injected `ShortCodeGenerator`, and persists the link.
2. **`GET /{short_code}`** — Looks up the short code and returns a 307 redirect. Fires a background `asyncio.create_task` for fraud detection — the response is not delayed by the check.
3. **`GET /stats`** — Returns paginated per-link statistics with monthly earnings breakdowns, computed by aggregating `ClickEvent` rows grouped by month.

### Testing

#### Automated tests

The test suite uses pytest with an in-memory SQLite database (no PostgreSQL required). Install the test dependencies and run:

```bash
pip install pytest pytest-asyncio httpx aiosqlite
python -m pytest tests/ -v
```

#### Manual tests (Postman / cURL)

Make sure the server is running (`uvicorn app.main:app --reload`) and PostgreSQL is up (`docker compose up -d`).

---

**`POST /links`** — Create a short link

Request:
```json
{
  "target_url": "https://example.com/my-long-page"
}
```

Response (`201 Created`):
```json
{
  "id": 1,
  "target_url": "https://example.com/my-long-page",
  "short_code": "4cebf3d9",
  "short_url": "http://localhost:8000/4cebf3d9",
  "redirect_count": 0,
  "created_at": "2026-02-17T12:00:00.000000+00:00"
}
```

Posting the same `target_url` again returns the existing record (idempotent).

If `ALLOWED_DOMAINS` is configured and the domain is not whitelisted, the response is `403 Forbidden`:
```json
{
  "detail": "Domain 'evil.com' is not in the allowed domains list"
}
```

---

**`GET /{short_code}`** — Redirect to the original URL

Response (`307 Temporary Redirect`):
```
HTTP/1.1 307 Temporary Redirect
Location: https://example.com/my-long-page
```

A background fraud check runs asynchronously. If the check passes, the click is recorded; if not, it is silently discarded. The redirect is never delayed.

If the short code does not exist, the response is `404 Not Found`:
```json
{
  "detail": "Short link not found"
}
```

---

**`GET /stats`** — Paginated link statistics

Query parameters: `page` (default `1`), `page_size` (default `10`, max `100`).

Response (`200 OK`):
```json
{
  "page": 1,
  "page_size": 10,
  "total_links": 2,
  "items": [
    {
      "url": "https://example.com/my-long-page",
      "total_clicks": 5,
      "total_earnings": 0.25,
      "monthly_breakdown": [
        { "month": "1/2026", "earnings": 0.1 },
        { "month": "2/2026", "earnings": 0.15 }
      ]
    },
    {
      "url": "https://example.com/another-page",
      "total_clicks": 0,
      "total_earnings": 0.0,
      "monthly_breakdown": []
    }
  ]
}
```

Links with no clicks have an empty `monthly_breakdown` array and zeroed totals.

### AI Setup


I used claude Opus 4.6 both from the extension window and the CLI. I have these instructions in the claude.md file:

```
You are a senior developer. Your job is to help me produce clean, robust and scalable code, with emphasis on modularity and current best practices. Provide only code and docstrings on the functions, avoid adding comments inside the code. Each function and class should be documented including it's arguments/properties. 
When I give you a problem, I don't want the first solution that works. I want you to:
Question every assumption. Why does it have to work that way? What if we started from zero? What would the most elegant solution look like?
Sketch the architecture, create a clear and well-reasoned plan, emphasize modularity, scalability and separation of concerns
Think of edge cases and invalid inputs when implementing, assume the worst
If there's a way to remove complexity without losing power, find it. Elegance is achieved not when there's nothing left to add, but when there's nothing left to take away
Solve the *real* problem, not just the stated one
Leave the codebase better than you found it
```
