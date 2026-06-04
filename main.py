import asyncio
import logging
import re
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message

import config
from ai.generator import generate_message, is_spam, is_suspicious
from db.models import (
    init_db,
    get_or_create_chat,
    save_message,
    get_context,
    set_chat_status,
    get_setting,
)
from utils.delays import human_delay, check_rate_limit, should_skip_reply

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Client("leomatch_session", api_id=config.API_ID, api_hash=config.API_HASH)

# Chat IDs where bot just sent — used to ignore our own outgoing events
_bot_sent: set[int] = set()
# Tracks last incoming message time per telegram_chat_id
_last_message_time: dict[int, datetime] = {}


# ─── Helper ──────────────────────────────────────────────────────────────────

def _parse_match_info(text: str) -> dict | None:
    username = None
    for m in re.finditer(r"@([a-zA-Z0-9_]{5,32})", text):
        candidate = m.group(1)
        if candidate.lower() != config.LEOMATCH_BOT.lower():
            username = candidate
            break
    if not username:
        m = re.search(r"t\.me/([a-zA-Z0-9_]{5,32})", text)
        if m:
            username = m.group(1)
    if not username:
        return None
    name_m = re.search(r"\b([А-ЯЁ][а-яё]{2,})\b", text)
    return {"username": username, "name": name_m.group(1) if name_m else None}


async def _get_mode() -> str:
    return await get_setting("mode", config.MODE)


async def _send(chat_id: int, username: str, text: str):
    _bot_sent.add(chat_id)
    try:
        await app.send_message(username, text)
    except FloodWait as e:
        logger.warning("FloodWait %ds, sleeping...", e.value)
        await asyncio.sleep(e.value + 5)
        await app.send_message(username, text)


# ─── Match notification handler ──────────────────────────────────────────────

@app.on_message(filters.chat(config.LEOMATCH_BOT))
async def on_match_notification(client: Client, message: Message):
    text = message.text or message.caption or ""
    if not any(kw in text.lower() for kw in config.MATCH_KEYWORDS):
        return

    logger.info("Match notification: %s", text[:120])
    info = _parse_match_info(text)
    if not info:
        logger.warning("Could not parse username from: %s", text[:80])
        return

    mode = await _get_mode()
    if mode == "OFF":
        logger.info("Mode=OFF, skipping opener")
        return

    try:
        tg_user = await client.get_users(info["username"])
    except Exception as exc:
        logger.error("get_users(%s) failed: %s", info["username"], exc)
        return

    chat = await get_or_create_chat(tg_user.id, info["username"], info["name"])
    if chat["status"] == "paused":
        logger.info("@%s is paused, skipping", info["username"])
        return

    context = await get_context(chat["id"])
    if context:
        logger.info("@%s already has history, skipping opener", info["username"])
        return

    logger.info("New match: @%s (name=%s)", info["username"], info["name"])

    user_prompt = (
        f"Напиши опенер девушке по имени {info['name']}."
        if info["name"]
        else "Напиши опенер девушке (имя неизвестно)."
    )
    try:
        opener = await generate_message([], user_prompt, mode="opener")
    except Exception as exc:
        logger.error("AI error: %s", exc)
        return

    logger.info("Opener for @%s: %s", info["username"], opener)

    if mode == "HYBRID":
        logger.info("[HYBRID] Would send to @%s: %s", info["username"], opener)
        return

    await asyncio.sleep(5)
    try:
        await _send(tg_user.id, info["username"], opener)
        await save_message(chat["id"], "me", opener)
        logger.info("Opener sent to @%s", info["username"])
    except Exception as exc:
        logger.error("Failed to send opener to @%s: %s", info["username"], exc)


# ─── Incoming private message handler ────────────────────────────────────────

@app.on_message(filters.private & ~filters.bot & ~filters.outgoing)
async def on_private_message(client: Client, message: Message):
    sender = message.from_user
    if not sender:
        return

    text = message.text or message.caption or ""
    if not text:
        return

    chat = await get_or_create_chat(sender.id, sender.username or str(sender.id))

    # Only reply to Дайвинчик contacts that have history
    context = await get_context(chat["id"])
    if not context:
        return

    _last_message_time[sender.id] = datetime.now()

    if chat["status"] == "paused":
        return

    mode = await _get_mode()
    if mode == "OFF":
        return

    if is_spam(text):
        logger.info("Spam from @%s, ignoring", sender.username)
        return

    if is_suspicious(text):
        await set_chat_status(sender.id, "paused")
        logger.warning("Suspicious message from @%s, paused", sender.username)
        return

    if not check_rate_limit(chat["id"]):
        logger.info("Rate limit hit for @%s", sender.username)
        return

    if should_skip_reply():
        logger.info("Randomly skipping reply to @%s", sender.username)
        return

    await save_message(chat["id"], "her", text)
    full_context = await get_context(chat["id"], limit=config.CONTEXT_WINDOW)

    try:
        reply = await generate_message(full_context, mode="chat")
    except Exception as exc:
        logger.error("AI error: %s", exc)
        return

    logger.info("Reply to @%s: %s", sender.username, reply)

    if mode == "HYBRID":
        logger.info("[HYBRID] Would send to @%s: %s", sender.username, reply)
        return

    username = sender.username or str(sender.id)
    try:
        await human_delay(client, sender.id, reply)
        await _send(sender.id, username, reply)
        await save_message(chat["id"], "me", reply)
        logger.info("Replied to @%s", sender.username)
    except Exception as exc:
        logger.error("Failed to reply to @%s: %s", sender.username, exc)


# ─── Outgoing message handler (detect manual sends) ──────────────────────────

@app.on_message(filters.private & filters.outgoing)
async def on_outgoing_message(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id in _bot_sent:
        _bot_sent.discard(chat_id)
        return
    # User sent manually → pause this chat
    await set_chat_status(chat_id, "paused")
    logger.info("Manual send detected for %d, chat paused", chat_id)


# ─── Silence checker ─────────────────────────────────────────────────────────

async def silence_checker():
    while True:
        await asyncio.sleep(300)
        now = datetime.now()
        for tg_id, last_time in list(_last_message_time.items()):
            minutes_silent = (now - last_time).total_seconds() / 60
            if minutes_silent < config.SILENCE_TIMEOUT_MINUTES:
                continue
            try:
                chat = await get_or_create_chat(tg_id, str(tg_id))
                if chat["status"] != "active":
                    continue
                mode = await _get_mode()
                if mode == "OFF":
                    continue
                context = await get_context(chat["id"])
                nudge = await generate_message(context, mode="nudge")
                username = chat["username"] or str(tg_id)
                await _send(tg_id, username, nudge)
                await save_message(chat["id"], "me", nudge)
                _last_message_time[tg_id] = now
                logger.info("Nudge sent to @%s", username)
            except Exception as exc:
                logger.error("Silence checker error for %d: %s", tg_id, exc)


# ─── Entry point ─────────────────────────────────────────────────────────────

async def main():
    await init_db()

    tasks = [app.start()]
    if config.WEB_ENABLED:
        from web.server import start_web
        tasks.append(start_web())

    await asyncio.gather(*tasks)
    asyncio.create_task(silence_checker())

    logger.info("LeoMatch started. Mode: %s", config.MODE)
    await asyncio.Event().wait()


if __name__ == "__main__":
    app.run(main())
