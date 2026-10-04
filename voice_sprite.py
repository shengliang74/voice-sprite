#!/usr/bin/env python3
"""Termux English conversation tutor; Python standard library only."""
import argparse
import json
import re
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from event_log import configure as configure_log, emit
from usage_help import help_reply, introduce_once
from memory_wake import Memory, WakeSession
from dialogue import Preferences, PreferenceError
from cloud_speech import speak_cloud, SpeechError, play_file
from auto_audio import AudioError, EndpointDetector, record_utterance

ROOT = Path(__file__).resolve().parent



class AppError(Exception):
    pass


def load_env(path):
    if not path.exists():
        return
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not key.strip().replace("_", "").isalnum():
            raise AppError(f"配置第 {number} 行格式错误，应为 KEY=value")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def setting(key, default=""):
    return os.environ.get(key, default).strip()


def number(key, default, minimum, maximum):
    try:
        value = float(setting(key, str(default)))
    except ValueError as exc:
        raise AppError(f"{key} 必须是数字") from exc
    if not minimum <= value <= maximum:
        raise AppError(f"{key} 必须在 {minimum} 到 {maximum} 之间")
    return value


def command(args, *, timeout=20, text=None):
    try:
        result = subprocess.run(args, input=text, text=True, capture_output=True,
                                timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise AppError(f"缺少命令 {args[0]}，请按 README 安装依赖") from exc
    except subprocess.TimeoutExpired as exc:
        emit("command_timeout", service=args[0], duration_ms=timeout*1000)
        raise AppError(f"{args[0]} 超时；检查 Termux:API、权限及后台限制") from exc
    output = result.stdout.strip()
    if result.returncode:
        emit("command_failed", service=args[0], status=result.returncode)
        raise AppError(f"{args[0]} 失败：{result.stderr.strip()[:400]}")
    # Termux API sometimes returns an error object with exit status zero.
    try:
        data = json.loads(output)
    except ValueError:
        data = None
    if isinstance(data, dict) and data.get("error"):
        raise AppError(f"{args[0]}：{data['error']}")
    return output


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward API credentials to a redirect target.


def post(prefix, route, body, content_type, *, binary=False):
    key = setting(prefix + "_API_KEY")
    base = setting(prefix + "_BASE_URL", "https://api.siliconflow.cn/v1" if prefix == "TTS" else "").rstrip("/")
    if prefix == "TTS" and not key and base == "https://api.siliconflow.cn/v1":
        key = setting("ASR_API_KEY")
    parsed = urllib.parse.urlsplit(base)
    if not key:
        raise AppError(f"请在 .env 填写 {prefix}_API_KEY")
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise AppError(f"{prefix}_BASE_URL 必须是无查询参数的 HTTPS 地址")
    request = urllib.request.Request(base + route, data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": content_type,
        "Accept": "audio/mpeg" if binary else "application/json", "User-Agent": "voice-sprite/0.1",
    })
    started = time.monotonic()
    emit("request_start", service=prefix)
    try:
        with urllib.request.build_opener(NoRedirect).open(
                request, timeout=number("HTTP_TIMEOUT", 90, 1, 300)) as response:
            if binary:
                data = response.read(20 * 1024 * 1024 + 1)
                if len(data) > 20 * 1024 * 1024:
                    raise AppError("TTS 音频超过 20 MB 限制")
            else:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise AppError("JSON response exceeds 2 MiB")
                data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        emit("request_error", service=prefix, status=exc.code, error_type=type(exc).__name__, duration_ms=round((time.monotonic()-started)*1000))
        hints = {401: "API Key 无效", 403: "权限或额度不足", 402: "余额不足",
                 404: "检查接口地址及模型名称", 429: "请求过多或额度不足"}
        raise AppError(f"{prefix} HTTP {exc.code}：" + hints.get(exc.code, "服务异常，请稍后重试")) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        cause = getattr(exc, "reason", exc)
        emit("request_error", service=prefix, error_type=type(exc).__name__, cause_type=type(cause).__name__, errno=getattr(cause,"errno",None), duration_ms=round((time.monotonic()-started)*1000))
        raise AppError(f"{prefix} 网络连接失败或超时，请检查网络后重试") from exc
    except ValueError as exc:
        raise AppError(f"{prefix} 返回的不是有效 JSON") from exc
    emit("request_complete", service=prefix, duration_ms=round((time.monotonic()-started)*1000))
    return data


def transcribe(path):
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n"
            f"{setting('ASR_MODEL')}\r\n--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="speech.wav"\r\n'
            'Content-Type: audio/wav\r\n\r\n').encode()
    body += path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    data = post("ASR", "/audio/transcriptions", body, "multipart/form-data; boundary=" + boundary)
    value = data.get("text") if isinstance(data, dict) else None
    if not isinstance(value, str):
        raise AppError("ASR 返回缺少 text 字段")
    if not value.strip():
        raise AppError("没有识别到语音，请靠近手机后重试")
    return value.strip()


def load_persona():
    configured = setting("PERSONA_FILE")
    path = Path(configured or "persona.txt").expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if not configured and not path.exists():
        path = ROOT / "persona.example.txt"
    try:
        content = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise AppError(f"无法读取人设文件：{path}") from exc
    if not content:
        raise AppError(f"人设文件不能为空：{path}")
    return content


def prepare_auto():
    for name in ("pulseaudio", "pactl", "parec"):
        if not shutil.which(name):
            raise AppError("自动模式需要 PulseAudio：请执行 pkg install pulseaudio")
    command(["pulseaudio", "--start", "--exit-idle-time=-1"])
    sources = command(["pactl", "list", "short", "sources"])
    for line in sources.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[2] == "module-sles-source.c":
            return fields[1]
    command(["pactl", "load-module", "module-sles-source",
             "source_name=voice_sprite_mic"])
    return "voice_sprite_mic"


def record_auto(directory, source, idle_seconds=None):
    detector = EndpointDetector(
        threshold=number("VAD_THRESHOLD", 600, 1, 32767),
        silence=number("SILENCE_SECONDS", 3, 0.3, 10),
        minimum=number("MIN_SPEECH_SECONDS", 0.3, 0.04, 2),
        maximum=number("RECORD_SECONDS", 120, 2, 120))
    return record_utterance(directory / "speech.wav", source, detector,
                            number("LISTEN_TIMEOUT", 30, 5, 300) if idle_seconds is None else idle_seconds)


def reply(text, history, preferences=None):
    turns = int(number("HISTORY_TURNS", 6, 1, 30))
    persona = load_persona()
    if preferences is not None:
        persona += "\n" + preferences.instruction()
    persona += Memory(ROOT / "memory.json").instruction()
    messages = [{"role": "system", "content": persona}] + history[-turns * 2:]
    messages.append({"role": "user", "content": text})
    payload = {"model": setting("LLM_MODEL"), "messages": messages,
               "stream": False, "max_tokens": 400}
    if urllib.parse.urlsplit(setting("LLM_BASE_URL")).hostname == "api.deepseek.com":
        payload["thinking"] = {"type": "disabled"}
    data = post("LLM", "/chat/completions", json.dumps(payload).encode(), "application/json")
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AppError("大模型返回格式异常，缺少回答内容") from exc
    if not isinstance(answer, str) or not answer.strip():
        raise AppError("大模型返回空回答，请检查模型配置")
    history.extend([{"role": "user", "content": text},
                    {"role": "assistant", "content": answer.strip()}])
    del history[:-turns * 2]
    return answer.strip()


def notify_voice(event):
    """Best-effort local prerecorded notice; never recursively use cloud TTS."""
    if setting("AUDIO_PROMPTS", "1") != "1":
        return
    if event not in ("synthesizing", "error", "paused"):
        return
    path = ROOT / "assets" / "prompts" / (event + ".wav")
    try:
        if not path.is_file():
            raise AppError("提示音文件缺失，请更新完整部署包")
        def prompt_command(args):
            return command(args, timeout=3)
        play_file(path, prompt_command, timeout=12)
    except (AppError, SpeechError, OSError) as exc:
        print("语音通知未能播放：", exc, file=sys.stderr)


def introduce(preferences, text_mode=False):
    if setting("INTRO_ENABLED", "1") != "1":
        return False
    def deliver(text):
        print(text, flush=True)
        if not text_mode:
            previous = os.environ.get("TTS_LANGUAGE", "zh")
            try:
                os.environ["TTS_LANGUAGE"] = "zh"
                speak(text)
            finally:
                os.environ["TTS_LANGUAGE"] = previous
    return introduce_once(ROOT / ".intro_done", preferences.name, deliver)


def speech_provider():
    provider = setting("TTS_PROVIDER", "siliconflow")
    if provider == "hybrid":
        return "siliconflow" if setting("TTS_LANGUAGE", "zh") == "en" else "android"
    if provider not in ("siliconflow", "android"):
        raise AppError("TTS_PROVIDER 必须是 hybrid、siliconflow 或 android")
    return provider


def speak(text):
    # Hybrid bilingual answers must use the correct voice for each sentence.
    if setting("TTS_PROVIDER") != "hybrid":
        return speak_single(text)
    previous = os.environ.get("TTS_LANGUAGE")
    try:
        for sentence in re.split(r'(?<=[。！？!?])|(?<=\.)\s+|\n+', text):
            sentence = sentence.strip()
            if not any(c.isalnum() for c in sentence):
                continue
            os.environ["TTS_LANGUAGE"] = "zh" if re.search(r'[\u4e00-\u9fff]', sentence) else "en"
            speak_single(sentence)
    finally:
        if previous is None:
            os.environ.pop("TTS_LANGUAGE", None)
        else:
            os.environ["TTS_LANGUAGE"] = previous


def speak_single(text):
    provider = speech_provider()
    if provider == "siliconflow":
        notify_voice("synthesizing")
        speak_cloud(text, post, command, setting, number)
        time.sleep(number("PLAYBACK_COOLDOWN", 0.8, 0, 5))
        return
    engine = setting("TTS_ENGINE")
    if setting("TTS_PROVIDER") == "hybrid":
        engine = setting("TTS_ZH_ENGINE")
        if not engine:
            raise AppError("请安装小雅 TTS Engine，并将 termux-tts-engines 中的包名填入 TTS_ZH_ENGINE")
    args = ["termux-tts-speak", "-s", "MUSIC", "-l", setting("TTS_LANGUAGE", "en"),
            "-n", ("CN" if setting("TTS_LANGUAGE", "zh") == "zh" else "US"), "-r",
            str(number("TTS_RATE", 0.85, 0.3, 2))]
    if engine:
        args += ["-e", engine]
    command(args, timeout=number("TTS_TIMEOUT", 180, 5, 600), text=text)
    time.sleep(number("PLAYBACK_COOLDOWN", 0.8, 0, 5))


def record(directory):
    source, target = directory / "speech.m4a", directory / "speech.wav"
    seconds = int(number("RECORD_SECONDS", 120, 2, 120))
    info = command(["termux-microphone-record", "-i"])
    try:
        if json.loads(info).get("isRecording"):
            raise AppError("已有录音正在进行，请先结束后重试")
    except (ValueError, AttributeError):
        pass
    # Stop even if starting the API times out after the Android recorder starts.
    try:
        command(["termux-microphone-record", "-f", str(source), "-e", "aac",
                 "-r", "16000", "-c", "1", "-l", str(seconds)])
        print(f"正在录音：说完按回车，最多 {seconds} 秒。", flush=True)
        ready, _, _ = select.select([sys.stdin], [], [], seconds)
        if ready and not sys.stdin.readline():
            raise EOFError
    finally:
        command(["termux-microphone-record", "-q"])
    command(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
             "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(target)])
    if target.stat().st_size < 1000:
        raise AppError("录音太短，请重新录制")
    return target


def doctor():
    ok = True
    provider = setting("TTS_PROVIDER", "siliconflow")
    names = ["termux-microphone-record", "ffmpeg"]
    if provider in ("siliconflow", "hybrid"):
        names.append("termux-media-player")
    if provider in ("android", "hybrid"):
        names.append("termux-tts-speak")
    if provider == "hybrid":
        configured = bool(setting("TTS_ZH_ENGINE"))
        print("已配置中文引擎（是否安装需实测）" if configured else "缺少 TTS_ZH_ENGINE：请安装小雅引擎并填写包名")
        ok &= configured
    for name in names:
        found = bool(shutil.which(name))
        print(f"{'OK' if found else '缺少'}  {name}")
        ok &= found
    for prefix in ("ASR", "LLM"):
        found = bool(setting(prefix + "_API_KEY"))
        print(f"{'已配置' if found else '未配置'}  {prefix}_API_KEY（不显示内容）")
        ok &= found
    if provider in ("siliconflow", "hybrid"):
        configured = bool(setting("TTS_API_KEY") or (setting("TTS_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/") == "https://api.siliconflow.cn/v1" and setting("ASR_API_KEY")))
        print("已配置云端 TTS 密钥（可复用 ASR 密钥）" if configured else "缺少 TTS_API_KEY")
        ok &= configured
    print("此检查不调用云端；录音权限、离线音色及蓝牙播放请按 README 实测。")
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser(description="Voice Sprite 儿童知识伙伴")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--auto", action="store_true", help="自动断句并连续对话（需要 PulseAudio）")
    modes.add_argument("--text", action="store_true", help="纯文字模式，不调用 ASR/TTS，可在电脑测试")
    parser.add_argument("--doctor", action="store_true", help="检查命令和密钥配置")
    parser.add_argument("--tts-test", action="store_true", help="测试当前 TTS；siliconflow 模式会调用云端并计费")
    parser.add_argument("--tts-language", choices=("zh", "en"), help="配合 --tts-test 单独试听，不保存语言设置")
    args = parser.parse_args()
    if args.tts_language and not args.tts_test:
        parser.error("--tts-language 需要与 --tts-test 一起使用")
    configure_log(ROOT / "logs")
    load_env(ROOT / ".env")
    if args.doctor:
        return doctor()
    preferences = Preferences(ROOT / "conversation.json")
    os.environ["TTS_LANGUAGE"] = preferences.language
    os.environ["TTS_REGION"] = "CN" if preferences.language == "zh" else "US"
    if args.tts_test:
        if args.tts_language:
            os.environ["TTS_LANGUAGE"] = args.tts_language
        speak("你好，我们一起探索宇宙吧。" if setting("TTS_LANGUAGE") == "zh" else "Hello, let's explore space!")
        return 0
    required = ("LLM",) if args.text else ("ASR", "LLM")
    for prefix in required:
        for suffix in ("API_KEY", "BASE_URL", "MODEL"):
            if not setting(prefix + "_" + suffix):
                raise AppError(f"请在 .env 填写 {prefix}_{suffix}")
    print("自动对话：直接说话，Ctrl+C 退出。" if args.auto else
          "知识伙伴：/quit 退出，/reset 清空上下文，/repeat 重播上一句，/slow 降低语速。")
    print("录音会发送给 ASR；对话发送给大模型；云端 TTS 会上传回答文字并计费。")
    load_persona()  # Fail before capturing audio or calling cloud services.
    source = prepare_auto() if args.auto else None
    history, last = [], ""
    memory = Memory(ROOT / "memory.json")
    wake = WakeSession(number("SLEEP_AFTER_SECONDS", 60, 5, 3600)) if args.auto and setting("WAKE_ENABLED", "1") == "1" else None
    try:
        introduced = introduce(preferences, args.text)
        if introduced and wake:
            wake.active = True
            wake.replied(time.monotonic())
            print("介绍完成，可以直接说话；待机后连续叫两遍当前名字可唤起。")
    except (AppError, PreferenceError, SpeechError) as exc:
        print("首次介绍未完成：", exc, file=sys.stderr)
        if not args.text:
            notify_voice("error")
    if wake and not wake.active:
        print(f"待机：请连续叫两遍名字“{preferences.name}”；有声音时仍会上传 ASR 识别。")
    while True:
        entry = "" if args.auto else input("\n输入：" if args.text else "按回车开始录音（请等音箱播放完），或输入命令：").strip()
        if entry == "/quit":
            return 0
        if entry == "/reset":
            history.clear()
            last = ""
            print("已清空上下文")
            continue
        if entry == "/slow":
            rate_key = "CLOUD_TTS_SPEED" if speech_provider() == "siliconflow" else "TTS_RATE"
            os.environ[rate_key] = str(max(0.3, number(rate_key, 1, 0.25, 4) - 0.1))
            print("朗读语速：", setting(rate_key))
            continue
        try:
            preferences = Preferences(ROOT / "conversation.json")
            os.environ["TTS_LANGUAGE"] = preferences.language
            if wake and wake.expire(time.monotonic()):
                emit("session", action="idle_sleep")
                print(f"已静默待机，请连续叫两遍“{preferences.name}”。")
            if entry == "/repeat":
                if last:
                    print(last)
                    if not args.text:
                        speak(last)
                continue
            if entry.startswith("/"):
                print("未知命令")
                continue
            if not args.text:
                if entry:
                    print("语音模式请直接按回车；文字模式使用 --text")
                    continue
                with tempfile.TemporaryDirectory(prefix="voice-sprite-") as tmp:
                    idle = number("LISTEN_TIMEOUT", 30, 5, 300)
                    if wake and wake.active:
                        idle = max(0.2, min(idle, wake.idle_seconds - (time.monotonic() - wake.last_reply)))
                    path = record_auto(Path(tmp), source, idle) if args.auto else record(Path(tmp))
                    if path is None:
                        emit("listen_idle")
                        print("未检测到足够长的声音，继续监听（未调用云端）。")
                        continue
                    print("正在识别……")
                    entry = transcribe(path)
                print("你：", entry)
            if not entry:
                continue
            # Reload after capture too: edits made while listening apply to this turn.
            preferences = Preferences(ROOT / "conversation.json")
            os.environ["TTS_LANGUAGE"] = preferences.language
            if wake:
                action = wake.accept(entry, preferences.name, time.monotonic())
                emit("wake_decision", action=action, characters=len(entry))
                if action in ("ignore", "sleep"):
                    if action == "sleep":
                        print("已进入待机。")
                    continue
                if action == "wake":
                    print(preferences.name + "：你好，我在。")
                    previous_language = os.environ.get("TTS_LANGUAGE", "zh")
                    try:
                        os.environ["TTS_LANGUAGE"] = "zh"
                        speak("你好，我在。")
                    finally:
                        os.environ["TTS_LANGUAGE"] = previous_language
                    wake.replied(time.monotonic())
                    continue
            assistance = help_reply(entry, preferences.name)
            if assistance is not None:
                last = assistance
                print(preferences.name + "：", last)
                if not args.text:
                    previous = os.environ.get("TTS_LANGUAGE", "zh")
                    try:
                        os.environ["TTS_LANGUAGE"] = "zh"
                        speak(last)
                    finally:
                        os.environ["TTS_LANGUAGE"] = previous
                if wake:
                    wake.replied(time.monotonic())
                continue
            confirmation = memory.handle(entry)
            if confirmation is None:
                confirmation = preferences.handle(entry)
            if confirmation is not None:
                history.clear()
                os.environ["TTS_LANGUAGE"] = preferences.language
                os.environ["TTS_REGION"] = "CN" if preferences.language == "zh" else "US"
                last = confirmation
            else:
                print("正在生成回答……")
                last = reply(entry, history, preferences)
            print(preferences.name + "：", last)
            if not args.text:
                speak(last)
            if wake:
                wake.replied(time.monotonic())
        except (AppError, AudioError, PreferenceError, SpeechError) as exc:
            emit("turn_error", error_type=type(exc).__name__, cause_type=type(exc.__cause__).__name__, action="paused" if args.auto else "retry")
            print("错误：", exc, file=sys.stderr)
            if not args.text:
                notify_voice("paused" if args.auto else "error")
            if args.auto:
                answer = input("自动监听已暂停；回车继续，输入 /quit 退出：").strip()
                emit("session", action="quit" if answer == "/quit" else "resume")
                if answer == "/quit":
                    return 0
            else:
                print("本轮已停止，可重试；若仅播放失败，可输入 /repeat。")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\n已退出")
    except (AppError, PreferenceError, SpeechError) as exc:
        print("错误：", exc, file=sys.stderr)
        sys.exit(1)
