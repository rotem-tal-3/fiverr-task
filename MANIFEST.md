# Task Manifest

## What works?

- DB Storage
- URL shortening (Tested the redirection using /testing endpoint)
- Stats

## What is missing?

Due to time:
 - i didn't build a mock DB for comprehensive testing.
 - I did not manually test the allowed domains.
 - I did not add authentication to any endpoint.
 - I did not check the validity of the incoming URL (see that it exists) other than the allowed domains test.
 

### DB Justification

PostgreSQL was chosen for its strong support for async drivers (asyncpg), reliable ACID transactions (critical for the concurrent redirect_count updates), and native `TIMESTAMP WITH TIME ZONE` handling. Its `GROUP BY` with `EXTRACT` makes the monthly earnings aggregation straightforward. For a URL shortener with click tracking, a relational DB is the natural fit — the ShortLink-to-ClickEvent relationship maps directly to a foreign key, and indexed lookups on `short_code` keep redirect latency low.


### Tradeoffs

**SHA-256 truncation for short codes.** We derive short codes deterministically from the target URL via truncated SHA-256 (8 hex chars = ~4 billion combinations). This guarantees idempotency — the same URL always produces the same code — and avoids a generate-then-check-for-collision loop. The tradeoff is that collisions between *different* URLs are theoretically possible (birthday problem), and the code space is limited to hexadecimal characters (0-9, a-f) rather than a denser alphabet like base62. For a production system at scale, a counter-based or base62 approach would yield shorter codes with zero collision risk, but at the cost of requiring coordination (e.g. a sequence or distributed ID generator). The abstract `ShortCodeGenerator` makes this a drop-in swap.

**Denormalized `redirect_count` on `ShortLink`.** We maintain a running counter directly on the `ShortLink` row rather than computing it from `COUNT(*)` on `ClickEvent`. This makes read-heavy operations (displaying stats, sorting by popularity) fast and avoids expensive aggregation queries. The tradeoff is write amplification — every valid click updates both the `ClickEvent` table and the `ShortLink` row — and the potential for drift if the background task fails between inserting the event and committing the count update (though both happen in the same transaction today). At higher scale, this counter could be moved to a cache (e.g. Redis) and periodically flushed.

**Fire-and-forget background tasks via `asyncio.create_task`.** Fraud detection runs as an unmanaged background coroutine so it never delays the redirect response. The tradeoff is that these tasks have no retry mechanism, no dead-letter queue, and no persistence — if the server shuts down mid-check, the click is silently lost. For a production system, a proper task queue (Celery, Dramatiq, or an async job runner with persistence) would provide reliability guarantees. The current approach is a pragmatic fit for the scope of this task.

**`SessionLocal` import in `_handle_fraud_check`.** The background fraud check creates its own database session via the module-level `SessionLocal` factory rather than receiving one through dependency injection. This is necessary because the task outlives the request lifecycle (FastAPI closes the request session after the response is sent). The tradeoff is that it creates a direct dependency on the module-level session factory, making unit tests require `unittest.mock.patch` rather than clean DI. An alternative would be injecting the session factory through `app.state`, consistent with the other strategies.

**Stats aggregation computed at query time.** Monthly earnings breakdowns are computed on every `/stats` request by grouping `ClickEvent` rows with `GROUP BY year, month`. This keeps the data model simple — no materialized views or pre-aggregated tables — and guarantees results are always consistent with the underlying data. The tradeoff is that query cost grows linearly with the number of click events. At scale, this would benefit from a materialized summary table updated on write, or from caching the aggregation results.

**Database credentials hardcoded in `session.py`.** The connection string is currently a literal in source code rather than loaded from environment variables via `Settings`. This was inherited from the initial boilerplate. In production, this should be moved to `config.py` and loaded from a `DATABASE_URL` env var, consistent with how `earning_per_click` and `allowed_domains` are handled.

**Domain allowlist uses exact hostname matching.** The `allowed_domains` check compares the parsed hostname literally, meaning `sub.example.com` is *not* covered by an entry for `example.com`. This is the more secure default (explicit over implicit), but means operators must list every subdomain individually. A suffix-based matching approach (e.g. `.example.com` covers all subdomains) could be added if needed.

### AI Usage

I used claude both from the extension window and the CLI. I have these instructions in the claude.md file:
'''
You are a senior developer. Your job is to help me produce clean, robust and scalable code, with emphasis on modularity and current best practices. Provide only code and docstrings on the functions, avoid adding comments inside the code. Each function and class should be documented including it's arguments/properties. 
When I give you a problem, I don't want the first solution that works. I want you to:
Question every assumption. Why does it have to work that way? What if we started from zero? What would the most elegant solution look like?
Sketch the architecture, create a clear and well-reasoned plan, emphasize modularity, scalability and separation of concerns
Think of edge cases and invalid inputs when implementing, assume the worst
If there's a way to remove complexity without losing power, find it. Elegance is achieved not when there's nothing left to add, but when there's nothing left to take away
Solve the *real* problem, not just the stated one
Leave the codebase better than you found it
'''


### Prompts

1)  the folder currently holds a placeholder for a DB, let's convert the hello world DB into a short link generatoer.
  create an endpoint the accept a target url and return a unique short url. if multiple request are made to generate      the same url, the answer should return the existing url. create another endpoint that redircts the short links to
  the original URL. each time the redirection is triggered, we need to simulate a fraud detection (pseudo funciton
  that runs for 500ms and return true or false with 50% prob) this fraud detection should not interfere with the
  redirection, we need to update a short link redirection on our database whenever a link redirects and passes the
  fraud test

  2) add a get stats endpoint, it should return a paginated list of all created links, where each link should have a
  report of performance, number of clicks and earnings, currently earnings are 0.05$ for each click, but create a         clean and scalable way to save this number (dont hardcode it). it should also include a grouped monthly report with
  the month and earning per month, and the url itself (total number of clicks and a monthly breakdown of earnings)

  3) add an abstract class for the fraud detection, implement the current detect fraud method in a class implementing the abstract class

  4) routes.py currently holds the link creation logic, create an abstract class to generate short links, move the current implementation to a class implementing the abstract class and use the app lifespan to DI the short link generator

  5) add the frauddetector the lifespan instead of the config

  6) create a test suite for the short code

  7) write tests for the routes file as well

  8 + 9) errors i got from the server for debugging

  10) in the config.py add allowed base addresses, whenever a post request is received verify that the link has the allowed base address

  11) in the stats JSON, the items should hold an array with jsons matching exactly the following fields:  'url':string (originial url), 'total_clicks":int, "total_earnings":float, "monthly_breakdown":array of jsons with "month" string (e.g. "12/2025"), earnings: float

12) in the readme i added an architecture subtitle, explain the architecture there (mention the abstract classes and lifespan, use of pydantic and anything you deem necessary)

13) I added a Testing subtitle, provide instructions of how to test this project, include the command to run automated tests,  and add jsons of the expected structure for post, alongside the expected return response, and the return response for stats and redirectionsmanual tests



