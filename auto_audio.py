"""Continuous PCM capture and energy-based endpoint detection (no Python dependencies)."""
from collections import deque
import math
import os
import select
import struct
import subprocess
import time
import tempfile
import wave

RATE = 16000
FRAME_SAMPLES = 320  # 20 ms, signed 16-bit mono
FRAME_BYTES = FRAME_SAMPLES * 2


class AudioError(Exception):
    pass


class EndpointDetector:
    """Energy gate, not a speech classifier: music/noise can also trigger it."""
    def __init__(self, *, threshold, silence, minimum, maximum):
        self.threshold = threshold
        self.silence_frames = math.ceil(silence * 50)
        self.minimum_frames = math.ceil(minimum * 50)
        self.maximum_frames = math.ceil(maximum * 50)
        self.preroll = deque(maxlen=15)  # Preserve 300 ms before onset.
        self.frames = []
        self.voiced = 0
        self.quiet = 0
        self.elapsed = 0

    @property
    def speaking(self):
        return bool(self.frames)

    def feed(self, pcm):
        samples = struct.unpack('<320h', pcm)
        rms = math.sqrt(sum(s * s for s in samples) / FRAME_SAMPLES)
        loud = rms >= self.threshold
        if not self.speaking:
            if not loud:
                self.preroll.append(pcm)
                return None
            self.frames = list(self.preroll)
            self.preroll.clear()
        self.frames.append(pcm)
        self.elapsed += 1
        self.voiced += int(loud)
        self.quiet = 0 if loud else self.quiet + 1
        if self.quiet >= self.silence_frames or self.elapsed >= self.maximum_frames:
            result = b''.join(self.frames) if self.voiced >= self.minimum_frames else None
            self.frames = []
            self.voiced = self.quiet = self.elapsed = 0
            return result
        return None


def stop_capture(process):
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    finally:
        process.stdout.close()


def record_utterance(path, source, detector, idle_seconds):
    """Return a WAV path, or None after idle timeout. Always close capture first."""
    with tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen([
                'parec', '--raw', '--format=s16le', '--rate=16000', '--channels=1',
                '--latency-msec=40', '--device=' + source,
            ], stdout=subprocess.PIPE, stderr=errors)
        except OSError as exc:
            raise AudioError('无法启动 parec；请运行 pkg install pulseaudio') from exc
        try:
            print('正在监听：直接说话，停顿后自动发送；Ctrl+C 退出。', flush=True)
            buffer = b''
            started = last_data = time.monotonic()
            while True:
                ready, _, _ = select.select([process.stdout], [], [], 0.2)
                now = time.monotonic()
                if ready:
                    chunk = os.read(process.stdout.fileno(), 4096)
                    if not chunk:
                        errors.seek(0)
                        detail = errors.read(1000).decode('utf-8', errors='replace')
                        raise AudioError('麦克风音频流已关闭：' + detail)
                    last_data = now
                    buffer += chunk
                    while len(buffer) >= FRAME_BYTES:
                        pcm, buffer = buffer[:FRAME_BYTES], buffer[FRAME_BYTES:]
                        was_speaking = detector.speaking
                        audio = detector.feed(pcm)
                        if not was_speaking and detector.speaking:
                            print('检测到声音，正在录音……', flush=True)
                        if audio is not None:
                            with wave.open(str(path), 'wb') as wav:
                                wav.setnchannels(1)
                                wav.setsampwidth(2)
                                wav.setframerate(RATE)
                                wav.writeframes(audio)
                            return path
                if now - last_data > 5:
                    raise AudioError('麦克风 5 秒未返回数据；检查权限、后台限制和 PulseAudio')
                if not detector.speaking and now - started >= idle_seconds:
                    return None
        finally:
            stop_capture(process)

