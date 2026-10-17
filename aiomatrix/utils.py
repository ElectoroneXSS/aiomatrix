"""Helpers for normalizing API payloads and command text."""
import re
_PERSIAN=str.maketrans({'ي':'ی','ك':'ک','ۀ':'ه','ة':'ه','ؤ':'و','إ':'ا','أ':'ا','ٱ':'ا'})
def normalize_text(text):
    text=str(text or '').translate(_PERSIAN).replace('\u200c',' ').replace('\u200f','').replace('\u200e','')
    return re.sub(r'\s+',' ',text).strip()
def chunks(items,size):
    if size<1: raise ValueError('size must be >= 1')
    for i in range(0,len(items),size): yield items[i:i+size]
def extract_command(text,prefix='/'):
    text=normalize_text(text)
    if not text.startswith(prefix):return None,[]
    parts=text[len(prefix):].split()
    if not parts:return None,[]
    return parts[0].split('@')[0].lower(),parts[1:]
