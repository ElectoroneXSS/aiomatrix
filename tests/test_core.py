from aiomatrix import Bot, Message, Update, InlineKeyboardButton, InlineKeyboardMarkup, filters
from aiomatrix.utils import normalize_text, extract_command

def test_url_and_validation():
    b=Bot('abc',api_base='https://example.test/bot')
    assert b._url('getMe')=='https://example.test/bot/abc/getMe'
    try: b._url('bad/method')
    except ValueError: pass
    else: raise AssertionError('expected validation error')

def test_message_parse_and_command():
    m=Message.from_dict({'message_id':3,'chat':{'id':'c1','type':'private'},'from':{'id':'u1'},'text':'/start hi'})
    assert m.chat_id=='c1' and m.user_id=='u1'
    assert filters.Command('start')(m)

def test_update_keyboard_and_utils():
    u=Update.from_dict({'update_id':4,'message':{'chat':{'id':1},'text':'hi'}})
    assert u.update_id==4 and u.message.text=='hi'
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('go',url='https://example.com')]])
    assert kb.to_dict()['inline_keyboard'][0][0]['url']=='https://example.com'
    assert normalize_text('سلام ك ي')=='سلام ک ی'
    assert extract_command('/start hi')==('start',['hi'])
