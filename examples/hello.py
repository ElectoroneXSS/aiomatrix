import asyncio
from aiomatrix import Bot, Dispatcher, Router
from aiomatrix.filters import Command

TOKEN = 'PUT_YOUR_TOKEN_HERE'
router = Router()

@router.message(Command('start'))
async def start(message):
    await message.answer('سلام! ربات با aiomatrix فعال است.')

@router.message(Command('id'))
async def show_id(message):
    await message.answer(f'Chat ID: {message.chat.id}')

async def main():
    bot = Bot(TOKEN, api_base='https://abarsayeh.ir/bot')
    dp = Dispatcher()
    dp.include_router(router)
    try:
        await dp.start_polling(bot)  # فقط اگر API از getUpdates پشتیبانی کند
    finally:
        await bot.close()

if __name__ == '__main__': asyncio.run(main())
