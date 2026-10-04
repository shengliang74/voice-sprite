import struct
import unittest
from auto_audio import EndpointDetector


def frame(level):
    return struct.pack('<320h', *([level] * 320))


class EndpointTests(unittest.TestCase):
    def detector(self, maximum=3):
        return EndpointDetector(threshold=500, silence=0.2, minimum=0.06, maximum=maximum)

    def test_silence_does_not_create_utterance(self):
        detector = self.detector()
        for _ in range(1000):
            self.assertIsNone(detector.feed(frame(0)))
        self.assertFalse(detector.speaking)

    def test_short_noise_is_discarded(self):
        detector = self.detector()
        detector.feed(frame(1000))
        for _ in range(30):
            self.assertIsNone(detector.feed(frame(0)))
        self.assertFalse(detector.speaking)

    def test_pause_inside_sentence_and_trailing_silence(self):
        detector = self.detector()
        for level in [1000] * 5 + [0] * 5 + [1000] * 5 + [0] * 9:
            self.assertIsNone(detector.feed(frame(level)))
        audio = detector.feed(frame(0))
        self.assertIsNotNone(audio)
        self.assertIn(frame(1000), audio)

    def test_continuous_sound_has_duration_limit(self):
        detector = self.detector(maximum=0.2)
        for _ in range(9):
            self.assertIsNone(detector.feed(frame(1000)))
        self.assertIsNotNone(detector.feed(frame(1000)))


class CaptureTests(unittest.TestCase):
    def test_pcm_pipe_creates_wav_and_closes_process(self):
        import subprocess
        import sys
        import tempfile
        import wave
        from pathlib import Path
        from unittest.mock import patch
        import auto_audio
        real_popen = subprocess.Popen
        processes = []

        def capture(*args, **kwargs):
            child = real_popen([sys.executable, '-c',
                "import sys,struct,time; sys.stdout.buffer.write("
                "struct.pack('<320h', *([1200]*320))*10 + b'\\0'*640*15);"
                "sys.stdout.buffer.flush(); time.sleep(10)"], **kwargs)
            processes.append(child)
            return child

        with tempfile.TemporaryDirectory() as tmp, patch.object(auto_audio.subprocess, 'Popen', side_effect=capture):
            path = Path(tmp) / 'speech.wav'
            detector = EndpointDetector(threshold=500, silence=0.2, minimum=0.06, maximum=3)
            result = auto_audio.record_utterance(path, 'test', detector, 30)
            self.assertEqual(result, path)
            with wave.open(str(path)) as wav:
                self.assertEqual(wav.getframerate(), 16000)
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getnframes(), 320 * 20)
        self.assertIsNotNone(processes[0].poll())
        self.assertTrue(processes[0].stdout.closed)

    def test_interrupt_closes_capture(self):
        from unittest.mock import patch, Mock
        from pathlib import Path
        import auto_audio
        process = Mock()
        process.poll.return_value = None
        with patch.object(auto_audio.subprocess, 'Popen', return_value=process), patch.object(auto_audio.select, 'select', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                auto_audio.record_utterance(Path('unused.wav'), 'test', None, 30)
        process.terminate.assert_called_once()
        process.wait.assert_called_once()
        process.stdout.close.assert_called_once()

    def test_stalled_microphone_times_out_and_closes(self):
        from unittest.mock import patch, Mock
        from pathlib import Path
        import auto_audio
        process = Mock()
        process.poll.return_value = None
        with patch.object(auto_audio.subprocess, 'Popen', return_value=process), \
             patch.object(auto_audio.select, 'select', return_value=([], [], [])), \
             patch.object(auto_audio.time, 'monotonic', side_effect=[0, 6]):
            with self.assertRaisesRegex(auto_audio.AudioError, '5 秒'):
                auto_audio.record_utterance(Path('unused.wav'), 'test', None, 30)
        process.terminate.assert_called_once()

    def test_silent_capture_returns_none_without_wav(self):
        from unittest.mock import patch, Mock
        from pathlib import Path
        import tempfile
        import auto_audio
        process = Mock()
        process.poll.return_value = None
        detector = EndpointDetector(threshold=500, silence=0.2, minimum=0.06, maximum=3)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(auto_audio.subprocess, 'Popen', return_value=process), \
             patch.object(auto_audio.select, 'select', return_value=([process.stdout], [], [])), \
             patch.object(auto_audio.os, 'read', return_value=frame(0)), \
             patch.object(auto_audio.time, 'monotonic', side_effect=[0, 31]):
            path = Path(tmp) / 'speech.wav'
            self.assertIsNone(auto_audio.record_utterance(path, 'test', detector, 30))
            self.assertFalse(path.exists())
        process.terminate.assert_called_once()

class DiagnosticsTests(unittest.TestCase):
    def test_bounded_statistics_distinguish_noise_and_voice(self):
        detector=EndpointDetector(threshold=500,silence=0.2,minimum=0.06,maximum=3)
        for _ in range(100):detector.feed(frame(100))
        for _ in range(10):detector.feed(frame(1000))
        for _ in range(10):detector.feed(frame(0))
        stats=detector.statistics()
        self.assertEqual(stats['frames'],120)
        self.assertEqual(stats['above_threshold_frames'],10)
        self.assertEqual(stats['accepted'],1)
        self.assertEqual(stats['rms_peak'],1000)
        self.assertEqual(len(detector.rms_histogram),33)
