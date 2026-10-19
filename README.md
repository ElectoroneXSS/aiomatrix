# aiomatrix 0.4.0

**aiomatrix** is an asynchronous Python client and lightweight polling framework for Telegram-like bot APIs. Its default endpoint is Abarsayeh's API base, `https://abarsayeh.ir/bot`, using the route form:

```text
{api_base}/{BOT_TOKEN}/{METHOD}
```

API methods call the configured server over HTTP; responses in examples are not mocked by the library. **A wrapper existing in aiomatrix does not guarantee the remote server implements that method or accepts the same payload.** The provider's method list and custom fields must be verified against the actual API.

## Install

```bash
python -m pip install -U aiomatrix
```

For local development from this source tree:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

## Safely test the actual API

Never hardcode a bot token in source code or share it in chat. Set it as an environment variable:

```bash
export BOT_TOKEN='YOUR_NEW_TOKEN'
export BOT_API_BASE='https://abarsayeh.ir/bot'
python scripts_probe_api.py
```

The default probe calls only `getMe`. To deliberately test another method, pass the exact method and JSON payload. Some methods mutate the remote bot or chat, so only call methods you intend to test:

```bash
python scripts_probe_api.py --method getChat --params '{"chat_id":"@your_channel"}'
python scripts_probe_api.py --method getChatMember --params '{"chat_id":"@your_channel","user_id":123456789}'
python scripts_probe_api.py --method getUpdates --params '{"limit":1,"timeout":0}'
```

The last command reads the pending update queue. Do not run multiple pollers for the same bot. `getMe` is the safest first check; a successful request confirms that the token and base route are accepted, not that every Bot API method is available.

## Quick start: polling

```python
import asyncio
import os
from aiomatrix import Bot, Dispatcher, Router, filters

bot = Bot(
    os.environ["BOT_TOKEN"],
    api_base=os.getenv("BOT_API_BASE", "https://abarsayeh.ir/bot"),
    retries=2,
    max_concurrency=50,
    connection_limit=100,
)
dp = Dispatcher()
router = Router()

@router.message(filters.Command("start"))
async def start(message):
    await message.answer("سلام! aiomatrix فعال است ⚡")

@router.message(filters.Text(contains="سلام"))
async def greeting(message):
    await message.reply("سلام به شما 🌱")

async def main():
    dp.include_router(router)
    try:
        me = await bot.get_me()
        print("Bot connected:", me)
        await dp.start_polling(bot, polling_timeout=20, limit=100, concurrency=20)
    finally:
        dp.stop_polling()
        await bot.close()
        print("HTTP statistics:", bot.stats())

if __name__ == "__main__":
    asyncio.run(main())
```

## Performance and reliability

- One reusable `aiohttp.ClientSession` and a pooled TCP connector are used instead of opening an HTTP session for each request.
- DNS answers are cached, connection limits are configurable, and connect/overall timeouts are applied.
- Request concurrency is bounded by a semaphore. `Bot.stats()` exposes request, success, failure, retry, cache-hit, rate-limit, and latency counters without exposing the token.
- An in-process TTL/LRU cache is available. `getMe` is cached briefly by default; additional methods can be enabled explicitly with `cache_methods=("getMe", "getChat")` and a chosen `cache_ttl`. Do not cache rapidly changing or permission-sensitive responses for long periods. `TTLCache` is also exported for application data.
- `Dispatcher.start_polling(..., concurrency=20)` processes updates from each returned batch concurrently with a bounded semaphore. It waits for the batch's handlers before advancing the next polling offset.
- A second polling loop on the same `Bot` or `Dispatcher` instance is rejected.
- HTTP 429 is handled according to `retry_after`. Read-like methods and GET requests may retry transient network/5xx errors; message-sending methods do **not** automatically retry network/5xx failures by default, because the server might have processed a message even if the response was lost. Set `retry_non_idempotent=True` only if duplicate effects are acceptable.
- SQLite FSM operations use worker threads instead of blocking the event loop.
- File downloads have a configurable byte ceiling. File URL formats vary by provider; pass `file_url_template=` when the server uses a non-default route.


## Direct decorator API

For small bots, `Bot` also exposes convenience decorators without manually creating a `Dispatcher` and `Router`:

```python
import asyncio, os
from aiomatrix import Bot

bot = Bot(os.environ["BOT_TOKEN"])

@bot.command("start", "help")
async def start(message):
    await message.answer("سلام! aiomatrix فعال است ⚡")

@bot.on_message()
async def other_messages(message):
    if message.text:
        await message.reply(message.text)

async def main():
    try:
        await bot.run_polling(concurrency=20, polling_timeout=20)
    finally:
        bot.stop_polling()
        await bot.close()

asyncio.run(main())
```

The handlers in a single router are checked in registration order; the first matching handler in that router handles the event. Media shortcuts include `@bot.on_photo()`, `@bot.on_document()`, `@bot.on_video()`, and `@bot.on_audio()`.

## Direct API calls

```python
async with Bot(os.environ["BOT_TOKEN"]) as bot:
    me = await bot.get_me()
    sent = await bot.send_message("CHAT_ID", "Hello")
    chat = await bot.get_chat("CHAT_ID")
    # Provider-specific / newly released API methods can use the dynamic fallback:
    result = await bot.get_chat_member_count(chat_id="CHAT_ID")
    result = await bot.call("ExactProviderMethod", json_data={"custom_field": "value"})
```

Unknown snake_case methods map to camelCase (`bot.some_new_method(key="value")` calls `someNewMethod`). That fallback sends a real HTTP request and propagates the server's response/error; it does not simulate missing API functionality.

## Messages, media and keyboards

Common wrappers include `send_message`, `edit_message_text`, `edit_message_caption`, `edit_message_reply_markup`, `edit_message_media`, `delete_message`, `delete_messages`, `forward_message`, `copy_message`, `send_media_group`, `send_photo`, `send_audio`, `send_document`, `send_video`, `send_animation`, `send_voice`, `send_video_note`, `send_sticker`, `send_location`, `send_venue`, `send_contact`, `send_poll`, `stop_poll`, `send_dice`, and `send_chat_action`.

Media wrappers accept a provider file ID/URL as a string. A local file path, bytes, or file object uses multipart form upload. Upload support still depends on the provider's endpoint and maximum file size.

```python
from aiomatrix import InlineKeyboardButton, InlineKeyboardMarkup

keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("راهنما", callback_data="help"),
     InlineKeyboardButton("وب‌سایت", url="https://example.com")]
])
await bot.send_message("CHAT_ID", "یک گزینه انتخاب کن:", reply_markup=keyboard)
```

The library also has `GlassKeyboard`/`GlassButton` for provider-specific keypad formats:

```python
from aiomatrix import GlassKeyboard

keyboard = (GlassKeyboard.builder()
    .row(
        GlassKeyboard.builder().button("start", "شروع", color="success"),
        GlassKeyboard.builder().button("delete", "حذف", color="danger"),
    )
    .build())

await bot.send_message("CHAT_ID", "پنل:", inline_keypad=keyboard)
```

`button_color` and the `rows`/`inline_keypad` fields are provider-specific extensions; an API or client that doesn't support them may ignore or reject them. No client library can force a remote application to render unsupported button colors.

## Chat administration and configuration wrappers

Wrappers are provided for `get_chat`, `get_chat_member`, `get_chat_administrators`, `get_chat_member_count`, `ban_chat_member`, `unban_chat_member`, `restrict_chat_member`, `promote_chat_member`, `set_chat_permissions`, `set_chat_title`, `set_chat_description`, `set_chat_photo`, `delete_chat_photo`, `pin_chat_message`, `unpin_chat_message`, `unpin_all_chat_messages`, `leave_chat`, invite links, bot commands, webhooks, profile photos, files, and sticker sets.

These are **client-side wrappers**, not a promise that Abarsayeh's server has implemented every method. Call the specific method with correct chat identifiers and permissions; read `APIError.payload` to see the provider's actual error. A `CHAT_ID_INVALID` response may indicate the identifier format is wrong or the provider uses a different schema—being an administrator by itself does not prove the API has accepted the ID.

## Framework pieces

- `Router` and `Dispatcher` for message, edited-message, channel-post, callback-query, inline-query, and generic update handlers
- Filters: `Command`, `Text`, `Regex`, `ChatType`, `Private`, `Group`, `HasText`, `StartsWith`, `FromUser`, `HasPhoto`, `HasDocument`, `HasVideo`, `HasAudio`, `HasSticker`
- Middleware hooks
- `MemoryStorage` and `SQLiteStorage` FSM state/data stores
- `RateLimiter`, `TTLCache`, `Scheduler`, `normalize_text`, `extract_command`, and `chunks`
- Structured exceptions: `APIError`, `NetworkError`, `ValidationError`, `RetryAfter`
- MIT license and offline HTTP-protocol tests

## Version and compatibility

Python 3.9+; `aiohttp` is the only required third-party runtime dependency. Use Python 3.10+ if your own application uses modern union type syntax. Run `pytest` to exercise the local client and dispatcher tests. Those tests verify request construction, response parsing, retry safety, multipart uploads, and concurrent dispatch using a local test server; they are intentionally not represented as proof of Abarsayeh server-side method support.
