#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p dist
tar --exclude='__pycache__' --exclude='*.pyc' -czf dist/voice-sprite.tar.gz README.md LICENSE .env.example .gitignore voice_sprite.py auto_audio.py dialogue.py cloud_speech.py memory_wake.py usage_help.py event_log.py memory.example.json persona.example.txt assets/prompts scripts tests
echo "已生成 dist/voice-sprite.tar.gz（不含 .env、密钥和 Git 历史）"
