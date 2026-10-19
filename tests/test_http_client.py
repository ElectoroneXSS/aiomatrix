"""Protocol-level tests use a local fake HTTP server; they never contact a real bot API."""
import asyncio
import json
from pathlib import Path

from aiohttp import web
import pytest

from aiomatrix import Bot, APIError, NetworkError, Dispatcher, Router, filters


def run(coro):
    return asyncio.run(coro)


async def start_server(handler):
    app = web.Application()
    app.router.add_route("*", "/bot/{token}/{method}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}/bot"


def test_real_http_route_and_get_me():
    seen = []

    async def handler(request):
        seen.append((request.method, request.match_info["token"], request.match_info["method"]))
        return web.json_response({"ok": True, "result": {"id": 7, "username": "demo"}})

    async def scenario():
        runner, base = await start_server(handler)
        async with Bot("12:secret", api_base=base, retries=0) as bot:
            me = await bot.get_me()
            assert me["username"] == "demo"
            assert bot.stats()["successes"] == 1
        await runner.cleanup()

    run(scenario())
    assert seen == [("GET", "12:secret", "getMe")]


def test_429_retry_and_safe_retry():
    state = {"calls": 0}

    async def handler(request):
        state["calls"] += 1
        if state["calls"] == 1:
            return web.json_response({"ok": False, "error_code": 429, "parameters": {"retry_after": 0.001}}, status=429)
        return web.json_response({"ok": True, "result": {"id": 1}})

    async def scenario():
        runner, base = await start_server(handler)
        async with Bot("test", api_base=base, retries=1, max_retry_after=0.01) as bot:
            result = await bot.get_me()
            assert result["id"] == 1
            assert bot.stats()["retries"] == 1
        await runner.cleanup()

    run(scenario())
    assert state["calls"] == 2


def test_non_idempotent_5xx_does_not_retry_to_avoid_duplicate_send():
    state = {"calls": 0}

    async def handler(request):
        state["calls"] += 1
        return web.json_response({"ok": False, "description": "server error"}, status=500)

    async def scenario():
        runner, base = await start_server(handler)
        async with Bot("test", api_base=base, retries=3) as bot:
            with pytest.raises(APIError):
                await bot.send_message(123, "hello")
        await runner.cleanup()

    run(scenario())
    assert state["calls"] == 1


def test_media_upload_uses_multipart(tmp_path):
    record = {}

    async def handler(request):
        record["method"] = request.match_info["method"]
        record["content_type"] = request.headers.get("Content-Type", "")
        form = await request.post()
        record["chat_id"] = form.get("chat_id")
        record["caption"] = form.get("caption")
        uploaded = form.get("photo")
        record["filename"] = uploaded.filename if uploaded else None
        record["bytes"] = uploaded.file.read() if uploaded else b""
        return web.json_response({"ok": True, "result": {"message_id": 2}})

    image_path = tmp_path / "image.bin"
    image_path.write_bytes(b"image-bytes")

    async def scenario():
        runner, base = await start_server(handler)
        async with Bot("test", api_base=base, retries=0) as bot:
            result = await bot.send_photo(55, image_path, caption="test caption")
            assert result["message_id"] == 2
        await runner.cleanup()

    run(scenario())
    assert record["method"] == "sendPhoto"
    assert record["content_type"].startswith("multipart/form-data;")
    assert record["chat_id"] == "55"
    assert record["caption"] == "test caption"
    assert record["filename"] == "image.bin"
    assert record["bytes"] == b"image-bytes"


def test_router_nested_and_concurrent_batch_dispatch():
    async def scenario():
        bot = type("FakeBot", (), {"_polling_active": False})()
        router = Router()
        dp = Dispatcher()
        dp.include_router(router)
        state = {"active": 0, "max_active": 0, "count": 0}

        @router.message(filters.Text(contains="go"))
        async def on_go(message):
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            await asyncio.sleep(0.02)
            state["active"] -= 1
            state["count"] += 1
            if state["count"] == 3:
                dp.stop_polling()

        batches = [[
            {"update_id": 1, "message": {"message_id": 1, "chat": {"id": 1, "type": "private"}, "text": "go 1"}},
            {"update_id": 2, "message": {"message_id": 2, "chat": {"id": 2, "type": "private"}, "text": "go 2"}},
            {"update_id": 3, "message": {"message_id": 3, "chat": {"id": 3, "type": "private"}, "text": "go 3"}},
        ]]

        async def get_updates(**kwargs):
            return batches.pop(0) if batches else []
        bot.get_updates = get_updates
        await asyncio.wait_for(dp.start_polling(bot, polling_timeout=0, retry_delay=0.1, concurrency=3), timeout=2)
        assert state["count"] == 3
        assert state["max_active"] > 1
        assert bot._polling_active is False

    run(scenario())


def test_bot_convenience_decorators_register_locally():
    bot = Bot("fake-token", retries=0)

    @bot.command("start")
    async def start(message):
        return message.text

    @bot.on_message()
    async def all_messages(message):
        return message.text

    @bot.on_callback_query()
    async def callback(query):
        return query.get("data")

    assert len(bot._local_dispatcher.message_handlers) == 2
    assert len(bot._local_dispatcher.callback_handlers) == 1


def test_get_me_cache_avoids_second_http_request():
    seen = {"calls": 0}

    async def handler(request):
        seen["calls"] += 1
        return web.json_response({"ok": True, "result": {"id": 9}})

    async def scenario():
        runner, base = await start_server(handler)
        async with Bot("test", api_base=base, cache_ttl=30) as bot:
            first = await bot.get_me()
            second = await bot.get_me()
            assert first == second == {"id": 9}
            assert bot.stats()["cache_hits"] == 1
            assert bot.stats()["requests"] == 1
        await runner.cleanup()

    run(scenario())
    assert seen["calls"] == 1


def test_ttl_cache_lru_and_copy_semantics():
    from aiomatrix import TTLCache
    cache = TTLCache(ttl=30, max_items=2)
    original = {"nested": [1]}
    cache.set("a", original)
    original["nested"].append(2)
    fetched = cache.get("a")
    assert fetched == {"nested": [1]}
    fetched["nested"].append(3)
    assert cache.get("a") == {"nested": [1]}
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert cache.stats()["evictions"] == 1
