# aiomatrix

کتابخانه async پایتون برای APIهای ربات با ساختار شبیه Telegram Bot API و تجربه توسعه الهام‌گرفته از aiogram.

> این پروژه نسخه اولیه است، نه کپی کامل یا جایگزین رسمی aiogram. سازگاری کامل با تمام متدهای Telegram یا آبارسایه تضمین نمی‌شود. مسیرها، پارامترها، کیبوردها و polling باید با API مقصد تأیید شوند.

## نصب

```bash
pip install .
```

یا فقط وابستگی را نصب کن:

```bash
pip install aiohttp
```

## مثال polling

```python
import asyncio
from aiomatrix import Bot, Dispatcher, Router
from aiomatrix.filters import Command

TOKEN = "PUT_YOUR_TOKEN_HERE"
router = Router()

@router.message(Command("start"))
async def start(message):
    await message.answer("سلام! ربات با aiomatrix فعال است.")

async def main():
    bot = Bot(TOKEN, api_base="https://abarsayeh.ir/bot")
    dp = Dispatcher()
    dp.include_router(router)
    try:
        await dp.start_polling(bot)  # نیازمند پشتیبانی API از getUpdates
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## فراخوانی مستقیم

```python
async with Bot("TOKEN", api_base="https://abarsayeh.ir/bot") as bot:
    me = await bot.get_me()
    print(me)
    await bot.send_message("CHAT_ID", "سلام")
    # متدهایی که wrapper ندارند:
    member = await bot.call("getChatMember", json_data={"chat_id": "CHAT_ID", "user_id": "USER_ID"})
```

## امکانات نسخه 0.1.0

- کلاینت HTTP ناهمگام مبتنی بر aiohttp
- مسیر پیش‌فرض `{api_base}/{token}/{method}`
- فراخوانی عمومی هر متد با `bot.call()`
- خطاهای ساخت‌یافته و عدم چاپ URL حاوی توکن
- Router / Dispatcher سبک و فیلترهای Command و Text
- مدل‌های پایه User، Chat، Message، Update
- مدل‌های Inline/Reply Keyboard به‌صورت عمومی
- wrapperهای getMe، sendMessage، getUpdates، setWebhook، getWebhookInfo، get/set/delete commands و getChatMember

## محدودیت‌ها

در این نسخه همه امکانات aiogram، FSM، middleware کامل، آپلود چندبخشی رسانه، تمام مدل‌ها و متدهای Bot API پیاده‌سازی نشده‌اند. `getUpdates` و `setWebhook` تنها وقتی کار می‌کنند که API مقصد واقعاً از آن‌ها پشتیبانی کند. HTTP ناامن است؛ از HTTPS معتبر استفاده کنید. این پروژه رسمی aiogram نیست و کد منبع آن را کپی نمی‌کند.
