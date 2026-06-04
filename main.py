import asyncio
import random
import re
import os
import logging

import httpx
from pyrogram import Client, filters
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

LEOMATCH_BOT = "leomatchbot"

# ─── НАСТРОЙ ПОД СЕБЯ ────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
Ты — [ИМЯ], [ВОЗРАСТ] лет. [КРАТКО: кем работаешь / чем занимаешься / интересы].

Характер: [например: ироничный, спокойный, с самоиронией, не душнила].

Как пишешь: [например: короткие фразы, с маленькой буквы, без смайлов, \
иногда "жиза", "рил", "норм", не используешь восклицательные знаки].

Задача: написать ОПЕНЕР — одно первое сообщение (1–2 предложения максимум) \
девушке, с которой у тебя взаимный лайк в приложении знакомств Дайвинчик.

Правила:
• Сообщение живое и нативное — никто не должен догадаться, что это бот
• Никакого "Привет, как дела?" или шаблонного флирта
• Приветствуется лёгкий юмор, подкол, интригующий вопрос
• Если известно имя девушки — используй его органично (не в самом начале в лоб)
• Никакой пошлости, пикап-гуру техник, банальных комплиментов внешности
• Отвечай ТОЛЬКО текстом самого сообщения — без кавычек, без объяснений\
"""
# ─────────────────────────────────────────────────────────────────────────────

MATCH_KEYWORDS = {"взаимн", "симпати", "лайк", "match", "💕", "❤️", "🔥", "нравит"}


def parse_match_info(text: str) -> dict | None:
    """Extract username and optionally a Cyrillic first name from a leomatchbot notification."""
    username = None

    # Priority: @username mention
    for m in re.finditer(r"@([a-zA-Z0-9_]{5,32})", text):
        candidate = m.group(1)
        if candidate.lower() != LEOMATCH_BOT.lower():
            username = candidate
            break

    # Fallback: t.me/username link
    if not username:
        m = re.search(r"t\.me/([a-zA-Z0-9_]{5,32})", text)
        if m:
            username = m.group(1)

    if not username:
        return None

    # Optional: first Cyrillic capitalized word as name
    name_match = re.search(r"\b([А-ЯЁ][а-яё]{2,})\b", text)
    name = name_match.group(1) if name_match else None

    return {"username": username, "name": name}


async def generate_opener(name: str | None) -> str:
    user_prompt = (
        f"Напиши опенер девушке по имени {name}."
        if name
        else "Напиши опенер девушке (имя неизвестно)."
    )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.85},
    }
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(f"{OLLAMA_URL}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


app = Client("leomatch_session", api_id=API_ID, api_hash=API_HASH)


@app.on_message(filters.chat(LEOMATCH_BOT))
async def on_leomatch_message(client: Client, message):
    text = message.text or message.caption or ""

    if not any(kw in text.lower() for kw in MATCH_KEYWORDS):
        return

    logger.info("Match notification: %s", text[:120])

    info = parse_match_info(text)
    if not info:
        logger.warning("Could not extract username from: %s", text[:120])
        return

    username, name = info["username"], info["name"]
    logger.info("Matched with @%s (name=%s)", username, name)

    try:
        opener = await generate_opener(name)
    except Exception as exc:
        logger.error("Ollama error: %s", exc)
        return

    logger.info("Opener: %s", opener)

    delay = random.uniform(5, 15)
    logger.info("Waiting %.1fs before sending...", delay)
    await asyncio.sleep(delay)

    try:
        await client.send_message(username, opener)
        logger.info("Sent to @%s", username)
    except Exception as exc:
        logger.error("Failed to send to @%s: %s", username, exc)


if __name__ == "__main__":
    app.run()
