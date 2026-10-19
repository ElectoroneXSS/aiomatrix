"""Example of pooled HTTP connections and bounded concurrent update processing."""
import asyncio
import os
import logging

from aiomatrix import Bot, Dispatcher, Router, filters

logging.basicConfig(level=logging.INFO)

async def main():
    token = os.environ["BOT_TOKEN"]
    api_base = os.getenv("BOT_API_BASE", "https://abarsayeh.ir/bot")
    bot = Bot(
        token,
        api_base=api_base,
        timeout=35,
        max_concurrency=50,
        connection_limit=100,
        connection_limit_per_host=50,
        retries=2,
    )
    dispatcher = Dispatcher()
    router = Router()

    @router.message(filters.Command("start"))
    async def start(message):
        await message.answer("سلام! ربات سریع aiomatrix آماده است ⚡")

    @router.message(filters.HasText())
    async def echo(message):
        await message.reply(message.text)

    dispatcher.include_router(router)
    try:
        me = await bot.get_me()
        logging.info("Connected successfully; bot profile received: %s", me)
        await dispatcher.start_polling(bot, polling_timeout=20, limit=100, concurrency=20)
    finally:
        dispatcher.stop_polling()
        await bot.close()
        logging.info("HTTP stats: %s", bot.stats())

if __name__ == "__main__":
    asyncio.run(main())
