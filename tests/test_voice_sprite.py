import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import urllib.error

import voice_sprite as app


class TutorTests(unittest.TestCase):
    def test_env_preserves_external_values_and_literal_secrets(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"LLM_API_KEY": "external"}, clear=True):
            path = Path(tmp) / ".env"
            path.write_text('LLM_API_KEY=file\nASR_API_KEY="literal$secret#key"\n')
            app.load_env(path)
            self.assertEqual(os.environ["LLM_API_KEY"], "external")
            self.assertEqual(os.environ["ASR_API_KEY"], "literal$secret#key")

    @patch.dict(os.environ, {"HISTORY_TURNS": "1", "LLM_BASE_URL": "https://api.deepseek.com"})
    @patch.object(app, "post")
    def test_history_committed_only_after_success_and_bounded(self, post):
        history = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "old reply"}]
        post.side_effect = app.AppError("network")
        with self.assertRaises(app.AppError):
            app.reply("new", history)
        self.assertEqual(len(history), 2)
        post.side_effect = None
        post.return_value = {"choices": [{"message": {"content": "Hello"}}]}
        self.assertEqual(app.reply("new", history), "Hello")
        self.assertEqual(history[0]["content"], "new")
        payload = json.loads(post.call_args.args[2])
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["thinking"], {"type": "disabled"})

    @patch.object(app, "post", return_value={"text": "Hello"})
    def test_asr_multipart_contains_actual_audio(self, post):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audio.wav"
            path.write_bytes(b"RIFF-test-audio")
            self.assertEqual(app.transcribe(path), "Hello")
            body = post.call_args.args[2]
            self.assertIn(b'filename="speech.wav"', body)
            self.assertIn(b"RIFF-test-audio", body)
            post.return_value = {"text": " "}
            with self.assertRaises(app.AppError):
                app.transcribe(path)

    @patch.object(app.subprocess, "run")
    def test_termux_error_even_with_zero_exit(self, run):
        run.return_value = Mock(returncode=0, stdout='{"error":"permission denied"}', stderr="")
        with self.assertRaisesRegex(app.AppError, "permission denied"):
            app.command(["termux-microphone-record"])

    @patch.object(app, "command")
    @patch.object(app.select, "select", side_effect=KeyboardInterrupt)
    def test_interrupted_recording_stops_microphone(self, select_mock, command):
        command.return_value = '{"isRecording":false}'
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(KeyboardInterrupt):
                app.record(Path(tmp))
        self.assertEqual(command.call_args.args[0], ["termux-microphone-record", "-q"])

    @patch.dict(os.environ, {"LLM_API_KEY": "secret", "LLM_BASE_URL": "https://example.com"})
    @patch.object(app.urllib.request, "build_opener")
    def test_http_error_is_actionable_without_leaking_key(self, opener):
        opener.return_value.open.side_effect = urllib.error.HTTPError("https://example.com", 401, "secret", {}, None)
        with self.assertRaisesRegex(app.AppError, "API Key 无效") as error:
            app.post("LLM", "/chat/completions", b"{}", "application/json")
        self.assertNotIn("secret", str(error.exception))

    @patch.dict(os.environ, {"LLM_API_KEY": "secret", "LLM_BASE_URL": "http://example.com"})
    def test_reject_plain_http(self):
        with self.assertRaisesRegex(app.AppError, "HTTPS"):
            app.post("LLM", "/chat/completions", b"{}", "application/json")


if __name__ == "__main__":
    unittest.main()
