# Changelog

## 0.4.0 — performance, HTTP reliability and API diagnostics

- Reworked the HTTP client around a reusable pooled `aiohttp` session with configurable connection limits, DNS cache, connection timeout, and overall timeout.
- Added request statistics (success/failure/rate-limit/retry/cache-hit counters and latency), bounded concurrency, safer retry rules, and rate-limit handling.
- Added a TTL/LRU data cache and short-lived `getMe` response caching by default; other API methods can be explicitly opted in.
- Avoided automatic retry of non-idempotent message sends after network/5xx errors by default, reducing duplicate-message risk.
- Added multipart file upload support for photo/audio/document/video/animation/voice/video-note/sticker and chat-photo methods when given a local path, bytes, or a file object.
- Added safe bounded file downloads and configurable provider-specific file URL templates.
- Added wrappers for media groups, venue, stop poll, delete messages, edit media, and chat permissions; dynamic snake_case wrappers remain available for provider-specific methods.
- Long polling now allows bounded concurrent dispatch of each batch, avoids an unbounded number of update tasks, waits for handlers before advancing the acknowledgement offset, and blocks duplicate pollers on the same bot instance.
- Improved response model parsing for common field-name variants and moved SQLite work off the event loop using `asyncio.to_thread`.
- Added offline HTTP protocol tests and an API probe script. The tests use a local mock server and do not claim remote-provider method support.

## 0.3.0
- Added RateLimiter, SQLiteStorage, Scheduler, glass-keypad models, middleware and router support.
- Added common messaging and moderation wrappers.
