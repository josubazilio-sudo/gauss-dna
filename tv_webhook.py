#!/usr/bin/env python3
"""
TradingView → Telegram Webhook
────────────────────────────────
Recebe POST /alert do TradingView, busca candles no MEXC,
roda analyze() do bot_actions.py e envia a mensagem completa no Telegram.

Variáveis de ambiente:
  TV_SECRET   — token secreto (configure igual no alerta do TV)
  TG_TOKEN    — token do bot Telegram
  TG_CHATID   — ID do chat/canal
  PORT        — porta HTTP (padrão 8080)
  CAPITAL     — capital base em USD (padrão 180)
  RISK_PCT    — risco por trade (padrão 0.03)

Configurar alerta no TradingView:
  Webhook URL : https://<seu-servidor>/alert
  Mensagem    : {"secret":"{{TV_SECRET}}","action":"LONG","ticker":"{{ticker}}","tf":"{{interval}}"}
  (Para SHORT, crie um alerta separado com "action":"SHORT")
"""
import asyncio, os, logging
from aiohttp import web
import aiohttp

from bot_actions import analyze, fetch_candles, send_telegram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("TV_WEBHOOK")

TV_SECRET = os.environ.get("TV_SECRET", "")
PORT      = int(os.environ.get("PORT", "8080"))


def tv_to_mexc(ticker: str) -> str:
    """BINANCE:BTCUSDT → BTCUSDT   |   BTC → BTCUSDT"""
    if ":" in ticker:
        ticker = ticker.split(":", 1)[1]
    ticker = ticker.upper().replace("/", "").replace("-", "")
    if not ticker.endswith("USDT"):
        ticker += "USDT"
    return ticker


async def handle_alert(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "JSON inválido"}, status=400)

    # ── Validação do secret ───────────────────────────────────────────────────
    if TV_SECRET and body.get("secret") != TV_SECRET:
        log.warning("Alert rejeitado: secret inválido (IP: %s)", request.remote)
        return web.json_response({"error": "unauthorized"}, status=401)

    action = body.get("action", "").upper()
    ticker = body.get("ticker", "")
    tf     = body.get("tf", "15m")

    if action not in ("LONG", "SHORT"):
        return web.json_response({"error": "action deve ser LONG ou SHORT"}, status=400)
    if not ticker:
        return web.json_response({"error": "ticker obrigatório"}, status=400)

    sym   = tv_to_mexc(ticker)
    base  = sym[:-4]          # remove USDT
    label = f"{base}/USDT"

    log.info("📡 Alert: %s %s [%s]", action, sym, tf)

    async with aiohttp.ClientSession() as session:
        candles = await fetch_candles(session, sym, tf)
        if not candles:
            log.warning("Sem dados para %s", sym)
            return web.json_response({"error": f"sem candles para {sym}"}, status=503)

        result = analyze(sym, candles)
        if not result:
            log.warning("Análise falhou para %s", sym)
            return web.json_response({"error": "análise falhou"}, status=500)

        # Direção do bot confirma TV? Loga discrepância mas envia assim mesmo.
        bot_sig = result.get("sig")
        if bot_sig and bot_sig != action:
            log.warning("⚠️  TV=%s mas bot=%s para %s — enviando alerta TV", action, bot_sig, sym)

        grade      = result.get("signal_grade", "B")
        sig_source = f"TV GAUSS FLEX"

        await send_telegram(
            session, sym, label, base, action,
            result["price"], result["atr"], result["score"],
            result["rsi"], result["adx"], result["trend"],
            result["kalman_up"], result["swing_low"], result["swing_high"],
            sig_source, tf, grade,
        )

    log.info("✅ Mensagem enviada: %s %s Grade:%s Score:%+d", action, sym, grade, result["score"])
    return web.json_response({"ok": True, "sym": sym, "action": action, "grade": grade})


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "version": "tv_webhook/1.0"})


def main():
    app = web.Application()
    app.router.add_post("/alert",  handle_alert)
    app.router.add_get("/health",  handle_health)

    log.info("🚀 TV Webhook na porta %d", PORT)
    if TV_SECRET:
        log.info("   Secret: configurado ✓")
    else:
        log.warning("   ⚠️  TV_SECRET não definido — qualquer um pode disparar alertas!")

    web.run_app(app, host="0.0.0.0", port=PORT, access_log=None)


if __name__ == "__main__":
    main()
