import os
from aiohttp import web
import config
from db.models import (
    get_all_chats,
    get_messages_for_chat,
    set_chat_status,
    get_stats,
    get_setting,
    set_setting,
)


async def api_chats(request):
    chats = await get_all_chats()
    return web.json_response(chats, dumps=_json_dumps)


async def api_messages(request):
    chat_id = int(request.match_info["chat_id"])
    msgs = await get_messages_for_chat(chat_id)
    return web.json_response(msgs, dumps=_json_dumps)


async def api_status(request):
    data = await request.json()
    await set_chat_status(data["telegram_chat_id"], data["status"])
    return web.json_response({"ok": True})


async def api_stats(request):
    stats = await get_stats()
    return web.json_response(stats)


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


async def serve_dashboard(request):
    html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    with open(html_path, encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/html")


def _json_dumps(obj):
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)


async def start_web():
    app = web.Application()
    app.router.add_get("/", serve_dashboard)
    app.router.add_get("/api/chats", api_chats)
    app.router.add_get("/api/messages/{chat_id}", api_messages)
    app.router.add_post("/api/status", api_status)
    app.router.add_get("/api/stats", api_stats)
    app.router.add_get("/api/mode", api_mode_get)
    app.router.add_post("/api/mode", api_mode_set)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.WEB_PORT)
    await site.start()
    print(f"[WEB] Dashboard: http://127.0.0.1:{config.WEB_PORT}")
