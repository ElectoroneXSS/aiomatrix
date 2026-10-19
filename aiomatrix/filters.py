"""Composable message filters."""
import re
class Filter:
    def __and__(self, other): return _Combined(self,other,all)
    def __or__(self, other): return _Combined(self,other,any)
    def __invert__(self): return _Not(self)
class _Combined(Filter):
    def __init__(self,a,b,fn): self.a,self.b,self.fn=a,b,fn
    def __call__(self,m): return self.fn((self.a(m),self.b(m)))
class _Not(Filter):
    def __init__(self,f): self.f=f
    def __call__(self,m): return not self.f(m)
class Command(Filter):
    def __init__(self,*commands,prefix='/'):
        self.commands={str(c).lstrip('/').split('@')[0].lower() for c in commands}; self.prefix=prefix
    def __call__(self,m):
        text=getattr(m,'text',None) or ''
        if not text.startswith(self.prefix):return False
        p=text[len(self.prefix):].split()
        return bool(p) and (not self.commands or p[0].split('@')[0].lower() in self.commands)
class Text(Filter):
    def __init__(self,text=None,*,contains=None,regexp=None,ignore_case=False):
        self.text,self.contains,self.ignore_case=text,contains,ignore_case
        self.regexp=re.compile(regexp,re.I if ignore_case else 0) if regexp else None
    def __call__(self,m):
        value=getattr(m,'text',None) or ''; compare=(lambda x:x.lower()) if self.ignore_case else (lambda x:x)
        if self.text is not None and compare(value)!=compare(self.text):return False
        if self.contains is not None and compare(self.contains) not in compare(value):return False
        return not self.regexp or bool(self.regexp.search(value))
class Regex(Text):
    def __init__(self,pattern,flags=0): self.pattern=re.compile(pattern,flags)
    def __call__(self,m): return bool(self.pattern.search(getattr(m,'text',None) or ''))
class ChatType(Filter):
    def __init__(self,*types): self.types=set(types)
    def __call__(self,m): return bool(getattr(getattr(m,'chat',None),'type',None) in self.types)
class Private(ChatType):
    def __init__(self): super().__init__('private')
class Group(ChatType):
    def __init__(self): super().__init__('group','supergroup')
class HasText(Filter):
    def __call__(self,m): return bool(getattr(m,'text',None))
class StartsWith(Filter):
    def __init__(self,prefix): self.prefix=prefix
    def __call__(self,m): return (getattr(m,'text',None) or '').startswith(self.prefix)
class FromUser(Filter):
    def __init__(self,*ids): self.ids={str(x) for x in ids}
    def __call__(self,m): return str(getattr(getattr(m,'from_user',None),'id',None)) in self.ids

class _HasMedia(Filter):
    field = None
    def __call__(self, message):
        raw = getattr(message, 'raw', {}) or {}
        return bool(raw.get(self.field))

class HasPhoto(_HasMedia):
    field = 'photo'

class HasDocument(_HasMedia):
    field = 'document'

class HasVideo(_HasMedia):
    field = 'video'

class HasAudio(_HasMedia):
    field = 'audio'

class HasSticker(_HasMedia):
    field = 'sticker'
