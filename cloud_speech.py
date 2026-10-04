"""SiliconFlow speech synthesis and Android media playback."""
import json
from pathlib import Path
import tempfile
import time


class SpeechError(Exception):
    pass


def play_file(path, command, timeout=180):
    try:
        result = command(['termux-media-player', 'play', str(path)])
        if not result.startswith('Now Playing:'):
            raise SpeechError('无法播放云端音频：' + result[:300])
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = command(['termux-media-player', 'info'])
            if status.strip() == 'No track currently!':
                return
            if not status.startswith('Status: Playing'):
                raise SpeechError('播放已暂停或状态异常：' + status[:300])
            time.sleep(0.2)
        raise SpeechError('云端音频播放超时')
    finally:
        # Also stop on Ctrl+C; do not leave playback running over the next recording.
        try:
            command(['termux-media-player', 'stop'])
        except Exception:
            pass


def speak_cloud(text, post, command, setting, number):
    model = setting('TTS_MODEL', 'FunAudioLLM/CosyVoice2-0.5B')
    payload = {'model': model, 'input': text,
               'voice': setting('TTS_VOICE') or model + ':diana',
               'response_format': 'mp3', 'stream': False,
               'speed': number('CLOUD_TTS_SPEED', 1, 0.25, 4)}
    print('正在合成云端语音……', flush=True)
    audio = post('TTS', '/audio/speech', json.dumps(payload).encode(),
                 'application/json', binary=True)
    if not audio or not (audio.startswith(b'ID3') or
                         (len(audio) >= 2 and audio[0] == 255 and audio[1] & 224 == 224)):
        raise SpeechError('TTS 未返回有效 MP3 音频')
    with tempfile.TemporaryDirectory(prefix='voice-sprite-tts-') as tmp:
        path = Path(tmp) / 'reply.mp3'
        path.write_bytes(audio)
        print('正在播放……', flush=True)
        play_file(path, command)
