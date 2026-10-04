import os
import unittest
from unittest.mock import patch
import voice_sprite as app

class NoticeTests(unittest.TestCase):
    def test_notice_uses_local_audio_and_no_cloud(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(app,'play_file') as play, patch.object(app,'post') as post:
            app.notify_voice('paused')
            self.assertTrue(play.call_args.args[0].is_file())
            post.assert_not_called()

    def test_notice_failure_does_not_mask_original_error(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(app,'play_file',side_effect=app.SpeechError('audio unavailable')):
            app.notify_voice('error')

    def test_notice_can_be_disabled(self):
        with patch.dict(os.environ, {'AUDIO_PROMPTS':'0'},clear=True), patch.object(app,'play_file') as play:
            app.notify_voice('synthesizing')
            play.assert_not_called()

    def test_notice_precedes_cloud_synthesis(self):
        events=[]
        with patch.dict(os.environ, {'TTS_PROVIDER':'siliconflow'},clear=True), patch.object(app,'notify_voice',side_effect=lambda event:events.append(event)), patch.object(app,'speak_cloud',side_effect=lambda *a:events.append('cloud')), patch.object(app.time,'sleep'):
            app.speak('你好')
            self.assertEqual(events,['synthesizing','cloud'])
