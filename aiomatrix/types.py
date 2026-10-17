"""Small typed models. Unknown API fields remain available in ``raw``."""
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class User:
    id: Any = None; is_bot: Optional[bool] = None; first_name: Optional[str] = None
    last_name: Optional[str] = None; username: Optional[str] = None; language_code: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False)
    @classmethod
    def from_dict(cls, data):
        data = data or {}; return cls(**{k:data.get(k) for k in ('id','is_bot','first_name','last_name','username','language_code')}, raw=data)

@dataclass
class Chat:
    id: Any = None; type: Optional[str] = None; title: Optional[str] = None
    username: Optional[str] = None; first_name: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False)
    @classmethod
    def from_dict(cls, data):
        data=data or {}; return cls(**{k:data.get(k) for k in ('id','type','title','username','first_name')},raw=data)

@dataclass
class Message:
    message_id: Any = None; date: Any = None; chat: Optional[Chat] = None
    from_user: Optional[User] = None; text: Optional[str] = None; caption: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False); _bot: Any = field(default=None,repr=False,compare=False)
    @classmethod
    def from_dict(cls,data,bot=None):
        data=data or {}; sender=data.get('from') or data.get('from_user') or data.get('sender'); chat=data.get('chat')
        return cls(message_id=data.get('message_id',data.get('id')),date=data.get('date'),chat=Chat.from_dict(chat) if isinstance(chat,dict) else None,from_user=User.from_dict(sender) if isinstance(sender,dict) else None,text=data.get('text'),caption=data.get('caption'),raw=data,_bot=bot)
    @property
    def from_(self): return self.from_user
    @property
    def chat_id(self): return self.chat.id if self.chat else None
    @property
    def user_id(self): return self.from_user.id if self.from_user else None
    async def answer(self,text,**kwargs):
        if self._bot is None or self.chat is None: raise RuntimeError('Message is not bound to a Bot or has no chat')
        return await self._bot.send_message(self.chat.id,text,**kwargs)
    async def reply(self,text,**kwargs):
        kwargs.setdefault('reply_to_message_id',self.message_id); return await self.answer(text,**kwargs)
    async def delete(self):
        if self._bot is None or self.chat is None: raise RuntimeError('Message is not bound to a Bot')
        return await self._bot.delete_message(self.chat.id,self.message_id)

@dataclass
class Update:
    update_id: Any=None; message: Optional[Message]=None; edited_message: Optional[Message]=None
    channel_post: Optional[Message]=None; callback_query: Optional[dict]=None; inline_query: Optional[dict]=None
    raw: dict=field(default_factory=dict,repr=False)
    @classmethod
    def from_dict(cls,data,bot=None):
        data=data or {}; keys=('message','edited_message','channel_post')
        vals={k:(Message.from_dict(data[k],bot) if isinstance(data.get(k),dict) else None) for k in keys}
        return cls(update_id=data.get('update_id'),callback_query=data.get('callback_query'),inline_query=data.get('inline_query'),raw=data,**vals)

@dataclass
class InlineKeyboardButton:
    text: str; callback_data: Optional[str]=None; url: Optional[str]=None; raw: dict=field(default_factory=dict,repr=False)
    def to_dict(self):
        d={'text':self.text};
        if self.callback_data is not None:d['callback_data']=self.callback_data
        if self.url is not None:d['url']=self.url
        d.update(self.raw); return d
@dataclass
class InlineKeyboardMarkup:
    inline_keyboard: list
    def to_dict(self): return {'inline_keyboard':[[b.to_dict() if hasattr(b,'to_dict') else b for b in row] for row in self.inline_keyboard]}
@dataclass
class KeyboardButton:
    text: str; request_contact: Optional[bool]=None; request_location: Optional[bool]=None; raw: dict=field(default_factory=dict,repr=False)
    def to_dict(self):
        d={'text':self.text}
        if self.request_contact is not None:d['request_contact']=self.request_contact
        if self.request_location is not None:d['request_location']=self.request_location
        d.update(self.raw); return d
@dataclass
class ReplyKeyboardMarkup:
    keyboard: list; resize_keyboard: bool=True; one_time_keyboard: Optional[bool]=None; is_persistent: Optional[bool]=None
    def to_dict(self):
        d={'keyboard':[[b.to_dict() if hasattr(b,'to_dict') else b for b in row] for row in self.keyboard],'resize_keyboard':self.resize_keyboard}
        if self.one_time_keyboard is not None:d['one_time_keyboard']=self.one_time_keyboard
        if self.is_persistent is not None:d['is_persistent']=self.is_persistent
        return d
@dataclass
class ReplyKeyboardRemove:
    remove_keyboard: bool=True
    def to_dict(self): return {'remove_keyboard':self.remove_keyboard}
@dataclass
class ForceReply:
    force_reply: bool=True; selective: Optional[bool]=None; input_field_placeholder: Optional[str]=None
    def to_dict(self):
        d={'force_reply':self.force_reply}
        if self.selective is not None:d['selective']=self.selective
        if self.input_field_placeholder is not None:d['input_field_placeholder']=self.input_field_placeholder
        return d
@dataclass
class BotCommand:
    command: str; description: str
    def to_dict(self): return {'command':self.command,'description':self.description}
