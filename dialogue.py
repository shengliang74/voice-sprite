"""Explicit spoken preferences, stored separately from persona and credentials."""
import json
import os
import re
import tempfile


class PreferenceError(Exception):
    pass


def language_request(text, name):
    """Recognize polite standalone requests, not quoted text or language questions."""
    text = text.strip().strip('。！？.!?').strip()
    text = re.sub(r'^' + re.escape(name) + r'[，,、\s]*', '', text)
    chinese = re.sub(r'\s+', '', text)
    prefix = r'(?:(?:请|麻烦你|麻烦|你|我们|咱们|接下来|以后|现在|能不能|能否|可以|可不可以|能|我想|我想要)[，,]*)*'
    suffix = r'(?:回答(?:我)?|跟我聊天|和我聊天|跟我说话|和我说话|聊天|交流|聊|说|再说一遍|解释)?(?:好吗|好不好|可以吗|吧|呀|吗|啊|呢|了)*'
    match = re.fullmatch(prefix + r'(?:用|改用|换成|换回|切换成|切换到|切回|说)(中文|汉语|普通话|英文|英语)' + suffix, chinese)
    if not match:
        match = re.fullmatch(prefix + r'(?:练习|练)(英语|英文)' + r'(?:吧|呀|吗)?', chinese)
    if match:
        return 'en' if match.group(1) in ('英语', '英文') else 'zh'
    match = re.fullmatch(
        r"(?:(?:could you|can you|would you|please|let's|let us|from now on)\s+)*"
        r'(?:switch to|speak|answer in|reply in|respond in|talk in|chat in)\s+'
        r'(english|chinese)(?:\s+(?:please|with me))?', text, re.I)
    if match:
        return 'en' if match.group(1).lower() == 'english' else 'zh'
    return None


class Preferences:
    def __init__(self, path):
        self.path = path
        self.language, self.name, self.role = 'zh', '小灵', '儿童知识伙伴'
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if (not isinstance(data, dict) or data.get('language') not in ('zh', 'en')
                        or not all(isinstance(data.get(k), str) and 1 <= len(data[k]) <= 24
                                   for k in ('name', 'role'))):
                    raise ValueError('invalid preferences')
                self.language, self.name, self.role = data['language'], data['name'], data['role']
            except (OSError, ValueError) as exc:
                raise PreferenceError('无法读取 conversation.json，请检查或移走该文件后重试') from exc

    def handle(self, text):
        text = text.strip().strip('。！？.!?').strip()
        language = language_request(text, self.name)
        field, value = ('language', language) if language else (None, None)
        rename = re.fullmatch(r'(?:以后你叫|你的名字改成|把你的名字改成|我给你起名叫|你叫)([\w\u4e00-\u9fff -]{1,24})', text)
        rename_en = re.fullmatch(r'(?:your name is|change your name to) ([\w -]{1,24})', text, re.I)
        role = re.fullmatch(r'(?:切换成|切换为|你现在是|请扮演)([\w\u4e00-\u9fff -]{1,24})', text)
        if field is None and (rename or rename_en):
            field, value = 'name', (rename or rename_en).group(1).strip()
        elif field is None and role:
            field, value = 'role', role.group(1).strip()
        if field is None or not value:
            return None
        data = {'language': self.language, 'name': self.name, 'role': self.role}
        data[field] = value
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             delete=False) as out:
                temporary = out.name
                json.dump(data, out, ensure_ascii=False)
            os.replace(temporary, self.path)
        except OSError as exc:
            raise PreferenceError('无法保存对话设置，请检查项目目录写权限') from exc
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        setattr(self, field, value)
        if self.language == 'en':
            return {'language': "I'll answer in English.", 'name': f'My name is now {self.name}.',
                    'role': f"I'll be your {self.role}."}[field]
        return {'language': '好的，接下来我用中文回答。', 'name': f'好的，以后我叫{self.name}。',
                'role': f'好的，我现在扮演{self.role}。'}[field]

    def instruction(self):
        return ('当前用户选择的设置优先于人设中的旧名字和语言要求。\n'
                + json.dumps({'名字': self.name, '角色': self.role,
                              '回答语言': '中文' if self.language == 'zh' else 'English'}, ensure_ascii=False)
                + '\n按所选语言回答；角色扮演中也要区分事实与想象，不确定时坦诚说明。')
