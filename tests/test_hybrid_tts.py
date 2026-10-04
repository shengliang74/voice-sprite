import os
import unittest
from unittest.mock import patch
import voice_sprite as app

class HybridTests(unittest.TestCase):
    def test_chinese_uses_explicit_local_engine(self):
        with patch.dict(os.environ, {'TTS_PROVIDER':'hybrid','TTS_LANGUAGE':'zh','TTS_ZH_ENGINE':'example.xiaoya'}, clear=True), patch.object(app,'command') as command, patch.object(app,'speak_cloud') as cloud, patch.object(app.time,'sleep'):
            app.speak('你好')
            cloud.assert_not_called()
            self.assertIn('example.xiaoya', command.call_args.args[0])
            self.assertIn('CN', command.call_args.args[0])

    def test_english_uses_cloud(self):
        with patch.dict(os.environ, {'TTS_PROVIDER':'hybrid','TTS_LANGUAGE':'en'}, clear=True), patch.object(app,'command') as command, patch.object(app,'speak_cloud') as cloud, patch.object(app.time,'sleep'):
            app.speak('Hello')
            cloud.assert_called_once()
            command.assert_not_called()

    def test_missing_chinese_engine_is_actionable(self):
        with patch.dict(os.environ, {'TTS_PROVIDER':'hybrid','TTS_LANGUAGE':'zh'}, clear=True):
            with self.assertRaisesRegex(app.AppError, 'TTS_ZH_ENGINE'):
                app.speak('你好')

    def test_local_tts_timeout_is_configurable(self):
        with patch.dict(os.environ, {'TTS_PROVIDER':'android','TTS_TIMEOUT':'20'}, clear=True), patch.object(app,'command') as command, patch.object(app.time,'sleep'):
            app.speak('你好')
            self.assertEqual(command.call_args.kwargs['timeout'], 20)

    def test_invalid_timeout_does_not_start_tts(self):
        with patch.dict(os.environ, {'TTS_PROVIDER':'android','TTS_TIMEOUT':'0'}, clear=True), patch.object(app,'command') as command:
            with self.assertRaises(app.AppError):
                app.speak('你好')
            command.assert_not_called()
