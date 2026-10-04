"""Deterministic instructions for the features actually supported by this app."""
import re
from dialogue import PreferenceError


def guide(name):
    return (f'我是{name}，可以陪你探索科学、讲故事，也可以练英语。'
            '想改我的名字，单独说“把你的名字改成小星星”。'
            '想保存事情，说“记住：我喜欢宇宙”；保存交流偏好，说“记住偏好：回答短一点”。'
            '说“你记住了什么”可以查看；说“忘记：我喜欢宇宙”或“删除偏好：回答短一点”可以删除，内容要和保存时一致。'
            '你也可以说“我叫小明”或“你可以叫我小米”，我就记住怎样称呼你。'
            '这些设置保存后立即生效，重启也保留。'
            f'如果进入待机，连续叫两遍我的当前名字，比如“{name}，{name}”，听到“你好，我在”后就能继续聊。')


def help_reply(text, name):
    normalized = re.sub(r'[\s，。！？,.!?]', '', text)
    if normalized in ('使用帮助', '怎么用', '你怎么用', '介绍一下你自己', '重新介绍一下', '你能做什么'):
        return guide(name)
    if re.search(r'怎么|如何|怎样', normalized) and re.search(r'记忆|记住|偏好|设置|改名|名字|名称|名词', normalized):
        if not normalized.startswith(('记住', '添加偏好', '删除偏好', '忘记')):
            return guide(name)
    return None


def introduce_once(marker, name, deliver):
    if marker.exists():
        return False
    deliver(guide(name))
    try:
        marker.write_text('introduced\n', encoding='utf-8')
    except OSError as exc:
        raise PreferenceError('介绍已播放，但无法保存首次介绍标记') from exc
    return True
