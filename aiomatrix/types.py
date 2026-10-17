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
        data = data or {}
        return cls(**{k: data.get(k) for k in ('id','is_bot','first_name','last_name','username','language_code')}, raw=data)

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
        data = data or {}
        return cls(**{k: data.get(k) for k in ('id','type','title','username','first_name')}, raw=data)

@dataclass
class Message:
    message_id: Any = None
    date: Any = None
    chat: Optional[Chat] = None
    from_user: Optional[User] = None
    text: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False)
    _bot: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data, bot=None):
        data = data or {}
        sender = data.get('from') or data.get('from_user') or data.get('sender')
        chat = data.get('chat')
        return cls(message_id=data.get('message_id', data.get('id')), date=data.get('date'),
                   chat=Chat.from_dict(chat) if isinstance(chat, dict) else None,
                   from_user=User.from_dict(sender) if isinstance(sender, dict) else None,
                   text=data.get('text'), raw=data, _bot=bot)

    @property
    def from_(self):
        return self.from_user

    async def answer(self, text, **kwargs):
        if self._bot is None or self.chat is None:
            raise RuntimeError('Message must be bound to a Bot and contain chat data')
        return await self._bot.send_message(self.chat.id, text, **kwargs)

    async def reply(self, text, **kwargs):
        return await self.answer(text, **kwargs)

@dataclass
class Update:
    update_id: Any = None
    message: Optional[Message] = None
    edited_message: Optional[Message] = None
    callback_query: Optional[dict] = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data, bot=None):
        data = data or {}
        msg, edited = data.get('message'), data.get('edited_message')
        return cls(update_id=data.get('update_id'),
                   message=Message.from_dict(msg, bot) if isinstance(msg, dict) else None,
                   edited_message=Message.from_dict(edited, bot) if isinstance(edited, dict) else None,
                   callback_query=data.get('callback_query'), raw=data)

@dataclass
class InlineKeyboardButton:
    text: str
    callback_data: Optional[str] = None
    url: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False)
    def to_dict(self):
        d = {'text': self.text}
        if self.callback_data is not None: d['callback_data'] = self.callback_data
        if self.url is not None: d['url'] = self.url
        d.update(self.raw)
        return d

@dataclass
class InlineKeyboardMarkup:
    inline_keyboard: list
    def to_dict(self):
        return {'inline_keyboard': [[b.to_dict() if hasattr(b, 'to_dict') else b for b in row] for row in self.inline_keyboard]}

@dataclass
class KeyboardButton:
    text: str
    request_contact: Optional[bool] = None
    request_location: Optional[bool] = None
    def to_dict(self):
        d = {'text': self.text}
        if self.request_contact is not None: d['request_contact'] = self.request_contact
        if self.request_location is not None: d['request_location'] = self.request_location
        return d

@dataclass
class ReplyKeyboardMarkup:
    keyboard: list
    resize_keyboard: bool = True
    one_time_keyboard: Optional[bool] = None
    is_persistent: Optional[bool] = None
    def to_dict(self):
        d = {'keyboard': [[b.to_dict() if hasattr(b, 'to_dict') else b for b in row] for row in self.keyboard], 'resize_keyboard': self.resize_keyboard}
        if self.one_time_keyboard is not None: d['one_time_keyboard'] = self.one_time_keyboard
        if self.is_persistent is not None: d['is_persistent'] = self.is_persistent
        return d
