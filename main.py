import asyncio
import json
import logging
import os
import random
import re
from pathlib import Path

import httpx
import yaml
from pyrogram import Client, filters
from pyrogram.types import Message
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
REPLY_DELAY_MIN = float(os.getenv("REPLY_DELAY_MIN", "15"))
REPLY_DELAY_MAX = float(os.getenv("REPLY_DELAY_MAX", "90"))

LEOMATCH_BOT = "leomatchbot"
CONTACTS_FILE = Path("data/contacts.json")
PERSONA_FILE = Path("persona.yml")
MATCH_KEYWORDS = {"взаимн", "симпати", "лайк", "match", "💕", "❤️", "🔥", "нравит"}

# ─── Persona ─────────────────────────────────────────────────────────────────
def load_persona() -> dict:
    with open(PERSONA_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_system_prompt(persona: dict, mode: str = "chat") -> str:
    if mode == "opener":
        task = (
            "написать ОПЕНЕР — одно первое сообщение (1–2 предложения максимум) "
            "девушке, с которой у тебя взаимный лайк в приложении знакомств Дайвинчик."
        )
        rules = (
            "• Сообщение живое и нативное — никто не должен догадаться, что это бот\n"
            "• Никакого «Привет, как дела?» или шаблонного флирта\n"
            "• Лёгкий юмор, подкол или интригующий вопрос — приветствуется\n"
            "• Если известно имя — используй органично, не в самом начале\n"
        )
    else:
        task = (
            "поддерживать живой диалог с девушкой из приложения знакомств Дайвинчик. "
            "Ты уже написал ей первым, она ответила — продолжай общение естественно."
        )
        rules = (
            "• Читай контекст и отвечай по смыслу — не повторяй уже сказанное\n"
            "• Задавай вопросы и проявляй интерес, но не заваливай ими\n"
            "• Если разговор идёт хорошо и уместно — можно намекнуть на встречу\n"
            "• Отвечай коротко (1–3 предложения), если её сообщение тоже короткое\n"
        )

    return (
        f"Ты — {persona['name']}, {persona['age']} лет. {persona['about'].strip()}.\n\n"
        f"Характер: {persona['character'].strip()}.\n"
        f"Как пишешь: {persona['writing_style'].strip()}.\n"
        f"Табу: {persona['taboo'].strip()}.\n\n"
        f"Задача: {task}\n\n"
        f"Правила:\n"
        f"• Пиши живо и нативно — никто не должен догадаться, что это ИИ\n"
        f"• Веди себя как ты, не как бот и не как пикап-гуру\n"
        f"{rules}"
        f"• Отвечай ТОЛЬКО текстом сообщения — без кавычек и пояснений"
    )


# ─── Contacts (persistent) ───────────────────────────────────────────────────
def load_contacts() -> dict:
    if CONTACTS_FILE.exists():
        with open(CONTACTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_contacts(data: dict) -> None:
    CONTACTS_FILE.parent.mkdir(exist_ok=True)
    with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


contacts: dict = load_contacts()


# ─── Ollama ──────────────────────────────────────────────────────────────────
async def call_ollama(system: str, history: list[dict], user_prompt: str | None = None) -> str:
    messages = [{"role": "system", "content": system}]
    messages.extend(history)
    if user_prompt:
        messages.append({"role": "user", "content": user_prompt})

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.85},
    }
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(f"{OLLAMA_URL}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


# ─── Parsing ─────────────────────────────────────────────────────────────────
def parse_match_info(text: str) -> dict | None:
    username = None
    for m in re.finditer(r"@([a-zA-Z0-9_]{5,32})", text):
        candidate = m.group(1)
        if candidate.lower() != LEOMATCH_BOT.lower():
            username = candidate
            break
    if not username:
        m = re.search(r"t\.me/([a-zA-Z0-9_]{5,32})", text)
        if m:
            username = m.group(1)
    if not username:
        return None
    name_match = re.search(r"\b([А-ЯЁ][а-яё]{2,})\b", text)
    return {"username": username, "name": name_match.group(1) if name_match else None}


# ─── Handlers ────────────────────────────────────────────────────────────────
app = Client("leomatch_session", api_id=API_ID, api_hash=API_HASH)


@app.on_message(filters.chat(LEOMATCH_BOT))
async def on_match_notification(client: Client, message: Message):
    text = message.text or message.caption or ""
    if not any(kw in text.lower() for kw in MATCH_KEYWORDS):
        return

    logger.info("Match notification: %s", text[:120])
    info = parse_match_info(text)
    if not info:
        logger.warning("Could not extract username from: %s", text[:120])
        return

    key = info["username"].lower()
    if key in contacts:
        logger.info("@%s already in contacts, skipping opener", key)
        return

    logger.info("New match: @%s (name=%s)", key, info["name"])

    persona = load_persona()
    user_prompt = (
        f"Напиши опенер девушке по имени {info['name']}."
        if info["name"]
        else "Напиши опенер девушке (имя неизвестно)."
    )
    try:
        opener = await call_ollama(build_system_prompt(persona, "opener"), [], user_prompt)
    except Exception as exc:
        logger.error("Ollama error: %s", exc)
        return

    logger.info("Opener: %s", opener)

    delay = random.uniform(5, 15)
    logger.info("Waiting %.1fs before sending...", delay)
    await asyncio.sleep(delay)

    try:
        await client.send_message(info["username"], opener)
        contacts[key] = {
            "username": info["username"],
            "name": info["name"],
            "history": [{"role": "assistant", "content": opener}],
        }
        save_contacts(contacts)
        logger.info("Opener sent to @%s", key)
    except Exception as exc:
        logger.error("Failed to send to @%s: %s", key, exc)


@app.on_message(filters.private & ~filters.bot & ~filters.me)
async def on_private_message(client: Client, message: Message):
    sender = message.from_user
    if not sender or not sender.username:
        return

    key = sender.username.lower()
    if key not in contacts:
        return  # не из Дайвинчика — не трогаем

    text = message.text or message.caption or ""
    if not text:
        return

    logger.info("Message from @%s: %s", key, text[:80])

    # Сохраняем сообщение девушки сразу
    contacts[key]["history"].append({"role": "user", "content": text})
    save_contacts(contacts)

    persona = load_persona()
    try:
        reply = await call_ollama(
            build_system_prompt(persona, "chat"),
            contacts[key]["history"],
        )
    except Exception as exc:
        logger.error("Ollama error: %s", exc)
        return

    logger.info("Reply to @%s: %s", key, reply)

    delay = random.uniform(REPLY_DELAY_MIN, REPLY_DELAY_MAX)
    logger.info("Waiting %.1fs...", delay)
    await asyncio.sleep(delay)

    try:
        await client.send_message(contacts[key]["username"], reply)
        contacts[key]["history"].append({"role": "assistant", "content": reply})
        save_contacts(contacts)
        logger.info("Replied to @%s", key)
    except Exception as exc:
        logger.error("Failed to reply to @%s: %s", key, exc)


if __name__ == "__main__":
    logger.info("LeoMatch userbot started. Listening for matches...")
    app.run()
