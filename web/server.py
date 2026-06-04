import json
import os
from aiohttp import web

import config
from ai.generator import load_persona, save_persona
from db.models import (
    get_all_chats,
    get_messages_for_chat,
    set_chat_status,
    get_stats,
    get_activity_stats,
    get_setting,
    set_setting,
)


def _j(obj):
    return json.dumps(obj, ensure_ascii=False, default=str)


# ── Chats ─────────────────────────────────────────────────────────────────────

async def api_chats(request):
    return web.Response(text=_j(await get_all_chats()), content_type="application/json")


async def api_messages(request):
    chat_id = int(request.match_info["chat_id"])
    return web.Response(text=_j(await get_messages_for_chat(chat_id)), content_type="application/json")


async def api_status(request):
    data = await request.json()
    await set_chat_status(data["telegram_chat_id"], data["status"])
    return web.json_response({"ok": True})


# ── Stats / Activity ──────────────────────────────────────────────────────────

async def api_stats(request):
    return web.json_response(await get_stats())


async def api_activity(request):
    days = int(request.rel_url.query.get("days", 14))
    return web.Response(text=_j(await get_activity_stats(days)), content_type="application/json")


# ── Mode ──────────────────────────────────────────────────────────────────────

async def api_mode_get(request):
    mode = await get_setting("mode", config.MODE)
    return web.json_response({"mode": mode})


async def api_mode_set(request):
    data = await request.json()
    mode = data.get("mode", "AUTO").upper()
    if mode not in ("AUTO", "HYBRID", "OFF"):
        return web.json_response({"error": "invalid mode"}, status=400)
    await set_setting("mode", mode)
    config.MODE = mode
    return web.json_response({"ok": True, "mode": mode})


# ── Persona ───────────────────────────────────────────────────────────────────

async def api_persona_get(request):
    p = load_persona()
    for k in ("about", "character", "writing_style", "taboo"):
        if k in p and p[k]:
            p[k] = str(p[k]).strip()
    return web.Response(text=_j(p), content_type="application/json")


async def api_persona_set(request):
    data = await request.json()
    save_persona(data)
    return web.json_response({"ok": True})


# ── Delays ────────────────────────────────────────────────────────────────────

async def api_delays_get(request):
    return web.json_response({
        "min":          float(await get_setting("reply_delay_min", str(config.REPLY_DELAY_MIN))),
        "max":          float(await get_setting("reply_delay_max", str(config.REPLY_DELAY_MAX))),
        "max_per_hour": int(  await get_setting("max_per_hour",    str(config.MAX_MESSAGES_PER_HOUR))),
    })


async def api_delays_set(request):
    data = await request.json()
    dmin = float(data.get("min", config.REPLY_DELAY_MIN))
    dmax = float(data.get("max", config.REPLY_DELAY_MAX))
    mph  = int(  data.get("max_per_hour", config.MAX_MESSAGES_PER_HOUR))
    await set_setting("reply_delay_min", str(dmin))
    await set_setting("reply_delay_max", str(dmax))
    await set_setting("max_per_hour",    str(mph))
    config.REPLY_DELAY_MIN       = dmin
    config.REPLY_DELAY_MAX       = dmax
    config.MAX_MESSAGES_PER_HOUR = mph
    return web.json_response({"ok": True})


# ── Sleep schedule ────────────────────────────────────────────────────────────

async def api_sleep_get(request):
    return web.json_response({
        "enabled": (await get_setting("sleep_enabled", "false")) == "true",
        "start":   int(await get_setting("sleep_start", "23")),
        "end":     int(await get_setting("sleep_end",   "8")),
    })


async def api_sleep_set(request):
    data = await request.json()
    await set_setting("sleep_enabled", "true" if data.get("enabled") else "false")
    await set_setting("sleep_start",   str(int(data.get("start", 23))))
    await set_setting("sleep_end",     str(int(data.get("end",    8))))
    return web.json_response({"ok": True})


# ── Stickers ──────────────────────────────────────────────────────────────────

async def api_stickers_get(request):
    raw  = await get_setting("stickers", "[]")
    prob = int(await get_setting("sticker_probability", "15"))
    try:
        ids = json.loads(raw)
    except Exception:
        ids = []
    return web.json_response({"ids": ids, "probability": prob})


async def api_stickers_set(request):
    data = await request.json()
    ids  = [s.strip() for s in data.get("ids", []) if str(s).strip()]
    prob = max(0, min(100, int(data.get("probability", 15))))
    await set_setting("stickers",            json.dumps(ids))
    await set_setting("sticker_probability", str(prob))
    return web.json_response({"ok": True})


# ── Dashboard ─────────────────────────────────────────────────────────────────

async def serve_dashboard(request):
    html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    with open(html_path, encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/html")


# ── App ───────────────────────────────────────────────────────────────────────

async def start_web():
    app = web.Application()
    app.router.add_get("/",                        serve_dashboard)
    app.router.add_get("/api/chats",               api_chats)
    app.router.add_get("/api/messages/{chat_id}",  api_messages)
    app.router.add_post("/api/status",             api_status)
    app.router.add_get("/api/stats",               api_stats)
    app.router.add_get("/api/activity",            api_activity)
    app.router.add_get("/api/mode",                api_mode_get)
    app.router.add_post("/api/mode",               api_mode_set)
    app.router.add_get("/api/persona",             api_persona_get)
    app.router.add_post("/api/persona",            api_persona_set)
    app.router.add_get("/api/delays",              api_delays_get)
    app.router.add_post("/api/delays",             api_delays_set)
    app.router.add_get("/api/sleep",               api_sleep_get)
    app.router.add_post("/api/sleep",              api_sleep_set)
    app.router.add_get("/api/stickers",            api_stickers_get)
    app.router.add_post("/api/stickers",           api_stickers_set)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.WEB_PORT)
    await site.start()
    print(f"[WEB] Dashboard: http://127.0.0.1:{config.WEB_PORT}")
