#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p dist
tar --exclude='__pycache__' --exclude='*.pyc' -czf dist/voice-sprite.tar.gz README.md LICENSE .env.example .gitignore voice_sprite.py auto_audio.py dialogue.py cloud_speech.py persona.example.txt scripts tests
echo "已生成 dist/voice-sprite.tar.gz（不含 .env、密钥和 Git 历史）"
