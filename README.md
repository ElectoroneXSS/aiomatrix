# aiomatrix

**aiomatrix** is an asynchronous Python client and lightweight polling framework for Telegram-like Bot APIs. It is designed for compatible providers whose endpoint format is `{api_base}/{token}/{method}`. The default base URL is `https://abarsayeh.ir/bot`.

> Compatibility note: API providers do not necessarily implement the same methods or payload format. A wrapper existing in aiomatrix does not guarantee that the server supports it. Check the provider's docs and use `bot.call()` for provider-specific methods.

## Install

```bash
python -m pip install -U aiomatrix
```

## Quick start (polling)

```python
import asyncio
import os
from aiomatrix import Bot, Dispatcher, Router, filters

bot = Bot(os.environ["BOT_TOKEN"], api_base="https://abarsayeh.ir/bot", retries=2)
dp = Dispatcher()
router = Router()

@router.message(filters.Command("start"))
async def start(message):
    await message.answer("سلام! aiomatrix فعال است.")

@router.message(filters.Text(contains="سلام"))
async def greeting(message):
    await message.reply("سلام به شما 🌱")

async def main():
    dp.include_router(router)
    try:
        await dp.start_polling(bot, polling_timeout=20, retry_delay=2)
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
```

Set the token as an environment variable rather than hardcoding it:

```bash
export BOT_TOKEN='YOUR_TOKEN'
python main.py
```

## Direct API calls

```python
async with Bot(token, api_base="https://abarsayeh.ir/bot") as bot:
    me = await bot.get_me()
    await bot.send_message(chat_id="CHAT_ID", text="Hello", disable_web_page_preview=True)
    member = await bot.get_chat_member(chat_id="GROUP_ID", user_id="USER_ID")
    # API methods not wrapped explicitly are available using snake_case:
    result = await bot.get_chat_member_count(chat_id="GROUP_ID")
    custom = await bot.call("providerSpecificMethod", json_data={"key": "value"})
```

## Keyboard example

```python
from aiomatrix import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
inline = InlineKeyboardMarkup([[InlineKeyboardButton("Open", url="https://example.com")]])
reply = ReplyKeyboardMarkup([[{"text": "تست 👑"}, {"text": "راهنما"}]])
await bot.send_message(chat_id, "Choose:", reply_markup=inline)
```

## Included features

- Async HTTP session reuse, concurrency limit, timeout and optional transient-network retries.
- `get_updates()` and long-polling `Dispatcher` with offset management and graceful stop.
- Routers, ordered handlers, command/text/regex/chat-type/user filters, edited-message and callback update dispatch.
- Typed `User`, `Chat`, `Message`, `Update`, keyboard and command models.
- Message helpers: `answer`, `reply`, `delete`.
- Common messaging, media, chat/member moderation, invite-link, command, webhook, callback and poll methods.
- `bot.call()` and dynamic snake_case fallback for new/provider-specific API methods.
- `MemoryStorage` FSM utility, Persian/Arabic text normalization, structured API exceptions.

## API wrappers

The client includes wrappers such as `get_me`, `send_message`, `get_updates`, `get_chat`, `get_chat_member`, `get_chat_administrators`, `get_chat_member_count`, `send_photo`, `send_document`, `send_video`, `send_audio`, `send_voice`, `send_animation`, `send_sticker`, `send_location`, `send_contact`, `send_poll`, `send_dice`, `edit_message_text`, `edit_message_caption`, `edit_message_reply_markup`, `delete_message`, `forward_message`, `copy_message`, `ban_chat_member`, `unban_chat_member`, `restrict_chat_member`, `promote_chat_member`, `pin_chat_message`, `unpin_chat_message`, `create_chat_invite_link`, `set_my_commands`, `set_webhook`, and many more.

For any method not explicitly wrapped, use `await bot.call("ExactApiMethod", json_data={...})`. The fallback also maps `snake_case` names to `camelCase` API names and accepts keyword payloads.

## Errors and logging

- `APIError`: provider returned an API or HTTP error. Attributes: `method`, `status`, `payload`, `error_code`.
- `RetryAfter`: rate limit error and `retry_after` hint.
- `NetworkError`: transport or timeout error.
- `ValidationError`: invalid local arguments.

Tokens are not included in error messages or library logs. Avoid logging raw request URLs yourself.

## Important provider caveats

- Bot API clones vary. Some require `chat_id` to be a string; others require a numeric ID. Keep IDs exactly as supplied by the provider.
- File upload behavior differs between APIs. The convenience media methods send JSON payloads and work best with provider-supported file IDs/URLs. Multipart upload may require provider-specific handling.
- Callback queries are dispatched as dictionaries; provider-specific callback answer semantics may vary.
- The library defaults to polling; it does not automatically enable or configure a webhook.

## License

MIT
