import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import voice_sprite as app


class PersonaTests(unittest.TestCase):
    def test_custom_persona_and_utf8(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, 'ROOT', Path(tmp)), patch.dict(os.environ, {}, clear=True):
            (Path(tmp) / 'persona.txt').write_text('你叫小灵。', encoding='utf-8')
            self.assertEqual(app.load_persona(), '你叫小灵。')

    def test_missing_default_uses_example(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, 'ROOT', Path(tmp)), patch.dict(os.environ, {}, clear=True):
            (Path(tmp) / 'persona.example.txt').write_text('Tutor', encoding='utf-8')
            self.assertEqual(app.load_persona(), 'Tutor')

    def test_explicit_missing_or_empty_persona_is_error(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, 'ROOT', Path(tmp)), patch.dict(os.environ, {'PERSONA_FILE': 'custom.txt'}, clear=True):
            with self.assertRaises(app.AppError):
                app.load_persona()
            (Path(tmp) / 'custom.txt').write_text('  ')
            with self.assertRaises(app.AppError):
                app.load_persona()
