import asyncio
from aiomatrix import GlassKeyboard, GlassKeyboardBuilder, GLASS_COLORS, SQLiteStorage, RateLimiter
from aiomatrix.types import InlineKeyboardButton, InlineKeyboardMarkup

def test_glass_keyboard_rubika_shape_and_color():
    builder = GlassKeyboard.builder()
    button = builder.button("go", "شروع", color="success")
    data = builder.row(button).build().to_dict()
    assert data["rows"][0]["buttons"][0] == {"id":"go", "type":"Simple", "button_text":"شروع", "button_color":GLASS_COLORS["success"]}

def test_telegram_keyboard_shape():
    data = InlineKeyboardMarkup([[InlineKeyboardButton("Open", callback_data="open")]]).to_dict()
    assert data["inline_keyboard"][0][0]["callback_data"] == "open"

def test_sqlite_storage(tmp_path):
    async def run():
        store=SQLiteStorage(str(tmp_path / "fsm.sqlite"))
        await store.set_state("u1", "name")
        await store.update_data("u1", name="Ali")
        assert await store.get_state("u1") == "name"
        assert await store.get_data("u1") == {"name":"Ali"}
        await store.clear("u1")
        assert await store.get_state("u1") is None
    asyncio.run(run())

def test_rate_limiter_validation():
    try: RateLimiter(0)
    except ValueError: pass
    else: assert False
