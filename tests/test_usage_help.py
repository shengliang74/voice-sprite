import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock
from usage_help import help_reply, introduce_once

class HelpTests(unittest.TestCase):
    def test_questions_explain_real_commands(self):
        for question in ['怎么保存记忆？','如何设置偏好','我想修改你的名字，怎么改？','怎么修改名称','使用帮助']:
            answer=help_reply(question,'小玉米')
            self.assertIn('记住偏好',answer)
            self.assertIn('把你的名字改成',answer)
        self.assertIsNone(help_reply('你还记得黑洞吗','小玉米'))
        self.assertIsNone(help_reply('记住偏好：回答短一点','小玉米'))

    def test_intro_only_marked_after_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'intro.done'
            speak=Mock(side_effect=RuntimeError('failed'))
            with self.assertRaises(RuntimeError):introduce_once(marker,'小玉米',speak)
            self.assertFalse(marker.exists())
            speak=Mock()
            self.assertTrue(introduce_once(marker,'小玉米',speak))
            self.assertFalse(introduce_once(marker,'小玉米',speak))
            speak.assert_called_once()
