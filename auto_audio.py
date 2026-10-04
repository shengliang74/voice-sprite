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
from event_log import emit

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
        self.end_reason = None
        self.rms_histogram = [0] * 33
        self.total_frames = self.above_frames = self.triggers = 0
        self.accepted = self.rejected = self.rms_peak = 0
        self.rms_sum = 0.0

    def statistics(self):
        def percentile(fraction):
            target = max(1, math.ceil(self.total_frames * fraction))
            count = 0
            for index, frequency in enumerate(self.rms_histogram):
                count += frequency
                if count >= target:
                    return (index + 1) * 100
            return 0
        return dict(frames=self.total_frames, above_threshold_frames=self.above_frames,
                    threshold=self.threshold, triggers=self.triggers,
                    accepted=self.accepted, rejected=self.rejected,
                    rms_peak=round(self.rms_peak),
                    rms_mean=round(self.rms_sum / max(1, self.total_frames)),
                    rms_p50_bucket=percentile(0.5), rms_p95_bucket=percentile(0.95),
                    silence_ms=self.silence_frames*20, min_speech_ms=self.minimum_frames*20)

    @property
    def speaking(self):
        return bool(self.frames)

    def feed(self, pcm):
        samples = struct.unpack('<320h', pcm)
        rms = math.sqrt(sum(s * s for s in samples) / FRAME_SAMPLES)
        loud = rms >= self.threshold
        self.total_frames += 1
        self.above_frames += int(loud)
        self.rms_sum += rms
        self.rms_peak = max(self.rms_peak, rms)
        self.rms_histogram[min(32, int(rms // 100))] += 1
        if not self.speaking:
            if not loud:
                self.preroll.append(pcm)
                return None
            self.triggers += 1
            self.frames = list(self.preroll)
            self.preroll.clear()
        self.frames.append(pcm)
        self.elapsed += 1
        self.voiced += int(loud)
        self.quiet = 0 if loud else self.quiet + 1
        if self.quiet >= self.silence_frames or self.elapsed >= self.maximum_frames:
            self.end_reason = 'maximum' if self.elapsed >= self.maximum_frames else 'silence'
            result = b''.join(self.frames) if self.voiced >= self.minimum_frames else None
            self.accepted += int(result is not None)
            self.rejected += int(result is None)
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
    with open(os.devnull, "wb") as errors:
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
                        detail = 'parec exit=' + str(process.poll())
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
                            emit("record_end", reason=detector.end_reason, duration_ms=round(len(audio)/32))
                            print("达到最长录音限制，结束本轮。" if detector.end_reason == "maximum" else "检测到持续停顿，结束本轮。", flush=True)
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
            if detector is not None:
                emit("vad_summary", **detector.statistics())

