"""
GAUSS+DNA v3 — Bot para GitHub Actions
Critérios suavizados para detectar mais sinais em qualquer mercado.
"""

import asyncio
import os
import json
import time
import logging
import aiohttp
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("GAUSS+DNA")

TG_TOKEN  = os.environ.get("TG_TOKEN", "")
TG_CHATID = os.environ.get("TG_CHATID", "")
TIMEFRAME = os.environ.get("TIMEFRAME", "15m")
COOLDOWN  = int(os.environ.get("COOLDOWN", "900"))
STATE_FILE = Path("last_signals.json")

COINS = [
    ("BTCUSDT",    "BTC/USDT",    "BTC"),
    ("ETHUSDT",    "ETH/USDT",    "ETH"),
    ("SOLUSDT",    "SOL/USDT",    "SOL"),
    ("SUIUSDT",    "SUI/USDT",    "SUI"),
    ("NEARUSDT",   "NEAR/USDT",   "NEAR"),
    ("AVAXUSDT",   "AVAX/USDT",   "AVAX"),
    ("LINKUSDT",   "LINK/USDT",   "LINK"),
    ("XRPUSDT",    "XRP/USDT",    "XRP"),
    ("DOGEUSDT",   "DOGE/USDT",   "DOGE"),
    ("PEPEUSDT",   "PEPE/USDT",   "PEPE"),
    ("BONKUSDT",   "BONK/USDT",   "BONK"),
    ("JUPUSDT",    "JUP/USDT",    "JUP"),
    ("SEIUSDT",    "SEI/USDT",    "SEI"),
    ("WIFUSDT",    "WIF/USDT",    "WIF"),
    ("TIAUSDT",    "TIA/USDT",    "TIA"),
    ("STRKUSDT",   "STRK/USDT",   "STRK"),
    ("ARBUSDT",    "ARB/USDT",    "ARB"),
    ("OPUSDT",     "OP/USDT",     "OP"),
    ("INJUSDT",    "INJ/USDT",    "INJ"),
    ("RENDERUSDT", "RENDER/USDT", "RENDER"),
]

def ema_arr(arr, p):
    k = 2 / (p + 1)
    out = [arr[0]]
    for v in arr[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out

def ema(arr, p):
    return ema_arr(arr, p)[-1]

def rsi_calc(closes, p=14):
    g = l = 0.0
    for i in range(1, p + 1):
        d = closes[i] - closes[i - 1]
        if d > 0: g += d
        else: l -= d
    ag, al = g / p, l / p
    for i in range(p + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (p - 1) + (d if d > 0 else 0)) / p
        al = (al * (p - 1) + (-d if d < 0 else 0)) / p
    return 100.0 if al == 0 else 100 - (100 / (1 + ag / al))

def atr_calc(candles, p=14):
    trs = [max(c["h"]-c["l"], abs(c["h"]-candles[i]["c"]), abs(c["l"]-candles[i]["c"])) for i, c in enumerate(candles[1:])]
    return sum(trs[-p:]) / p

def macd_calc(closes, f=12, s=26, sig=9):
    ea = ema_arr(closes, f); eb = ema_arr(closes, s)
    ml = [a - b for a, b in zip(ea, eb)]
    sl = ema_arr(ml, sig)
    hist = [m - s for m, s in zip(ml, sl)]
    return ml[-1], sl[-1], hist[-1], hist[-2]

def adx_calc(candles, p=14):
    pdm = mdm = tr = 0.0
    limit = min(p, len(candles) - 1)
    for i in range(1, limit + 1):
        h, l = candles[i]["h"], candles[i]["l"]
        ph, pl, pc = candles[i-1]["h"], candles[i-1]["l"], candles[i-1]["c"]
        up, dn = h - ph, pl - l
        if up > dn and up > 0: pdm += up
        if dn > up and dn > 0: mdm += dn
        tr += max(h - l, abs(h - pc), abs(l - pc))
    if tr == 0: return 20.0
    pdi = (pdm / tr) * 100; mdi = (mdm / tr) * 100
    return abs(pdi - mdi) / (pdi + mdi or 1) * 100

def fmt_price(price, sym):
    if price < 0.0001: return f"{price:.7f}"
    if price < 0.01: return f"{price:.5f}"
    if price < 1: return f"{price:.4f}"
    if price < 100: return f"{price:.3f}"
    return f"{price:,.2f}"

def analyze(sym, candles):
    if len(candles) < 50: return None
    closes = [c["c"] for c in candles]
    vols = [c["v"] for c in candles]
    n = len(closes)
    price = closes[-1]

    e10 = ema(closes[-10:], 10)
    e21 = ema(closes[-21:], 21)
    e50 = ema(closes[-50:], 50)
    e200 = ema(closes, 200) if n >= 200 else ema(closes, n)

    # Critérios suavizados — não exige alinhamento perfeito com EMA200
    t_bull = e10 > e21 and e21 > e50  # removido: price > e200
    t_bear = e10 < e21 and e21 < e50  # removido: price < e200

    ml, sl, hist, hist_p = macd_calc(closes)
    m_bull = ml > sl and hist > hist_p
    m_bear = ml < sl and hist < hist_p

    rsi_v = rsi_calc(closes[-30:])
    rsi_bull = 40 < rsi_v < 75  # faixa mais ampla
    rsi_bear = 25 < rsi_v < 60

    avg_vol = sum(vols[-20:]) / 20
    v_strong = vols[-1] > avg_vol * 0.8  # 80% da média (antes era 100%)

    adx_v = adx_calc(candles[-20:])
    adx_ok = adx_v > 15  # antes era 18

    last_c = candles[-1]
    sp = max(last_c["h"] - last_c["l"], 0.0001)
    flow = ((last_c["c"] - last_c["o"]) / sp) * last_c["v"]
    f_bull = flow > 0; f_bear = flow < 0

    score = (
        (30 if t_bull else -30 if t_bear else 0) +
        (25 if m_bull else -25 if m_bear else 0) +
        (15 if rsi_bull else -15 if rsi_bear else 0) +
        (10 if v_strong else -10) +
        (15 if adx_ok else -15) +
        (20 if f_bull else -20 if f_bear else 0)
    )
    score = max(-115, min(115, score))
    atr_v = atr_calc(candles[-20:])

    # Sinal: score > 20 (antes era 30) e MACD + tendência alinhados
    sig = None
    if score > 20 and t_bull and m_bull and adx_ok:
        sig = "LONG"
    elif score < -20 and t_bear and m_bear and adx_ok:
        sig = "SHORT"

    return {"price": price, "score": score, "atr": atr_v, "rsi": rsi_v, "adx": adx_v,
            "trend": "BULL" if t_bull else "BEAR" if t_bear else "NEUTRO", "sig": sig}

async def send_telegram(session, sym, label, short, sig_type, price, atr, score):
    is_long = sig_type == "LONG"
    a = atr or price * 0.015
    stop = price - a * 1.5 if is_long else price + a * 1.5
    risk = abs(price - stop)
    tp1 = price + risk * 1.5 if is_long else price - risk * 1.5
    final = price + risk * 5 if is_long else price - risk * 5

    def d(v): return f"{v:.5f}" if v < 1 else f"{v:.2f}"
    def esc(v):
        s = str(v)
        for ch in r"_*[]()~`>#+=|{}.!\-": s = s.replace(ch, f"\\{ch}")
        return s

    now = datetime.now().strftime("%H:%M — %d/%m/%Y")
    text = (
        f"🚨 *GAUSS\\+DNA v3 — SINAL {sig_type}*\n\n"
        f"{'🟢' if is_long else '🔴'} Par: *{esc(label)}*\n"
        f"💰 Entrada: `${esc(fmt_price(price, sym))}`\n"
        f"🛑 Stop Loss: `${esc(d(stop))}`\n"
        f"🎯 TP1 \\(1\\.5R\\): `${esc(d(tp1))}`\n"
        f"🏆 Final \\(5R\\): `${esc(d(final))}`\n"
        f"📊 Score: *{esc(score)}/115*\n"
        f"⏰ {esc(now)}"
    )
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with session.post(url, json={"chat_id": TG_CHATID, "text": text, "parse_mode": "MarkdownV2"}, timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            if data.get("ok"): log.info(f"✅ Telegram → {sig_type} {short} | Score {score}")
            else: log.warning(f"❌ Telegram: {data.get('description')}")
    except Exception as e:
        log.error(f"Telegram erro: {e}")

async def fetch_candles(session, sym, tf, limit=210):
    url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={tf}&limit={limit}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            if not isinstance(data, list) or len(data) < 50: return None
            return [{"o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])} for k in data]
    except Exception as e:
        log.debug(f"Fetch {sym}: {e}"); return None

def load_state():
    try:
        if STATE_FILE.exists(): return json.loads(STATE_FILE.read_text())
    except: pass
    return {}

def save_state(state):
    try: STATE_FILE.write_text(json.dumps(state))
    except: pass

async def main():
    if not TG_TOKEN or not TG_CHATID:
        log.error("❌ Configure TG_TOKEN e TG_CHATID!"); return

    last_sig = load_state()
    now = time.time()
    signals_sent = 0

    log.info(f"🚀 GAUSS+DNA v3 | TF: {TIMEFRAME} | {len(COINS)} moedas")

    async with aiohttp.ClientSession() as session:
        for sym, label, short in COINS:
            candles = await fetch_candles(session, sym, TIMEFRAME)
            if not candles: await asyncio.sleep(0.3); continue

            result = analyze(sym, candles)
            if not result: await asyncio.sleep(0.3); continue

            sig = result["sig"]
            log.info(f"{short:7s} | Score {result['score']:+4d} | RSI {result['rsi']:5.1f} | Trend {result['trend']:6s} | {sig or '—'}")

            if sig:
                last_t = last_sig.get(sym, 0)
                if now - last_t >= COOLDOWN:
                    last_sig[sym] = now
                    signals_sent += 1
                    await send_telegram(session, sym, label, short, sig, result["price"], result["atr"], result["score"])
                else:
                    mins = int((COOLDOWN - (now - last_t)) / 60)
                    log.info(f"  ⏳ {short} cooldown ({mins}min)")

            await asyncio.sleep(0.4)

    save_state(last_sig)
    log.info(f"✅ Ciclo concluído. Sinais enviados: {signals_sent}")

if __name__ == "__main__":
    asyncio.run(main())
    save_state(last_sig)
    log.info(f"✅ Ciclo concluído. Sinais enviados: {signals_sent}")


if __name__ == "__main__":
    asyncio.run(main())
