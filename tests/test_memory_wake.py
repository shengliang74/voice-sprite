import tempfile
from pathlib import Path
import unittest
from memory_wake import Memory, WakeSession

class MemoryWakeTests(unittest.TestCase):
    def test_memory_hot_reload_and_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'memory.json'
            memory=Memory(path)
            memory.handle('记住：我喜欢宇宙')
            self.assertIn('我喜欢宇宙', Memory(path).instruction())
            memory.handle('以后学英语时先中文再英文')
            self.assertIn('中文', memory.instruction())
            path.write_text('{"preferences":["回答短一点"],"memories":[]}',encoding='utf-8')
            self.assertIn('回答短一点',memory.instruction())
            memory.handle('删除偏好：回答短一点')
            self.assertNotIn('回答短一点',memory.instruction())

    def test_wake_idle_and_exact_double_name(self):
        session=WakeSession(60)
        self.assertEqual(session.accept('普通问题','小玉米',0),'ignore')
        self.assertEqual(session.accept('小玉米，小玉米！','小玉米',1),'wake')
        session.replied(10)
        self.assertEqual(session.accept('宇宙多大','小玉米',30),'talk')
        self.assertTrue(session.expire(71))
        self.assertEqual(session.accept('小玉米','小玉米',72),'ignore')
        self.assertEqual(session.accept('小星星小星星','小星星',73),'wake')
        self.assertEqual(session.accept('先不聊了','小星星',74),'sleep')

    def test_memory_is_in_next_model_request_without_restart(self):
        import json
        from unittest.mock import patch
        import voice_sprite as app
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, 'ROOT', Path(tmp)), patch.object(app, 'load_persona', return_value='Tutor'), patch.object(app, 'post', return_value={'choices':[{'message':{'content':'OK'}}]}) as post:
            memory=Memory(Path(tmp)/'memory.json')
            memory.handle('记住偏好：回答短一点')
            app.reply('你好',[])
            self.assertIn('回答短一点',json.loads(post.call_args.args[2])['messages'][0]['content'])
            memory.handle('删除偏好：回答短一点')
            app.reply('你好',[])
            self.assertNotIn('回答短一点',json.loads(post.call_args.args[2])['messages'][0]['content'])

    def test_auto_waits_for_wake_and_then_answers(self):
        import os
        from unittest.mock import patch
        import voice_sprite as app
        env={p+'_'+s:'test' for p in ('ASR','LLM') for s in ('API_KEY','BASE_URL','MODEL')}
        env['WAKE_ENABLED']='1'
        env['INTRO_ENABLED']='0'
        with tempfile.TemporaryDirectory() as tmp, patch.object(app,'ROOT',Path(tmp)), patch.dict(os.environ,env,clear=True), patch.object(app,'load_env'), patch.object(app,'load_persona',return_value='Tutor'), patch.object(app,'prepare_auto',return_value='mic'), patch.object(app,'record_auto',side_effect=[Path('fake.wav')]*3+[KeyboardInterrupt]), patch.object(app,'transcribe',side_effect=['宇宙多大','小灵，小灵','宇宙多大']), patch.object(app,'reply',return_value='很大') as reply, patch.object(app,'speak') as speak, patch('sys.argv',['voice_sprite.py','--auto']):
            with self.assertRaises(KeyboardInterrupt): app.main()
            reply.assert_called_once()
            self.assertEqual([call.args[0] for call in speak.call_args_list],['你好，我在。','很大'])

    def test_invalid_file_does_not_get_overwritten(self):
        from dialogue import PreferenceError
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'memory.json';path.write_text('broken')
            with self.assertRaises(PreferenceError): Memory(path).handle('记住：你好')
            self.assertEqual(path.read_text(),'broken')

    def test_user_names_persist_and_replace_same_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'memory.json'; memory=Memory(path)
            for phrase in ['我叫小明。','我的小名是小米','你可以叫我米粒']:
                self.assertIsNotNone(memory.handle(phrase))
            data=Memory(path).read()
            self.assertIn('用户名字：小明',data['memories'])
            self.assertIn('用户小名：小米',data['memories'])
            self.assertIn('用户希望被称呼为：米粒',data['preferences'])
            memory.handle('我叫小亮')
            self.assertNotIn('用户名字：小明',memory.read()['memories'])
            self.assertIn('用户小名：小米',memory.read()['memories'])
            memory.handle('忘记：用户名字：小亮')
            self.assertNotIn('用户名字：小亮',memory.read()['memories'])

    def test_user_name_questions_and_ai_names_not_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory=Memory(Path(tmp)/'memory.json')
            for phrase in ['你叫小玉米','我叫什么名字？','你可以叫我什么','我的小名是什么','我叫妈妈来帮忙','他说我叫小明','我叫小明，你呢？']:
                with self.subTest(phrase=phrase):
                    self.assertIsNone(memory.handle(phrase))
            self.assertEqual(memory.read()['memories'],[])

    def test_wake_with_third_name_and_trailing_words(self):
        session=WakeSession(60)
        self.assertEqual(session.accept('小玉米小玉米小玉米，可以了','小玉米',0),'wake')
        session.active=False
        self.assertEqual(session.accept('他说小玉米小玉米','小玉米',1),'ignore')
