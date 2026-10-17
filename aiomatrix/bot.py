"""Async client for Telegram-like bot APIs (including compatible providers)."""
import asyncio, json, logging, random
from urllib.parse import quote
import aiohttp
from .exceptions import APIError, NetworkError, ValidationError, RetryAfter
from .types import Update, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply
log=logging.getLogger('aiomatrix')

def _plain(value):
    if hasattr(value,'to_dict'): return value.to_dict()
    if isinstance(value,dict): return {k:_plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [_plain(v) for v in value]
    return value

class Bot:
    """Async Bot API client. Default URL format is ``{api_base}/{token}/{method}``.

    ``api_base`` is the provider's base path, not including token or method.
    The client never logs token-bearing URLs.
    """
    def __init__(self, token, *, api_base='https://abarsayeh.ir/bot', timeout=30,
                 session=None, default_parse_mode=None, max_concurrency=20,
                 retries=0, retry_backoff=0.35, headers=None):
        if not isinstance(token,str) or not token.strip(): raise ValidationError('token must be a non-empty string')
        if timeout <= 0: raise ValidationError('timeout must be positive')
        self.token=token.strip(); self.api_base=api_base.rstrip('/')
        self.timeout=aiohttp.ClientTimeout(total=timeout); self._session=session
        self._owns_session=session is None; self.default_parse_mode=default_parse_mode
        self._semaphore=asyncio.Semaphore(max(1,int(max_concurrency))); self.retries=max(0,int(retries))
        self.retry_backoff=max(0.0,float(retry_backoff)); self.headers=headers or {}
    async def __aenter__(self): await self._ensure_session(); return self
    async def __aexit__(self,*exc): await self.close()
    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session=aiohttp.ClientSession(timeout=self.timeout,headers=self.headers); self._owns_session=True
    def _url(self,method):
        method=str(method).strip('/')
        if not method or '/' in method: raise ValidationError('method must be a single method name')
        return f'{self.api_base}/{quote(self.token,safe=":")}/{quote(method,safe="")}'
    async def call(self, method, *, data=None, json_data=None, http_method='POST', params=None):
        """Call any provider method, including methods not yet wrapped by aiomatrix."""
        await self._ensure_session(); method=str(method)
        if json_data is not None: json_data=_plain(json_data)
        if data is not None: data=_plain(data)
        attempts=self.retries+1
        async with self._semaphore:
            for attempt in range(attempts):
                try:
                    async with self._session.request(http_method.upper(),self._url(method),data=data,json=json_data,params=params) as resp:
                        status=resp.status; body=await resp.text()
                        try: payload=json.loads(body) if body else {}
                        except json.JSONDecodeError as e: raise APIError('non-JSON response: '+body[:300],method=method,status=status) from e
                        if status==429 or (isinstance(payload,dict) and payload.get('error_code')==429):
                            retry_after=(payload.get('parameters') or {}).get('retry_after',1) if isinstance(payload,dict) else 1
                            err=RetryAfter('rate limited',retry_after=retry_after,method=method,status=status,payload=payload,error_code=429)
                            if attempt+1<attempts:
                                await asyncio.sleep(err.retry_after); continue
                            raise err
                        if status>=400: raise APIError((payload.get('description') or payload.get('message') or str(payload)) if isinstance(payload,dict) else str(payload),method=method,status=status,payload=payload,error_code=payload.get('error_code') if isinstance(payload,dict) else None)
                        if isinstance(payload,dict) and payload.get('ok') is False:
                            raise APIError(payload.get('description') or payload.get('message') or 'API returned ok=false',method=method,status=status,payload=payload,error_code=payload.get('error_code'))
                        return payload.get('result') if isinstance(payload,dict) and 'result' in payload else payload
                except asyncio.CancelledError: raise
                except (APIError,RetryAfter): raise
                except (aiohttp.ClientError,asyncio.TimeoutError) as e:
                    if attempt+1>=attempts: raise NetworkError(f'{method}: {type(e).__name__}: {e}') from e
                    await asyncio.sleep(self.retry_backoff*(2**attempt)+random.random()*0.1)
    async def close(self):
        if self._session is not None and self._owns_session and not self._session.closed: await self._session.close()
    async def get_me(self): return await self.call('getMe',http_method='GET')
    async def send_message(self,chat_id,text,**kwargs):
        p={'chat_id':chat_id,'text':text};
        if self.default_parse_mode and 'parse_mode' not in kwargs:p['parse_mode']=self.default_parse_mode
        p.update(kwargs); return await self.call('sendMessage',json_data=p)
    async def get_updates(self,*,offset=None,limit=100,timeout=20,allowed_updates=None):
        p={'limit':limit,'timeout':timeout}
        if offset is not None:p['offset']=offset
        if allowed_updates is not None:p['allowed_updates']=allowed_updates
        result=await self.call('getUpdates',json_data=p)
        if result is None:return []
        if not isinstance(result,list):
            if isinstance(result,dict) and isinstance(result.get('updates'),list): result=result['updates']
            else: raise APIError('getUpdates result is not a list',method='getUpdates',payload=result)
        return [Update.from_dict(x,bot=self) for x in result if isinstance(x,dict)]
    async def get_chat(self,chat_id): return await self.call('getChat',json_data={'chat_id':chat_id})
    async def get_chat_member(self,chat_id,user_id): return await self.call('getChatMember',json_data={'chat_id':chat_id,'user_id':user_id})
    async def get_chat_administrators(self,chat_id): return await self.call('getChatAdministrators',json_data={'chat_id':chat_id})
    async def get_chat_member_count(self,chat_id): return await self.call('getChatMemberCount',json_data={'chat_id':chat_id})
    async def get_chat_members_count(self,chat_id): return await self.get_chat_member_count(chat_id)
    async def edit_message_text(self,chat_id,message_id,text,**kwargs): return await self.call('editMessageText',json_data={'chat_id':chat_id,'message_id':message_id,'text':text,**kwargs})
    async def edit_message_caption(self,chat_id,message_id,caption,**kwargs): return await self.call('editMessageCaption',json_data={'chat_id':chat_id,'message_id':message_id,'caption':caption,**kwargs})
    async def edit_message_reply_markup(self,chat_id,message_id,reply_markup=None,**kwargs): return await self.call('editMessageReplyMarkup',json_data={'chat_id':chat_id,'message_id':message_id,'reply_markup':reply_markup,**kwargs})
    async def delete_message(self,chat_id,message_id): return await self.call('deleteMessage',json_data={'chat_id':chat_id,'message_id':message_id})
    async def forward_message(self,chat_id,from_chat_id,message_id,**kwargs): return await self.call('forwardMessage',json_data={'chat_id':chat_id,'from_chat_id':from_chat_id,'message_id':message_id,**kwargs})
    async def copy_message(self,chat_id,from_chat_id,message_id,**kwargs): return await self.call('copyMessage',json_data={'chat_id':chat_id,'from_chat_id':from_chat_id,'message_id':message_id,**kwargs})
    async def send_photo(self,chat_id,photo,**kwargs): return await self.call('sendPhoto',json_data={'chat_id':chat_id,'photo':photo,**kwargs})
    async def send_audio(self,chat_id,audio,**kwargs): return await self.call('sendAudio',json_data={'chat_id':chat_id,'audio':audio,**kwargs})
    async def send_document(self,chat_id,document,**kwargs): return await self.call('sendDocument',json_data={'chat_id':chat_id,'document':document,**kwargs})
    async def send_video(self,chat_id,video,**kwargs): return await self.call('sendVideo',json_data={'chat_id':chat_id,'video':video,**kwargs})
    async def send_animation(self,chat_id,animation,**kwargs): return await self.call('sendAnimation',json_data={'chat_id':chat_id,'animation':animation,**kwargs})
    async def send_voice(self,chat_id,voice,**kwargs): return await self.call('sendVoice',json_data={'chat_id':chat_id,'voice':voice,**kwargs})
    async def send_video_note(self,chat_id,video_note,**kwargs): return await self.call('sendVideoNote',json_data={'chat_id':chat_id,'video_note':video_note,**kwargs})
    async def send_sticker(self,chat_id,sticker,**kwargs): return await self.call('sendSticker',json_data={'chat_id':chat_id,'sticker':sticker,**kwargs})
    async def send_location(self,chat_id,latitude,longitude,**kwargs): return await self.call('sendLocation',json_data={'chat_id':chat_id,'latitude':latitude,'longitude':longitude,**kwargs})
    async def send_contact(self,chat_id,phone_number,first_name,**kwargs): return await self.call('sendContact',json_data={'chat_id':chat_id,'phone_number':phone_number,'first_name':first_name,**kwargs})
    async def send_poll(self,chat_id,question,options,**kwargs): return await self.call('sendPoll',json_data={'chat_id':chat_id,'question':question,'options':options,**kwargs})
    async def send_dice(self,chat_id,**kwargs): return await self.call('sendDice',json_data={'chat_id':chat_id,**kwargs})
    async def send_chat_action(self,chat_id,action,**kwargs): return await self.call('sendChatAction',json_data={'chat_id':chat_id,'action':action,**kwargs})
    async def answer_callback_query(self,callback_query_id,**kwargs): return await self.call('answerCallbackQuery',json_data={'callback_query_id':callback_query_id,**kwargs})
    async def get_file(self,file_id): return await self.call('getFile',json_data={'file_id':file_id})
    async def ban_chat_member(self,chat_id,user_id,**kwargs): return await self.call('banChatMember',json_data={'chat_id':chat_id,'user_id':user_id,**kwargs})
    async def unban_chat_member(self,chat_id,user_id,**kwargs): return await self.call('unbanChatMember',json_data={'chat_id':chat_id,'user_id':user_id,**kwargs})
    async def restrict_chat_member(self,chat_id,user_id,permissions,**kwargs): return await self.call('restrictChatMember',json_data={'chat_id':chat_id,'user_id':user_id,'permissions':permissions,**kwargs})
    async def promote_chat_member(self,chat_id,user_id,**kwargs): return await self.call('promoteChatMember',json_data={'chat_id':chat_id,'user_id':user_id,**kwargs})
    async def set_chat_title(self,chat_id,title): return await self.call('setChatTitle',json_data={'chat_id':chat_id,'title':title})
    async def set_chat_description(self,chat_id,description): return await self.call('setChatDescription',json_data={'chat_id':chat_id,'description':description})
    async def set_chat_photo(self,chat_id,photo): return await self.call('setChatPhoto',json_data={'chat_id':chat_id,'photo':photo})
    async def delete_chat_photo(self,chat_id): return await self.call('deleteChatPhoto',json_data={'chat_id':chat_id})
    async def pin_chat_message(self,chat_id,message_id,**kwargs): return await self.call('pinChatMessage',json_data={'chat_id':chat_id,'message_id':message_id,**kwargs})
    async def unpin_chat_message(self,chat_id,message_id=None):
        p={'chat_id':chat_id};
        if message_id is not None:p['message_id']=message_id
        return await self.call('unpinChatMessage',json_data=p)
    async def unpin_all_chat_messages(self,chat_id): return await self.call('unpinAllChatMessages',json_data={'chat_id':chat_id})
    async def leave_chat(self,chat_id): return await self.call('leaveChat',json_data={'chat_id':chat_id})
    async def get_chat_administrators_count(self,chat_id): return len(await self.get_chat_administrators(chat_id))
    async def set_my_commands(self,commands,**kwargs): return await self.call('setMyCommands',json_data={'commands':[_plain(c) for c in commands],**kwargs})
    async def get_my_commands(self,**kwargs): return await self.call('getMyCommands',json_data=kwargs,http_method='GET')
    async def delete_my_commands(self,**kwargs): return await self.call('deleteMyCommands',json_data=kwargs)
    async def set_webhook(self,url,**kwargs): return await self.call('setWebhook',json_data={'url':url,**kwargs})
    async def delete_webhook(self,**kwargs): return await self.call('deleteWebhook',json_data=kwargs)
    async def get_webhook_info(self): return await self.call('getWebhookInfo',http_method='GET')
    async def get_user_profile_photos(self,user_id,**kwargs): return await self.call('getUserProfilePhotos',json_data={'user_id':user_id,**kwargs})
    async def create_chat_invite_link(self,chat_id,**kwargs): return await self.call('createChatInviteLink',json_data={'chat_id':chat_id,**kwargs})
    async def export_chat_invite_link(self,chat_id): return await self.call('exportChatInviteLink',json_data={'chat_id':chat_id})
    async def revoke_chat_invite_link(self,chat_id,invite_link): return await self.call('revokeChatInviteLink',json_data={'chat_id':chat_id,'invite_link':invite_link})
    async def get_sticker_set(self,name): return await self.call('getStickerSet',json_data={'name':name})
    async def get_chat_member_status(self,chat_id,user_id):
        result=await self.get_chat_member(chat_id,user_id)
        return result.get('status') if isinstance(result,dict) else None
    async def get_updates_raw(self,**kwargs):
        """Raw updates for API variants that return provider-specific fields."""
        result=await self.call('getUpdates',json_data=kwargs)
        if result is None:return []
        return result if isinstance(result,list) else result.get('updates',[]) if isinstance(result,dict) else []
    def __getattr__(self, name):
        """Fallback for newly added API methods: ``await bot.some_new_method(x=1)``.

        Explicit wrappers above provide friendly positional arguments. Unknown
        snake_case attributes map to the provider's camelCase method names.
        """
        if name.startswith('_') or name in {'token','api_base'}: raise AttributeError(name)
        parts=name.split('_')
        method=parts[0]+''.join(p[:1].upper()+p[1:] for p in parts[1:])
        async def dynamic_method(*args, **kwargs):
            if args:
                raise TypeError(f'{name} fallback accepts keyword arguments only; use bot.call({method!r}, json_data=...) for positional payloads')
            return await self.call(method,json_data=kwargs)
        dynamic_method.__name__=name
        return dynamic_method
    async def download_file(self,file_path):
        """Download a provider-returned file path; URL format may vary by provider."""
        await self._ensure_session(); url=file_path if str(file_path).startswith(('http://','https://')) else f'{self.api_base}/file/{quote(self.token,safe=":")}/{str(file_path).lstrip("/")} '
        url=url.strip()
        try:
            async with self._session.get(url) as r:
                if r.status>=400: raise APIError('file download failed',status=r.status,method='downloadFile')
                return await r.read()
        except (aiohttp.ClientError,asyncio.TimeoutError) as e: raise NetworkError(f'download: {type(e).__name__}') from e
