import re

class Command:
    def __init__(self, *commands): self.commands = {str(c).lstrip('/').split('@')[0].lower() for c in commands}
    def __call__(self, message):
        text = getattr(message, 'text', None) or ''
        if not text.startswith('/'): return False
        parts = text[1:].split()
        return bool(parts) and parts[0].split('@')[0].lower() in self.commands

class Text:
    def __init__(self, text=None, *, contains=None, regexp=None, ignore_case=False):
        self.text, self.contains, self.ignore_case = text, contains, ignore_case
        self.regexp = re.compile(regexp, re.I if ignore_case else 0) if regexp else None
    def __call__(self, message):
        value = getattr(message, 'text', None) or ''
        if self.text is not None and ((value.lower() != self.text.lower()) if self.ignore_case else (value != self.text)): return False
        if self.contains is not None and self.contains not in value: return False
        if self.regexp is not None and not self.regexp.search(value): return False
        return True
