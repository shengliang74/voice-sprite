import tempfile
from pathlib import Path
import unittest
from dialogue import Preferences

class PreferenceTests(unittest.TestCase):
    def test_voice_changes_persist_and_questions_do_not_rename(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            prefs = Preferences(path)
            self.assertEqual(prefs.language, 'zh')
            self.assertIsNotNone(prefs.handle('请用英文回答。'))
            self.assertEqual(Preferences(path).language, 'en')
            self.assertIsNotNone(prefs.handle('以后你叫小星星。'))
            self.assertEqual(Preferences(path).name, '小星星')
            self.assertIsNone(prefs.handle('为什么这个星球叫火星？'))
            self.assertIsNotNone(prefs.handle('切回中文'))
            self.assertEqual(prefs.language, 'zh')

    def test_english_and_role_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs = Preferences(Path(tmp) / 'settings.json')
            self.assertIsNotNone(prefs.handle('Switch to English.'))
            self.assertIsNotNone(prefs.handle('Your name is Nova.'))
            self.assertEqual(prefs.name, 'Nova')
            self.assertIsNotNone(prefs.handle('切换成太空探险家'))
            self.assertEqual(prefs.role, '太空探险家')

    def test_rename_updates_model_system_context(self):
        import json
        from unittest.mock import patch
        import voice_sprite as app
        with tempfile.TemporaryDirectory() as tmp:
            prefs = Preferences(Path(tmp) / 'settings.json')
            prefs.handle('以后你叫小星星')
            prefs.handle('请用英文回答')
            with patch.object(app, 'post', return_value={'choices': [{'message': {'content': 'Hello'}}]}) as post:
                app.reply('Tell me about stars', [], prefs)
            prompt = json.loads(post.call_args.args[2])['messages'][0]['content']
            self.assertIn('小星星', prompt)
            self.assertIn('English', prompt)

    def test_voice_switch_in_main_bypasses_llm_and_persists(self):
        import os
        from unittest.mock import patch
        import voice_sprite as app
        env = {p + '_' + s: 'test' for p in ('ASR', 'LLM') for s in ('API_KEY', 'BASE_URL', 'MODEL')}
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, 'ROOT', Path(tmp)), \
             patch.dict(os.environ, env, clear=True), patch.object(app, 'load_env'), \
             patch.object(app, 'load_persona', return_value='Tutor'), \
             patch.object(app, 'prepare_auto', return_value='mic'), \
             patch.object(app, 'record_auto', side_effect=[Path('fake.wav'), KeyboardInterrupt]), \
             patch.object(app, 'transcribe', return_value='请用英文回答'), \
             patch.object(app, 'reply') as reply, patch.object(app, 'speak') as speak, \
             patch('sys.argv', ['voice_sprite.py', '--auto']):
            with self.assertRaises(KeyboardInterrupt):
                app.main()
            reply.assert_not_called()
            speak.assert_called_once_with("I'll answer in English.")
            self.assertEqual(Preferences(Path(tmp) / 'conversation.json').language, 'en')

    def test_flexible_language_requests(self):
        from dialogue import language_request
        for text, expected in [
            ('小灵，你能不能用英文跟我聊天呀？', 'en'),
            ('接下来我们用英语聊吧', 'en'),
            ('我想练习英语', 'en'),
            ('换成中文说好吗？', 'zh'),
            ('可以用中文再说一遍吗？', 'zh'),
            ('Could you please answer in English?', 'en'),
            ("Let's talk in Chinese.", 'zh'),
        ]:
            with self.subTest(text=text):
                self.assertEqual(language_request(text, '小灵'), expected)
        for text in ['不要用英文回答', '为什么你用英文回答？', '英语怎么说宇宙',
                     '他说“请用英文回答”是什么意思', 'Can you explain English grammar?',
                     "Don't speak English", '用中文还是英文回答？']:
            with self.subTest(text=text):
                self.assertIsNone(language_request(text, '小灵'))
