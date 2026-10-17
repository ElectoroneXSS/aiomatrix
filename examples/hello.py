import asyncio, os
from aiomatrix import Bot, Dispatcher, Router, filters

async def main():
    bot=Bot(os.environ['BOT_TOKEN'], api_base=os.getenv('BOT_API_BASE','https://abarsayeh.ir/bot'), retries=2)
    dp=Dispatcher(); router=Router()
    @router.message(filters.Command('start'))
    async def start(message): await message.answer('سلام! ربات آماده است ⚡')
    @router.message(filters.HasText())
    async def echo(message): await message.reply(message.text)
    dp.include_router(router)
    try: await dp.start_polling(bot)
    finally: await bot.close()
if __name__=='__main__': asyncio.run(main())
