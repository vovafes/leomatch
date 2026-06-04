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

# Venv
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✅  Виртуальное окружение создано"
else
    echo "✅  Виртуальное окружение уже есть"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# Deps
echo "⏳  Устанавливаю зависимости..."
pip install -q -r requirements.txt
echo "✅  Зависимости установлены"

# .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "  ┌─────────────────────────────────────────────────┐"
    echo "  │  Настройка Telegram API                         │"
    echo "  │  Зайди: https://my.telegram.org                 │"
    echo "  │  → API development tools → создай приложение    │"
    echo "  └─────────────────────────────────────────────────┘"
    echo ""
    read -rp "  API_ID:   " api_id
    read -rp "  API_HASH: " api_hash
    sed -i "s/API_ID=12345678/API_ID=$api_id/" .env
    sed -i "s/API_HASH=abcdef.*/API_HASH=$api_hash/" .env

    echo ""
    echo "  ┌─────────────────────────────────────────────────┐"
    echo "  │  Groq API Key (бесплатно, быстро)               │"
    echo "  │  Получи: https://console.groq.com → API Keys    │"
    echo "  └─────────────────────────────────────────────────┘"
    echo ""
    read -rp "  OPENAI_API_KEY: " groq_key
    sed -i "s/OPENAI_API_KEY=gsk_.*/OPENAI_API_KEY=$groq_key/" .env
    echo "✅  .env создан"
else
    echo "✅  .env уже существует"
fi

# data dir
mkdir -p data
echo "✅  Папка data/ создана"

echo ""
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║  Готово! Следующие шаги:                             ║"
echo "  ║                                                      ║"
echo "  ║  1. Отредактируй persona.yml                         ║"
echo "  ║     (заполни имя, возраст, стиль общения)            ║"
echo "  ║                                                      ║"
echo "  ║  2. Запусти бота:                                    ║"
echo "  ║     source .venv/bin/activate && python main.py      ║"
echo "  ║                                                      ║"
echo "  ║  3. Dashboard: http://127.0.0.1:8082                 ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo ""
