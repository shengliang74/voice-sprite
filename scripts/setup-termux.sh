#!/data/data/com.termux/files/usr/bin/bash
set -eu
if [ -z "${TERMUX_VERSION:-}" ]; then
  echo "请在安卓手机的 Termux 中运行此脚本。"
  exit 1
fi
pkg update -y
pkg install -y python termux-api ffmpeg pulseaudio
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  (umask 077; cp .env.example .env)
fi
if [ ! -f persona.txt ]; then
  cp persona.example.txt persona.txt
fi
if [ ! -f memory.json ]; then
  cp memory.example.json memory.json
fi
chmod 600 .env memory.json
echo "安装完成。编辑 .env 填写两个 API Key，然后运行 python voice_sprite.py --doctor"
