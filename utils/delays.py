import asyncio
import random
from collections import defaultdict
from datetime import datetime, timedelta

from pyrogram import Client
from pyrogram.enums import ChatAction

import config

message_counts: dict[int, list[datetime]] = defaultdict(list)


def should_skip_reply() -> bool:
    return random.random() < 0.03


def check_rate_limit(chat_id: int) -> bool:
    now = datetime.now()
    hour_ago = now - timedelta(hours=1)
    message_counts[chat_id] = [t for t in message_counts[chat_id] if t > hour_ago]
    if len(message_counts[chat_id]) >= config.MAX_MESSAGES_PER_HOUR:
        return False
    message_counts[chat_id].append(now)
    return True


async def human_delay(client: Client, chat_id: int, text: str):
    base = random.uniform(config.REPLY_DELAY_MIN, config.REPLY_DELAY_MAX)
    await asyncio.sleep(base * 0.7)
    try:
        await client.send_chat_action(chat_id, ChatAction.TYPING)
    except Exception:
        pass
    await asyncio.sleep(min(len(text) * 0.055, 7))


async def is_sleep_time() -> bool:
    from db.models import get_setting
    if await get_setting("sleep_enabled", "false") != "true":
        return False
    now_h = datetime.now().hour
    start = int(await get_setting("sleep_start", "23"))
    end   = int(await get_setting("sleep_end",   "8"))
    if start > end:          # overnight window, e.g. 23–08
        return now_h >= start or now_h < end
    return start <= now_h < end
