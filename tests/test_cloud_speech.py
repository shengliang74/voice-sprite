import json
import os
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import cloud_speech as cloud
import voice_sprite as app

class CloudSpeechTests(unittest.TestCase):
    def test_wait_for_playback_completion_and_stop(self):
        command = Mock(side_effect=['Now Playing: reply.mp3', 'Status: Playing\nTrack: reply.mp3', 'No track currently!', 'Stopped'])
        with patch.object(cloud.time, 'sleep'):
            cloud.play_file(Path('reply.mp3'), command)
        self.assertEqual(command.call_args.args[0][-1], 'stop')
        self.assertEqual(command.call_count, 4)

    def test_failed_play_not_silently_ignored(self):
        with self.assertRaises(cloud.SpeechError):
            cloud.play_file(Path('reply.mp3'), Mock(return_value='file missing'))

    def test_payload_and_temporary_audio_cleanup(self):
        paths = []
        def play(path, command):
            self.assertTrue(path.exists())
            paths.append(path)
        post = Mock(return_value=b'ID3fakeaudio')
        with patch.dict(os.environ, {}, clear=True), patch.object(cloud, 'play_file', side_effect=play):
            cloud.speak_cloud('你好 Hello', post, Mock(), app.setting, app.number)
        payload = json.loads(post.call_args.args[2])
        self.assertEqual(payload['voice'], 'FunAudioLLM/CosyVoice2-0.5B:diana')
        self.assertEqual(payload['input'], '你好 Hello')
        self.assertFalse(paths[0].exists())

    def test_binary_response_and_asr_key_reuse(self):
        response = Mock()
        response.read.return_value = b'ID3audio'
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch.dict(os.environ, {'ASR_API_KEY': 'test-secret'}, clear=True), patch.object(app.urllib.request, 'build_opener', return_value=opener):
            self.assertEqual(app.post('TTS', '/audio/speech', b'{}', 'application/json', binary=True), b'ID3audio')
            self.assertEqual(opener.open.call_args.args[0].get_header('Authorization'), 'Bearer test-secret')

    def test_asr_key_not_sent_to_custom_tts_endpoint(self):
        with patch.dict(os.environ, {'ASR_API_KEY': 'test-secret', 'TTS_BASE_URL': 'https://example.com/v1'}, clear=True):
            with self.assertRaisesRegex(app.AppError, 'TTS_API_KEY'):
                app.post('TTS', '/audio/speech', b'{}', 'application/json', binary=True)

    def test_interrupt_stops_media(self):
        command = Mock(side_effect=['Now Playing: reply.mp3', KeyboardInterrupt, 'Stopped'])
        with self.assertRaises(KeyboardInterrupt):
            cloud.play_file(Path('reply.mp3'), command)
        self.assertEqual(command.call_args.args[0], ['termux-media-player', 'stop'])

    def test_json_error_body_is_not_played(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(cloud, 'play_file') as play:
            with self.assertRaises(cloud.SpeechError):
                cloud.speak_cloud('Hello', Mock(return_value=b'{"error":"failed"}'), Mock(), app.setting, app.number)
            play.assert_not_called()
