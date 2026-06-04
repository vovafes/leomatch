import asyncio
import json
import logging
import re

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
from utils.delays import human_delay, check_rate_limit, should_skip_reply, is_sleep_time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Client("leomatch_session", api_id=config.API_ID, api_hash=config.API_HASH)

# Chat IDs where bot just sent — used to ignore our own outgoing events
_bot_sent: set[int] = set()


# ─── Helpers ─────────────────────────────────────────────────────────────────

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


async def _maybe_send_sticker(client: Client, chat_id: int, username: str):
    raw  = await get_setting("stickers", "[]")
    prob = int(await get_setting("sticker_probability", "15")) / 100
    try:
        ids = json.loads(raw)
    except Exception:
        return
    if not ids or not (prob > 0):
        return
    import random
    if random.random() >= prob:
        return
    sticker_id = random.choice(ids)
    await asyncio.sleep(random.uniform(1, 3))
    _bot_sent.add(chat_id)
    try:
        await client.send_sticker(username, sticker_id)
        logger.info("Sticker sent to %s", username)
    except Exception as exc:
        logger.warning("Failed to send sticker: %s", exc)


# ─── Match notification ───────────────────────────────────────────────────────

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
        return

    try:
        tg_user = await client.get_users(info["username"])
    except Exception as exc:
        logger.error("get_users(%s) failed: %s", info["username"], exc)
        return

    chat = await get_or_create_chat(tg_user.id, info["username"], info["name"])
    if chat["status"] == "paused":
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
        logger.error("Failed to send opener: %s", exc)


# ─── Incoming messages ────────────────────────────────────────────────────────

@app.on_message(filters.private & ~filters.bot & ~filters.outgoing)
async def on_private_message(client: Client, message: Message):
    sender = message.from_user
    if not sender:
        return
    text = message.text or message.caption or ""
    if not text:
        return

    chat = await get_or_create_chat(sender.id, sender.username or str(sender.id))

    # Only reply to Дайвинчик contacts that already have an opener
    context = await get_context(chat["id"])
    if not context:
        return

    if chat["status"] == "paused":
        await save_message(chat["id"], "her", text)
        return

    mode = await _get_mode()
    if mode == "OFF":
        await save_message(chat["id"], "her", text)
        return

    if await is_sleep_time():
        logger.info("Sleep time, skipping reply to @%s", sender.username)
        await save_message(chat["id"], "her", text)
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
        await save_message(chat["id"], "her", text)
        return

    if should_skip_reply():
        logger.info("Randomly skipping reply to @%s", sender.username)
        await save_message(chat["id"], "her", text)
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
        await _maybe_send_sticker(client, sender.id, username)
    except Exception as exc:
        logger.error("Failed to reply to @%s: %s", sender.username, exc)


# ─── Outgoing message handler (detect manual sends) ──────────────────────────

@app.on_message(filters.private & filters.outgoing)
async def on_outgoing_message(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id in _bot_sent:
        _bot_sent.discard(chat_id)
        return
    await set_chat_status(chat_id, "paused")
    logger.info("Manual send detected for %d, chat paused", chat_id)


# ─── Entry point ─────────────────────────────────────────────────────────────

async def main():
    await init_db()

    # Apply saved settings to config
    config.REPLY_DELAY_MIN = float(
        await get_setting("reply_delay_min", str(config.REPLY_DELAY_MIN))
    )
    config.REPLY_DELAY_MAX = float(
        await get_setting("reply_delay_max", str(config.REPLY_DELAY_MAX))
    )
    config.MAX_MESSAGES_PER_HOUR = int(
        await get_setting("max_per_hour", str(config.MAX_MESSAGES_PER_HOUR))
    )

    tasks = [app.start()]
    if config.WEB_ENABLED:
        from web.server import start_web
        tasks.append(start_web())

    await asyncio.gather(*tasks)
    logger.info("LeoMatch started. Mode: %s", config.MODE)
    await asyncio.Event().wait()


if __name__ == "__main__":
    app.run(main())
