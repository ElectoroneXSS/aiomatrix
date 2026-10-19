"""Lightweight response/update models. Provider-specific fields remain in ``raw``."""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class User:
    id: Any = None
    is_bot: Optional[bool] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data):
        data = data if isinstance(data, dict) else {}
        display = data.get("display_name") or data.get("displayName") or data.get("name")
        return cls(
            id=data.get("id", data.get("user_id")),
            is_bot=data.get("is_bot", data.get("isBot")),
            first_name=data.get("first_name", data.get("firstName", display)),
            last_name=data.get("last_name", data.get("lastName")),
            username=data.get("username", data.get("user_name")),
            language_code=data.get("language_code", data.get("languageCode")),
            raw=data,
        )


@dataclass
class Chat:
    id: Any = None
    type: Optional[str] = None
    title: Optional[str] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data):
        data = data if isinstance(data, dict) else {}
        return cls(
            id=data.get("id", data.get("chat_id", data.get("conversation_id"))),
            type=data.get("type", data.get("chat_type")),
            title=data.get("title", data.get("name")),
            username=data.get("username", data.get("user_name")),
            first_name=data.get("first_name", data.get("firstName")),
            raw=data,
        )


@dataclass
class Message:
    message_id: Any = None
    date: Any = None
    chat: Optional[Chat] = None
    from_user: Optional[User] = None
    text: Optional[str] = None
    caption: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False)
    _bot: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data, bot=None):
        data = data if isinstance(data, dict) else {}
        sender = data.get("from") or data.get("from_user") or data.get("sender") or data.get("author")
        chat_data = data.get("chat")
        if not isinstance(chat_data, dict):
            chat_id = data.get("chat_id", data.get("conversation_id", data.get("peer_id")))
            chat_data = {"id": chat_id, "type": data.get("chat_type")} if chat_id is not None else None
        if not isinstance(sender, dict):
            sender_id = data.get("from_id", data.get("user_id", data.get("sender_id")))
            sender = {"id": sender_id} if sender_id is not None else None
        return cls(
            message_id=data.get("message_id", data.get("messageId", data.get("id"))),
            date=data.get("date", data.get("timestamp")),
            chat=Chat.from_dict(chat_data) if isinstance(chat_data, dict) else None,
            from_user=User.from_dict(sender) if isinstance(sender, dict) else None,
            text=data.get("text", data.get("message_text")),
            caption=data.get("caption"),
            raw=data,
            _bot=bot,
        )

    @property
    def from_(self): return self.from_user

    @property
    def chat_id(self): return self.chat.id if self.chat else None

    @property
    def user_id(self): return self.from_user.id if self.from_user else None

    @property
    def chat_type(self): return self.chat.type if self.chat else None

    async def answer(self, text, **kwargs):
        if self._bot is None or self.chat is None:
            raise RuntimeError("Message is not bound to a Bot or has no chat")
        return await self._bot.send_message(self.chat.id, text, **kwargs)

    async def reply(self, text, **kwargs):
        kwargs.setdefault("reply_to_message_id", self.message_id)
        return await self.answer(text, **kwargs)

    async def delete(self):
        if self._bot is None or self.chat is None:
            raise RuntimeError("Message is not bound to a Bot")
        return await self._bot.delete_message(self.chat.id, self.message_id)


@dataclass
class Update:
    update_id: Any = None
    message: Optional[Message] = None
    edited_message: Optional[Message] = None
    channel_post: Optional[Message] = None
    edited_channel_post: Optional[Message] = None
    callback_query: Optional[dict] = None
    inline_query: Optional[dict] = None
    poll: Optional[dict] = None
    poll_answer: Optional[dict] = None
    my_chat_member: Optional[dict] = None
    chat_member: Optional[dict] = None
    message_reaction: Optional[dict] = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data, bot=None):
        data = data if isinstance(data, dict) else {}
        message_keys = (
            "message", "edited_message", "channel_post", "edited_channel_post"
        )
        message_values = {
            key: Message.from_dict(data[key], bot) if isinstance(data.get(key), dict) else None
            for key in message_keys
        }
        update_id = data.get("update_id", data.get("updateId", data.get("id")))
        known = {
            "callback_query", "inline_query", "poll", "poll_answer",
            "my_chat_member", "chat_member", "message_reaction",
        }
        extra = {key: data.get(key) for key in known}
        return cls(update_id=update_id, raw=data, **message_values, **extra)


@dataclass
class InlineKeyboardButton:
    text: str
    callback_data: Optional[str] = None
    url: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False)

    def to_dict(self):
        d = {"text": self.text}
        if self.callback_data is not None: d["callback_data"] = self.callback_data
        if self.url is not None: d["url"] = self.url
        d.update(self.raw)
        return d


@dataclass
class InlineKeyboardMarkup:
    inline_keyboard: list
    def to_dict(self):
        return {"inline_keyboard": [[b.to_dict() if hasattr(b, "to_dict") else b for b in row] for row in self.inline_keyboard]}


@dataclass
class KeyboardButton:
    text: str
    request_contact: Optional[bool] = None
    request_location: Optional[bool] = None
    raw: dict = field(default_factory=dict, repr=False)

    def to_dict(self):
        d = {"text": self.text}
        if self.request_contact is not None: d["request_contact"] = self.request_contact
        if self.request_location is not None: d["request_location"] = self.request_location
        d.update(self.raw)
        return d


@dataclass
class ReplyKeyboardMarkup:
    keyboard: list
    resize_keyboard: bool = True
    one_time_keyboard: Optional[bool] = None
    is_persistent: Optional[bool] = None

    def to_dict(self):
        d = {"keyboard": [[b.to_dict() if hasattr(b, "to_dict") else b for b in row] for row in self.keyboard], "resize_keyboard": self.resize_keyboard}
        if self.one_time_keyboard is not None: d["one_time_keyboard"] = self.one_time_keyboard
        if self.is_persistent is not None: d["is_persistent"] = self.is_persistent
        return d


@dataclass
class ReplyKeyboardRemove:
    remove_keyboard: bool = True
    def to_dict(self): return {"remove_keyboard": self.remove_keyboard}


@dataclass
class ForceReply:
    force_reply: bool = True
    selective: Optional[bool] = None
    input_field_placeholder: Optional[str] = None

    def to_dict(self):
        d = {"force_reply": self.force_reply}
        if self.selective is not None: d["selective"] = self.selective
        if self.input_field_placeholder is not None: d["input_field_placeholder"] = self.input_field_placeholder
        return d


@dataclass
class BotCommand:
    command: str
    description: str
    def to_dict(self): return {"command": self.command, "description": self.description}


# Rubika-style inline glass keypad models. Color is a provider-specific extension.
GLASS_COLORS = {
    "primary": "#2563EB", "success": "#16A34A", "danger": "#DC2626",
    "warning": "#D97706", "info": "#0891B2", "purple": "#7C3AED",
    "pink": "#DB2777", "gray": "#6B7280",
}


@dataclass
class GlassButton:
    button_id: str
    text: str
    color: Optional[str] = None
    button_type: str = "Simple"
    url: Optional[str] = None
    extra: dict = field(default_factory=dict, repr=False)

    def to_dict(self):
        if not self.button_id or not self.text:
            raise ValueError("button_id and text must be non-empty")
        result = {"id": self.button_id, "type": self.button_type, "button_text": self.text}
        if self.url is not None: result["url"] = self.url
        if self.color is not None:
            result["button_color"] = GLASS_COLORS.get(self.color.lower(), self.color)
        result.update(self.extra)
        return result


@dataclass
class GlassKeyboard:
    rows: list
    resize_keyboard: bool = True
    one_time_keyboard: bool = False

    def to_dict(self):
        out_rows = []
        for row in self.rows:
            buttons = [b.to_dict() if hasattr(b, "to_dict") else b for b in row]
            out_rows.append({"buttons": buttons})
        return {"rows": out_rows, "resize_keyboard": self.resize_keyboard, "one_time_keyboard": self.one_time_keyboard}

    @classmethod
    def builder(cls, *, resize_keyboard=True, one_time_keyboard=False):
        return GlassKeyboardBuilder(resize_keyboard=resize_keyboard, one_time_keyboard=one_time_keyboard)


class GlassKeyboardBuilder:
    def __init__(self, *, resize_keyboard=True, one_time_keyboard=False):
        self.rows = []
        self._resize = resize_keyboard
        self._one_time = one_time_keyboard

    def row(self, *buttons):
        if not buttons: raise ValueError("a keyboard row must contain at least one button")
        self.rows.append(list(buttons))
        return self

    def button(self, button_id, text, *, color=None, button_type="Simple", url=None, **extra):
        return GlassButton(str(button_id), str(text), color, button_type, url, extra)

    def build(self):
        return GlassKeyboard(self.rows, self._resize, self._one_time)
