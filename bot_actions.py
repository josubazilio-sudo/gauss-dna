"""
GAUSS+DNA ELITE — Bot GitHub Actions
Lógica identica ao Pine Script DNA INSTITUCIONAL ELITE + KALMAN
Filtro de Kalman + Score Institucional + Divergencia RSI + Volume Flow
"""

import asyncio
import os
import json
import time
import math
import logging
import aiohttp
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("GAUSS+DNA")

TG_TOKEN   = os.environ.get("TG_TOKEN", "")
TG_CHATID  = os.environ.get("TG_CHATID", "")
TIMEFRAME  = os.environ.get("TIMEFRAME", "15m")
COOLDOWN   = int(os.environ.get("COOLDOWN", "900"))
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

# ── INDICADORES ──────────────────────────────────────────────────────────────

def ema_series(arr, p):
    k = 2.0 / (p + 1)
    out = [arr[0]]
    for v in arr[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out

def sma_series(arr, p):
    out = []
    for i in range(len(arr)):
        s = arr[max(0, i-p+1):i+1]
        out.append(sum(s) / len(s))
    return out

def kalman_filter(src, length, R=0.01, Q=0.1):
    estimate = src[0]
    error_est = 1.0
    out = []
    for s in src:
        error_meas = R * length
        kalman_gain = error_est / (error_est + error_meas)
        estimate = estimate + kalman_gain * (s - estimate)
        error_est = (1 - kalman_gain) * error_est + Q / length
        out.append(estimate)
    return out

def atr_series(candles, p=14):
    trs = [candles[0]["h"] - candles[0]["l"]]
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["h"], candles[i]["l"], candles[i-1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    # RMA (Wilder)
    out = [sum(trs[:p]) / p]
    for tr in trs[p:]:
        out.append((out[-1] * (p - 1) + tr) / p)
    return [trs[0]] * p + out[1:]  # pad

def rsi_series(closes, p=14):
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[1:p+1]) / p
    al = sum(losses[1:p+1]) / p
    rsi_out = [50.0] * (p + 1)
    for i in range(p + 1, len(closes)):
        ag = (ag * (p - 1) + gains[i]) / p
        al = (al * (p - 1) + losses[i]) / p
        rs = ag / al if al > 0 else 100
        rsi_out.append(100 - 100 / (1 + rs))
    return rsi_out

def dmi_adx(candles, p=14, smooth=14):
    pdm_list, mdm_list, tr_list = [], [], []
    for i in range(1, len(candles)):
        h, l = candles[i]["h"], candles[i]["l"]
        ph, pl, pc = candles[i-1]["h"], candles[i-1]["l"], candles[i-1]["c"]
        up, dn = h - ph, pl - l
        pdm_list.append(up if up > dn and up > 0 else 0)
        mdm_list.append(dn if dn > up and dn > 0 else 0)
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))

    def rma(arr, n):
        r = [sum(arr[:n]) / n]
        for v in arr[n:]:
            r.append((r[-1] * (n - 1) + v) / n)
        return [arr[0]] * n + r[1:]

    rtr  = rma(tr_list, p)
    rpdm = rma(pdm_list, p)
    rmdm = rma(mdm_list, p)

    pdi_list, mdi_list, dx_list = [], [], []
    for i in range(len(rtr)):
        t = rtr[i] if rtr[i] > 0 else 1e-10
        pdi = rpdm[i] / t * 100
        mdi = rmdm[i] / t * 100
        pdi_list.append(pdi)
        mdi_list.append(mdi)
        sm = pdi + mdi
        dx_list.append(abs(pdi - mdi) / sm * 100 if sm > 0 else 0)

    adx_list = rma(dx_list, smooth)
    return pdi_list, mdi_list, adx_list

def fmt_price(price):
    if price < 0.0001: return f"{price:.7f}"
    if price < 0.01:   return f"{price:.5f}"
    if price < 1:      return f"{price:.4f}"
    if price < 100:    return f"{price:.3f}"
    return f"{price:,.2f}"

# ── ANÁLISE COMPLETA ──────────────────────────────────────────────────────────

def analyze(sym, candles):
    n = len(candles)
    if n < 220:
        return None

    closes  = [c["c"] for c in candles]
    highs   = [c["h"] for c in candles]
    lows    = [c["l"] for c in candles]
    opens   = [c["o"] for c in candles]
    volumes = [c["v"] for c in candles]

    # EMAs
    e10  = ema_series(closes, 10)
    e21  = ema_series(closes, 21)
    e50  = ema_series(closes, 50)
    e200 = ema_series(closes, 200)

    # ATR
    atr_arr = atr_series(candles, 14)

    # Kalman
    k_short = kalman_filter(closes, 50)
    k_long  = kalman_filter(closes, 150)

    # RSI + EMA do RSI
    rsi_arr = rsi_series(closes, 14)
    rsi_ema = ema_series(rsi_arr, 5)

    # MACD
    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    macd_line   = [a - b for a, b in zip(ema12, ema26)]
    signal_line = ema_series(macd_line, 9)
    hist_line   = [m - s for m, s in zip(macd_line, signal_line)]

    # ADX / DMI
    pdi_arr, mdi_arr, adx_arr = dmi_adx(candles, 14, 14)

    # Volume Flow (EMA do fluxo bruto)
    flow_raw = []
    for i in range(n):
        spread = max(highs[i] - lows[i], 1e-10)
        flow_raw.append(((closes[i] - opens[i]) / spread) * volumes[i])
    flow_ema = ema_series(flow_raw, 13)
    flow_abs = [abs(f) for f in flow_ema]
    flow_sma = sma_series(flow_abs, 20)

    # Volume médio
    vol_sma = sma_series(volumes, 20)

    # ── Valores atuais (última barra) ──
    i = n - 1
    price   = closes[i]
    atr     = max(atr_arr[i], 1e-10)
    kalman_s = k_short[i]
    kalman_l = k_long[i]
    rsi     = rsi_ema[i]
    macd    = macd_line[i]
    sig     = signal_line[i]
    hist    = hist_line[i]
    hist_p  = hist_line[i-1]
    hist_pp = hist_line[i-2]
    pdi     = pdi_arr[i] if i < len(pdi_arr) else 0
    mdi     = mdi_arr[i] if i < len(mdi_arr) else 0
    adx     = adx_arr[i] if i < len(adx_arr) else 0
    adx_p   = adx_arr[i-1] if i-1 < len(adx_arr) else adx
    flow    = flow_ema[i]
    flow_s  = flow_sma[i]
    vol     = volumes[i]
    vol_ma  = vol_sma[i]

    # ── Condições ──
    # Kalman
    kalman_up   = kalman_s > kalman_l
    kalman_down = kalman_s < kalman_l

    # Tendência completa
    trend_bull = (price > e200[i] and e10[i] > e21[i] and
                  e21[i] > e50[i] and e50[i] > e200[i])
    trend_bear = (price < e200[i] and e10[i] < e21[i] and
                  e21[i] < e50[i] and e50[i] < e200[i])

    align_bull = price > e10[i] and price > e21[i] and price > e50[i]
    align_bear = price < e10[i] and price < e21[i] and price < e50[i]

    e200_rising  = e200[i] > e200[i-3]
    e200_falling = e200[i] < e200[i-3]

    trend_strength = abs(e21[i] - e50[i]) / atr if atr > 0 else 0
    strong_trend   = trend_strength > 0.6

    # MACD Heikin Ashi
    ha_close = (macd + sig + hist) / 3
    ha_open  = (macd_line[i-1] + signal_line[i-1]) / 2
    ha_bull  = ha_close > ha_open
    ha_bull2 = ha_bull and ((macd_line[i-1] + signal_line[i-1]) / 2 < (macd_line[i-1] + signal_line[i-1] + hist_line[i-1]) / 3)
    ha_bear  = ha_close < ha_open

    macd_bull = (macd > sig and hist > hist_p and hist > 0 and ha_bull)
    macd_bear = (macd < sig and hist < hist_p and hist < 0 and ha_bear)

    # Exaustão
    sell_exhaust = (hist < hist_p < hist_pp and
                    price < e21[i] and price < e50[i] and price < e200[i])
    buy_exhaust  = (hist > hist_p > hist_pp and
                    price > e21[i] and price > e50[i] and price > e200[i])

    # ADX
    adx_long_ok  = adx > 22 and pdi > mdi and adx >= adx_p * 0.95
    adx_short_ok = adx > 28 and mdi > pdi and adx >= adx_p * 0.95

    # Volume
    vol_strong = vol > vol_ma * 1.1
    vol_weak   = vol < vol_ma * 0.85

    # Flow
    flow_bull   = flow > 0
    flow_bear   = flow < 0
    flow_strong = abs(flow) > flow_s * 1.2

    # RSI zonas
    rsi_bull = rsi > 50 and rsi < 70  # momentum bull
    rsi_bear = rsi < 50 and rsi > 30  # momentum bear

    # Distância da EMA50
    dist_long  = (price - e50[i]) / atr if atr > 0 else 0
    dist_short = (e50[i] - price) / atr if atr > 0 else 0
    not_ext_long  = dist_long  < 2.5
    not_ext_short = dist_short < 2.5

    # Impulso
    bull_impulse = (price > highs[i-1] and price > opens[i] and
                    (price - opens[i]) > atr * 0.2)
    bear_impulse = (price < lows[i-1] and price < opens[i] and
                    (opens[i] - price) > atr * 0.2)

    # Sweep de liquidez
    liq_sweep_long  = (lows[i] < lows[i-1] and price > lows[i-1] and price > opens[i])
    liq_sweep_short = (highs[i] > highs[i-1] and price < highs[i-1] and price < opens[i])

    # Absorção
    candle_range = highs[i] - lows[i]
    lower_wick   = min(opens[i], price) - lows[i]
    upper_wick   = highs[i] - max(opens[i], price)
    bull_absorb  = (candle_range > 0 and
                    lower_wick > candle_range * 0.45 and
                    price > (lows[i] + candle_range * 0.6) and
                    vol > vol_ma)
    bear_absorb  = (candle_range > 0 and
                    upper_wick > candle_range * 0.45 and
                    price < (highs[i] - candle_range * 0.6) and
                    vol > vol_ma)

    # ── SCORE INSTITUCIONAL ──
    score = (
        (35 if trend_bull else -35 if trend_bear else 0) +
        (20 if flow_bull  else -20 if flow_bear  else 0) +
        (10 if flow_strong else 0) +
        (20 if macd_bull  else -20 if macd_bear  else 0) +
        (20 if adx > 30 else 10 if adx > 22 else 0) +
        (10 if vol_strong else -5) +
        (10 if rsi_bull   else -10 if rsi_bear   else 0) +
        (10 if e200_rising else -10 if e200_falling else 0) +
        (10 if kalman_up  else -10 if kalman_down else 0)
    )

    # ── SINAIS ──
    long_signal = (
        strong_trend and trend_bull and align_bull and
        e200_rising  and macd_bull  and flow_bull  and
        flow_strong  and adx_long_ok and rsi_bull  and
        vol_strong   and not_ext_long and kalman_up and
        (bull_impulse or liq_sweep_long) and score > 50
    )

    short_signal = (
        strong_trend and trend_bear and align_bear and
        e200_falling and macd_bear  and flow_bear  and
        flow_strong  and adx_short_ok and rsi_bear and
        vol_strong   and not_ext_short and kalman_down and
        (bear_impulse or liq_sweep_short) and score < -50
    )

    # Reversão precoce (early)
    early_long = (
        adx_long_ok and vol_strong and sell_exhaust and
        liq_sweep_long and bull_absorb and
        flow_bull and trend_bull and e200_rising and kalman_up
    )

    early_short = (
        adx_short_ok and vol_strong and buy_exhaust and
        liq_sweep_short and bear_absorb and
        flow_bear and trend_bear and e200_falling and kalman_down
    )

    sig_type = None
    if long_signal or early_long:
        sig_type = "LONG"
    elif short_signal or early_short:
        sig_type = "SHORT"

    return {
        "price": price, "score": score, "atr": atr,
        "rsi": rsi, "adx": adx, "pdi": pdi, "mdi": mdi,
        "kalman_up": kalman_up,
        "trend": "BULL" if trend_bull else "BEAR" if trend_bear else "NEUTRO",
        "macd": "BULL" if macd_bull else "BEAR" if macd_bear else "—",
        "sig": sig_type,
    }

# ── TELEGRAM ─────────────────────────────────────────────────────────────────

async def send_telegram(session, sym, label, short, sig_type, price, atr, score):
    is_long = sig_type == "LONG"
    stop    = price - atr * 1.5 if is_long else price + atr * 1.5
    risk    = abs(price - stop)
    tp1     = price + risk * 1.8 if is_long else price - risk * 1.8
    tp_fin  = price + risk * 4.0 if is_long else price - risk * 4.0

    def d(v): return f"{v:.6f}" if v < 0.01 else f"{v:.4f}" if v < 1 else f"{v:.2f}"
    def esc(v):
        s = str(v)
        for ch in r"_*[]()~`>#+=|{}.!\-": s = s.replace(ch, f"\\{ch}")
        return s

    now = datetime.now().strftime("%H:%M — %d/%m/%Y")
    text = (
        f"🚨 *DNA ELITE KALMAN — {sig_type}*\n\n"
        f"{'🟢' if is_long else '🔴'} *{esc(label)}*\n"
        f"💰 Entrada: `${esc(fmt_price(price))}`\n"
        f"🛑 Stop: `${esc(d(stop))}`\n"
        f"🎯 TP1 \\(1\\.8R\\): `${esc(d(tp1))}`\n"
        f"🏆 Final \\(4R\\): `${esc(d(tp_fin))}`\n"
        f"📊 Score: *{esc(score)}/145*\n"
        f"⏰ {esc(now)}"
    )
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with session.post(url, json={"chat_id": TG_CHATID, "text": text, "parse_mode": "MarkdownV2"},
                                timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            if data.get("ok"): log.info(f"✅ Telegram → {sig_type} {short} Score:{score}")
            else: log.warning(f"❌ Telegram: {data.get('description')}")
    except Exception as e:
        log.error(f"Telegram erro: {e}")

# ── BINANCE ───────────────────────────────────────────────────────────────────

async def fetch_candles(session, sym, tf, limit=250):
    url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={tf}&limit={limit}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            if not isinstance(data, list) or len(data) < 220: return None
            return [{"o": float(k[1]), "h": float(k[2]),
                     "l": float(k[3]), "c": float(k[4]), "v": float(k[5])} for k in data]
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

# ── MAIN ──────────────────────────────────────────────────────────────────────

async def main():
    if not TG_TOKEN or not TG_CHATID:
        log.error("❌ Configure TG_TOKEN e TG_CHATID!"); return

    last_sig = load_state()
    now = time.time()
    sent = 0

    log.info(f"🚀 DNA ELITE KALMAN | TF: {TIMEFRAME} | {len(COINS)} moedas")

    async with aiohttp.ClientSession() as session:
        for sym, label, short in COINS:
            candles = await fetch_candles(session, sym, TIMEFRAME)
            if not candles: await asyncio.sleep(0.4); continue

            result = analyze(sym, candles)
            if not result: await asyncio.sleep(0.4); continue

            log.info(
                f"{short:7s} | Score {result['score']:+4d} | "
                f"RSI {result['rsi']:5.1f} | ADX {result['adx']:5.1f} | "
                f"Kalman {'UP' if result['kalman_up'] else 'DN':2s} | "
                f"Trend {result['trend']:6s} | {result['sig'] or '—'}"
            )

            if result["sig"]:
                if now - last_sig.get(sym, 0) >= COOLDOWN:
                    last_sig[sym] = now
                    sent += 1
                    await send_telegram(session, sym, label, short,
                                        result["sig"], result["price"],
                                        result["atr"], result["score"])
                else:
                    mins = int((COOLDOWN - (now - last_sig.get(sym, 0))) / 60)
                    log.info(f"  ⏳ {short} cooldown {mins}min")

            await asyncio.sleep(0.5)

    save_state(last_sig)
    log.info(f"✅ Concluído. Sinais: {sent}")

if __name__ == "__main__":
    asyncio.run(main())
