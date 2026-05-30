#!/usr/bin/env python3
"""
GAUSS+DNA — Web Dashboard
Roda um servidor local e abre o painel no navegador.

Uso:
  pip install aiohttp
  python app.py
"""
import asyncio
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path

from aiohttp import web

bot_proc   = None
ws_clients = set()

DASHBOARD = Path(__file__).parent / "dashboard.html"


async def handle_index(request: web.Request) -> web.Response:
    html = DASHBOARD.read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html")


async def handle_start(request: web.Request) -> web.Response:
    global bot_proc

    if bot_proc and bot_proc.returncode is None:
        return web.json_response({"error": "Bot ja esta rodando"})

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "JSON invalido"}, status=400)

    token  = body.get("tg_token", "").strip()
    chatid = body.get("tg_chatid", "").strip()
    if not token:
        return web.json_response({"error": "TG_TOKEN obrigatorio"}, status=400)
    if not chatid:
        return web.json_response({"error": "TG_CHATID obrigatorio"}, status=400)

    env = os.environ.copy()
    env.update({
        "TG_TOKEN":    token,
        "TG_CHATID":   chatid,
        "CAPITAL":     str(body.get("capital",     "180")),
        "RISK_PCT":    str(body.get("risk_pct",    "0.03")),
        "TIMEFRAMES":  body.get("timeframes",  "15m"),
        "TIMEFRAME":   body.get("timeframes",  "15m").split(",")[0],
        "SIGNAL_MODE": body.get("signal_mode", "FLEX"),
        "LOOP_MODE":   "false" if body.get("test_mode") else "true",
        "DYNAMIC_SCAN":"true",
        "SCANNER_TOP": str(body.get("scanner_top", "30")),
        "TEST_MODE":   "true" if body.get("test_mode") else "false",
    })

    bot_path = Path(__file__).parent / "bot_actions.py"
    if not bot_path.exists():
        return web.json_response({"error": "bot_actions.py nao encontrado"}, status=500)

    bot_proc = await asyncio.create_subprocess_exec(
        sys.executable, str(bot_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    asyncio.create_task(_stream_logs())
    return web.json_response({"ok": True, "pid": bot_proc.pid})


async def _stream_logs():
    global bot_proc
    if not bot_proc or not bot_proc.stdout:
        return
    async for line in bot_proc.stdout:
        msg = line.decode("utf-8", errors="replace").rstrip()
        await _broadcast({"type": "log", "msg": msg})
    await _broadcast({"type": "status", "running": False})


async def handle_stop(request: web.Request) -> web.Response:
    global bot_proc
    if bot_proc and bot_proc.returncode is None:
        bot_proc.terminate()
        try:
            await asyncio.wait_for(bot_proc.wait(), timeout=6)
        except asyncio.TimeoutError:
            bot_proc.kill()
    await _broadcast({"type": "log", "msg": "Bot parado."})
    return web.json_response({"ok": True})


async def handle_status(request: web.Request) -> web.Response:
    running = bot_proc is not None and bot_proc.returncode is None
    return web.json_response({"running": running})


async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    ws_clients.add(ws)
    running = bot_proc is not None and bot_proc.returncode is None
    await ws.send_str(json.dumps({"type": "status", "running": running}))
    try:
        async for _ in ws:
            pass
    finally:
        ws_clients.discard(ws)
    return ws


async def _broadcast(data: dict):
    msg  = json.dumps(data)
    dead = set()
    for ws in ws_clients:
        try:
            await ws.send_str(msg)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)


def main():
    port = int(os.environ.get("PORT", "8080"))
    url  = f"http://localhost:{port}"

    app = web.Application()
    app.router.add_get("/",       handle_index)
    app.router.add_post("/start", handle_start)
    app.router.add_post("/stop",  handle_stop)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/ws",     handle_ws)

    print("=" * 45)
    print("  GAUSS+DNA Dashboard")
    print(f"  Abrindo: {url}")
    print("  Ctrl+C para parar")
    print("=" * 45)

    def _open():
        import time; time.sleep(1.2)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()
    web.run_app(app, host="0.0.0.0", port=port, access_log=None)


if __name__ == "__main__":
    main()
