import os
from pathlib import Path
import unittest
from unittest.mock import patch
import voice_sprite as app


class AutoLoopTests(unittest.TestCase):
    def run_loop(self, failure=False):
        events = []
        def capture(*args):
            events.append('listen')
            if len(events) > 1:
                raise KeyboardInterrupt
            return Path('fake.wav')
        def speak(text):
            events.append('speak')
            if failure:
                raise app.AppError('tts timeout')
        env = {prefix + '_' + suffix: 'test' for prefix in ('ASR', 'LLM')
               for suffix in ('API_KEY', 'BASE_URL', 'MODEL')}
        with patch.dict(os.environ, dict(env, WAKE_ENABLED='0', INTRO_ENABLED='0'), clear=True), patch.object(app, 'load_env'), \
             patch.object(app, 'load_persona', return_value='Tutor'), \
             patch.object(app, 'prepare_auto', return_value='mic'), \
             patch.object(app, 'record_auto', side_effect=capture), \
             patch.object(app, 'transcribe', return_value='Hello'), \
             patch.object(app, 'reply', side_effect=lambda *a: events.append('reply') or 'Hi'), \
             patch.object(app, 'speak', side_effect=speak), \
             patch('sys.argv', ['voice_sprite.py', '--auto']), \
             patch('builtins.input', return_value='/quit') as prompt:
            if failure:
                self.assertEqual(app.main(), 0)
                prompt.assert_called_once()
            else:
                with self.assertRaises(KeyboardInterrupt):
                    app.main()
                prompt.assert_not_called()
        return events

    def test_next_listen_only_after_speak_returns(self):
        self.assertEqual(self.run_loop(), ['listen', 'reply', 'speak', 'listen'])

    def test_tts_failure_pauses_instead_of_auto_retry(self):
        self.assertEqual(self.run_loop(failure=True), ['listen', 'reply', 'speak'])

    def test_microphone_source_selected_not_monitor(self):
        sources = '0 sink.monitor module-sles-sink.c s16le\n1 mic module-sles-source.c s16le'
        with patch.object(app.shutil, 'which', return_value='/bin/tool'), \
             patch.object(app, 'command', side_effect=['', sources]):
            self.assertEqual(app.prepare_auto(), 'mic')
