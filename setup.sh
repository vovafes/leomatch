#!/usr/bin/env bash
set -e

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║     LeoMatch — установка         ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# Python check
if ! command -v python3 &>/dev/null; then
    echo "❌  Python 3 не найден. Установи Python 3.10+"
    exit 1
fi

PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
if [ "$PY_MAJOR" -lt 3 ] || [ "$PY_MINOR" -lt 10 ]; then
    echo "❌  Нужен Python 3.10+. У тебя: $(python3 --version)"
    exit 1
fi
echo "✅  Python $(python3 --version)"

# Virtual environment
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✅  Виртуальное окружение создано (.venv/)"
else
    echo "✅  Виртуальное окружение уже есть"
fi

# Activate
# shellcheck disable=SC1091
source .venv/bin/activate

# Dependencies
echo "⏳  Устанавливаю зависимости..."
pip install -q -r requirements.txt
echo "✅  Зависимости установлены"

# .env setup
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "  ┌─────────────────────────────────────┐"
    echo "  │  Настройка Telegram API             │"
    echo "  └─────────────────────────────────────┘"
    echo "  Зайди на https://my.telegram.org"
    echo "  → API development tools → создай приложение"
    echo ""
    read -rp "  API_ID:   " api_id
    read -rp "  API_HASH: " api_hash
    sed -i "s/API_ID=12345678/API_ID=$api_id/" .env
    sed -i "s/API_HASH=abcdef.*/API_HASH=$api_hash/" .env
    echo "✅  .env создан"
else
    echo "✅  .env уже существует"
fi

# Ollama check
echo ""
if command -v ollama &>/dev/null; then
    echo "✅  Ollama найдена: $(ollama --version 2>/dev/null || echo 'ok')"
else
    echo "⚠️   Ollama не найдена."
    echo "     Установи: https://ollama.com/download"
    echo "     Затем: ollama pull llama3"
fi

# data dir
mkdir -p data
echo "✅  Папка data/ создана"

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║  Готово! Следующие шаги:                     ║"
echo "  ║                                              ║"
echo "  ║  1. Отредактируй persona.yml                 ║"
echo "  ║     (имя, возраст, стиль общения)            ║"
echo "  ║                                              ║"
echo "  ║  2. Запусти Ollama:                          ║"
echo "  ║     ollama serve                             ║"
echo "  ║     ollama pull llama3                       ║"
echo "  ║                                              ║"
echo "  ║  3. Запусти бота:                            ║"
echo "  ║     source .venv/bin/activate                ║"
echo "  ║     python main.py                           ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""
