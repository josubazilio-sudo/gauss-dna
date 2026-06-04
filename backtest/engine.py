"""
GAUSS+DNA Backtest Engine
Replica exata da estratégia FLEX do bot_actions.py
"""
import asyncio, aiohttp, math, csv, json, os, time as _time
from datetime import datetime, timedelta
from pathlib import Path

BINANCE_BASE = "https://api.binance.com"
BYBIT_BASE   = "https://api.bybit.com"
RESULTS_DIR  = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

BYBIT_INTERVAL = {
    "1m":"1","3m":"3","5m":"5","15m":"15","30m":"30",
    "1h":"60","2h":"120","4h":"240","6h":"360","12h":"720",
    "1d":"D","1w":"W",
}
INTERVAL_MINUTES = {
    "1m":1,"5m":5,"15m":15,"30m":30,"1h":60,
    "2h":120,"4h":240,"6h":360,"12h":720,"1d":1440,
}

# ── INDICADORES (cópia fiel do bot_actions.py) ────────────────────────────────

def ema_series(arr, p):
    k = 2.0 / (p + 1); out = [arr[0]]
    for v in arr[1:]: out.append(v * k + out[-1] * (1 - k))
    return out

def rma_series(arr, p):
    out = [sum(arr[:p]) / p]
    for v in arr[p:]: out.append((out[-1] * (p - 1) + v) / p)
    return out

def alma_series(src, length=50, offset=0.85, sigma=6):
    n = len(src)
    m = math.floor(offset * (length - 1))
    s = length / sigma
    w = [math.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(length)]
    w_sum = sum(w)
    out = [float('nan')] * (length - 1)
    for i in range(length - 1, n):
        val = sum(w[j] * src[i - length + 1 + j] for j in range(length)) / w_sum
        out.append(val)
    return out

def kalman_filter(src, length, R=0.01, Q=0.1):
    est = src[0]; err = 1.0; out = []
    for s in src:
        em = R * length; gain = err / (err + em)
        est = est + gain * (s - est); err = (1 - gain) * err + Q / length
        out.append(est)
    return out

def atr_series(candles, p=14):
    trs = [candles[0]["h"] - candles[0]["l"]]
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["h"], candles[i]["l"], candles[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    rma = rma_series(trs, p)
    return [trs[0]] * p + rma[1:]

def rsi_calc(closes, p=14):
    gains = [0.0]; losses = [0.0]
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains[1:p + 1]) / p; al = sum(losses[1:p + 1]) / p
    for i in range(p + 1, len(closes)):
        ag = (ag * (p - 1) + gains[i]) / p; al = (al * (p - 1) + losses[i]) / p
    return 100.0 if al == 0 else 100 - (100 / (1 + ag / al))

def macd_calc(closes, f=12, s=26, sig=9):
    ea = ema_series(closes, f); eb = ema_series(closes, s)
    ml = [a - b for a, b in zip(ea, eb)]
    sl = ema_series(ml, sig); hist = [m - s for m, s in zip(ml, sl)]
    return ml[-1], sl[-1], hist[-1], hist[-2] if len(hist) > 1 else hist[-1], hist[-3] if len(hist) > 2 else hist[-1]

def dmi_adx(candles, p=14, smooth=14):
    pdm, mdm, tr = [], [], []
    for i in range(1, len(candles)):
        h, l = candles[i]["h"], candles[i]["l"]
        ph, pl, pc = candles[i - 1]["h"], candles[i - 1]["l"], candles[i - 1]["c"]
        up, dn = h - ph, pl - l
        pdm.append(up if up > dn and up > 0 else 0)
        mdm.append(dn if dn > up and dn > 0 else 0)
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    rtr = rma_series(tr, p); rpdm = rma_series(pdm, p); rmdm = rma_series(mdm, p)
    dx = []
    for i in range(len(rtr)):
        t = rtr[i] or 1e-10
        pdi = (rpdm[i] / t) * 100; mdi = (rmdm[i] / t) * 100
        dx.append(abs(pdi - mdi) / (pdi + mdi or 1) * 100)
    adx_arr = rma_series(dx, smooth)
    idx = len(adx_arr) - 1
    t = rtr[idx] or 1e-10
    pdi = (rpdm[idx] / t) * 100; mdi = (rmdm[idx] / t) * 100
    return pdi, mdi, adx_arr[idx], adx_arr[idx - 1] if idx > 0 else adx_arr[idx]

def ha_series(candles):
    ha = []
    for i, c in enumerate(candles):
        hc = (c["o"] + c["h"] + c["l"] + c["c"]) / 4
        ho = (c["o"] + c["c"]) / 2 if i == 0 else (ha[-1]["o"] + ha[-1]["c"]) / 2
        ha.append({"o": ho, "h": max(c["h"], ho, hc), "l": min(c["l"], ho, hc), "c": hc})
    return ha

def bb_calc(closes, p=20, mult=2.0):
    def _bw(data):
        b = sum(data) / p; s = math.sqrt(sum((c - b) ** 2 for c in data) / p)
        return (2 * mult * s) / (b or 1e-10), b + mult * s, b - mult * s, b
    bw, upper, lower, basis = _bw(closes[-p:])
    bw_prev, _, _, _ = _bw(closes[-(p + 1):-1]) if len(closes) >= p + 1 else (bw, 0, 0, 0)
    return upper, lower, basis, bw, bw_prev

def obv_calc(closes, vols):
    obv = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]: obv.append(obv[-1] + vols[i])
        elif closes[i] < closes[i - 1]: obv.append(obv[-1] - vols[i])
        else: obv.append(obv[-1])
    return obv

def vwap_calc(candles, period=20):
    sl = candles[-period:]
    vp = sum((c["h"] + c["l"] + c["c"]) / 3 * c["v"] for c in sl)
    tv = sum(c["v"] for c in sl)
    return vp / tv if tv > 0 else sl[-1]["c"]

# ── ANÁLISE FLEX (idêntica ao bot) ────────────────────────────────────────────

def analyze_flex(candles):
    """Retorna dict com sinal FLEX ou None."""
    n = len(candles)
    if n < 60: return None

    ha_raw = ha_series(candles)
    closes = [c["c"] for c in ha_raw]
    highs  = [c["h"] for c in ha_raw]
    lows   = [c["l"] for c in ha_raw]
    opens  = [c["o"] for c in ha_raw]
    vols   = [c["v"] for c in candles]
    price  = candles[-1]["c"]

    e10_arr = ema_series(closes, 10); e10 = e10_arr[-1]; e10_p = e10_arr[-2]
    e21_arr = ema_series(closes, 21); e21 = e21_arr[-1]; e21_p = e21_arr[-2]
    e50_arr = ema_series(closes, 50); e50 = e50_arr[-1]; e50_p = e50_arr[-2]
    e200a   = ema_series(closes, 200); e200 = e200a[-1]; e200p = e200a[-4] if n > 4 else e200
    price_p = closes[-2]

    atr_arr = atr_series(candles, 14); atr = max(atr_arr[-1], 1e-10)

    ks = kalman_filter(closes, 50); kl = kalman_filter(closes, 150)
    kalman_up   = ks[-1] > kl[-1]; kalman_down = ks[-1] < kl[-1]
    kalman_spread   = ks[-1] - kl[-1]; kalman_spread_p = ks[-2] - kl[-2]
    kalman_accel_up   = kalman_spread > kalman_spread_p > 0
    kalman_accel_down = kalman_spread < kalman_spread_p < 0
    k_short_rising  = ks[-1] > ks[-2]
    k_short_falling = ks[-1] < ks[-2]

    ml, sl_v, hist, hist_p, hist_pp = macd_calc(closes)
    macd_bull  = ml > sl_v and hist > hist_p and hist > 0
    macd_bear  = ml < sl_v and hist < hist_p and hist < 0
    macd_bull3 = macd_bull and hist_p > hist_pp
    macd_bear3 = macd_bear and hist_p < hist_pp
    macd_recovering = hist > hist_p
    macd_exhausting = hist < hist_p
    macd_bull_r = ml > sl_v and hist > hist_p
    macd_bear_r = ml < sl_v and hist < hist_p

    ha_body_ok = abs(closes[-1] - opens[-1]) > atr * 0.2
    ha_bull  = closes[-1] > opens[-1] and closes[-2] > opens[-2] and ha_body_ok
    ha_bear  = closes[-1] < opens[-1] and closes[-2] < opens[-2] and ha_body_ok
    ha_bull3 = ha_bull and closes[-3] > opens[-3]
    ha_bear3 = ha_bear and closes[-3] < opens[-3]

    rsi      = rsi_calc(closes[-50:])
    rsi_prev = rsi_calc(closes[-53:-3]) if n >= 53 else rsi
    rsi_rising  = rsi > rsi_prev; rsi_falling = rsi < rsi_prev
    rsi_bull = 50 < rsi < 65; rsi_bear = 35 < rsi < 50
    rsi_bull_elite = 48 < rsi < 65 and rsi_rising
    rsi_bear_elite = 35 < rsi < 52 and rsi_falling

    pdi, mdi, adx, adx_p = dmi_adx(candles[-60:])
    adx_long_ok  = adx > 22 and pdi > mdi and adx > adx_p
    adx_short_ok = adx > 22 and mdi > pdi and adx > adx_p

    vol_ma   = sum(vols[-20:]) / 20
    v_strong = vols[-1] > vol_ma * 1.1
    v_strong2 = v_strong and vols[-2] > vol_ma * 0.9
    vol_avg   = v_strong and vols[-2] > vol_ma * 0.9

    flow_raw = [((c["c"] - c["o"]) / max(c["h"] - c["l"], 1e-10)) * c["v"] for c in candles]
    flow_ema  = ema_series(flow_raw, 13); flow = flow_ema[-1]
    flow_sma  = sum(abs(f) for f in flow_ema[-20:]) / 20
    f_bull = flow > 0; f_bear = flow < 0; f_strong = abs(flow) > flow_sma * 1.2

    bb_upper, bb_lower, bb_basis, bb_bw, bb_bw_prev = bb_calc(closes)
    bb_squeeze    = bb_bw < bb_bw_prev * 0.95
    bb_expand     = bb_bw > bb_bw_prev * 1.02
    bb_break_long  = price > bb_upper
    bb_break_short = price < bb_lower

    obv = obv_calc(closes, vols); obv_ema = ema_series(obv, 20)
    obv_bull = obv[-1] > obv_ema[-1] and obv[-1] > obv[-6]
    obv_bear = obv[-1] < obv_ema[-1] and obv[-1] < obv[-6]

    vwap = vwap_calc(candles)
    above_vwap = price > vwap; below_vwap = price < vwap

    trend_bull = price > e200 and e10 > e21 and e21 > e50 and e50 > e200
    trend_bear = price < e200 and e10 < e21 and e21 < e50 and e50 < e200
    align_bull  = price > e10 and price > e21 and price > e50
    align_bear  = price < e10 and price < e21 and price < e50
    e200_rising  = e200 > e200p; e200_falling = e200 < e200p
    strong_trend = abs(e21 - e50) / atr > 0.6

    not_ext_long  = (price - e50) / atr < 4.0
    not_ext_short = (e50 - price) / atr < 4.0

    bb_range = max(bb_upper - bb_lower, 1e-10)
    price_bb_pos = (price - bb_lower) / bb_range
    near_bb_top = price_bb_pos > 0.97
    near_bb_bot = price_bb_pos < 0.03
    ext_above_ema21 = (price - e21) / atr > 3.0
    ext_below_ema21 = (e21 - price) / atr > 3.0

    vol3 = [vols[-4], vols[-3], vols[-2]]
    vol_drying = vols[-1] < vol_ma * 0.6 and vols[-1] < min(vol3) * 0.7

    rsi_not_overbought = rsi < 65

    def _low_touched_ema(ema_arr, n=5):
        return any(lows[i] <= ema_arr[i] * 1.008 for i in range(-n, -1))
    def _high_touched_ema(ema_arr, n=5):
        return any(highs[i] >= ema_arr[i] * 0.992 for i in range(-n, -1))

    pullback_bull = (_low_touched_ema(e10_arr) or _low_touched_ema(e21_arr)) and price > e10 and price > opens[-1] and ha_bull
    pullback_bear = (_high_touched_ema(e10_arr) or _high_touched_ema(e21_arr)) and price < e10 and price < opens[-1] and ha_bear

    uwick_ratio = (highs[-1] - max(opens[-1], price)) / max(highs[-1] - lows[-1], 1e-10)
    lwick_ratio = (min(opens[-1], price) - lows[-1]) / max(highs[-1] - lows[-1], 1e-10)
    exhaustion_top = uwick_ratio > 0.40 and price < (highs[-1] - bb_range * 0.02)
    exhaustion_bot = lwick_ratio > 0.40 and price > (lows[-1] + bb_range * 0.02)

    bulls_5 = sum(1 for i in range(-5, 0) if closes[i] > e21_arr[i])
    trend_consistent_bull = bulls_5 >= 4
    trend_consistent_bear = bulls_5 <= 1

    bull_impulse = price > highs[-2] and price > opens[-1] and (price - opens[-1]) > atr * 0.2
    bear_impulse = price < lows[-2] and price < opens[-1] and (opens[-1] - price) > atr * 0.2
    liq_long  = lows[-1] < lows[-2] and price > lows[-2] and price > opens[-1]
    liq_short = highs[-1] > highs[-2] and price < highs[-2] and price < opens[-1]

    crange = highs[-1] - lows[-1]
    lwick  = min(opens[-1], price) - lows[-1]
    uwick  = highs[-1] - max(opens[-1], price)
    bull_absorb = crange > 0 and lwick > crange * 0.45 and price > (lows[-1] + crange * 0.6) and vols[-1] > vol_ma
    bear_absorb = crange > 0 and uwick > crange * 0.45 and price < (highs[-1] - crange * 0.6) and vols[-1] > vol_ma

    sell_exhaust = hist < hist_p and hist_p < hist_pp and price < e21 and price < e50 and price < e200
    buy_exhaust  = hist > hist_p and hist_p > hist_pp and price > e21 and price > e50 and price > e200

    cross_10_21_bull = e10_p <= e21_p and e10 > e21
    cross_10_21_bear = e10_p >= e21_p and e10 < e21
    cross_21_50_bull = e21_p <= e50_p and e21 > e50
    cross_21_50_bear = e21_p >= e50_p and e21 < e50
    px_e50_bull = price_p <= e50_p and price > e50
    px_e50_bear = price_p >= e50_p and price < e50
    any_cross_bull = cross_10_21_bull or cross_21_50_bull or px_e50_bull
    any_cross_bear = cross_10_21_bear or cross_21_50_bear or px_e50_bear

    if cross_21_50_bull:  cross_label = "EMA21>EMA50"
    elif px_e50_bull:     cross_label = "Preco>EMA50"
    elif cross_10_21_bull: cross_label = "EMA10>EMA21"
    elif cross_21_50_bear: cross_label = "EMA21<EMA50"
    elif px_e50_bear:      cross_label = "Preco<EMA50"
    elif cross_10_21_bear: cross_label = "EMA10<EMA21"
    else:                  cross_label = ""

    swing_low  = min(lows[-9:-1])
    swing_high = max(highs[-9:-1])

    pch = [0.0] + [(closes[i] - closes[i - 1]) / closes[i] * 100 for i in range(1, n)]
    avpch = alma_series(pch, 50, 0.85, 6)
    rms_vals = [math.sqrt(sum(v * v for v in avpch[max(0, i - 49):i + 1]) / min(i + 1, 50))
                for i in range(len(avpch))]
    trendilo_long  = not math.isnan(avpch[-1]) and avpch[-1] > rms_vals[-1]
    trendilo_short = not math.isnan(avpch[-1]) and avpch[-1] < -rms_vals[-1]

    score = (
        (35 if trend_bull else -35 if trend_bear else 0) +
        (15 if f_bull else -15 if f_bear else 0) +
        (10 if f_strong else 0) +
        (20 if macd_bull else -20 if macd_bear else 0) +
        (20 if adx > 30 else 10 if adx > 22 else 0) +
        (10 if v_strong else -5) +
        (10 if rsi_bull else -10 if rsi_bear else 0) +
        (10 if e200_rising else -10 if e200_falling else 0) +
        (10 if kalman_up else -10 if kalman_down else 0) +
        (15 if obv_bull else -15 if obv_bear else 0) +
        (5 if above_vwap else -5) +
        (10 if ha_bull else -10 if ha_bear else 0) +
        (5 if kalman_accel_up else -5 if kalman_accel_down else 0) +
        (5 if trend_consistent_bull else -5 if trend_consistent_bear else 0) +
        (10 if trendilo_long else -10 if trendilo_short else 0)
    )
    score = max(-145, min(145, score))

    strong_bear_override = adx > 45 and score < -80 and trend_bear
    rsi_not_oversold = rsi > 35 or strong_bear_override
    safe_long  = not near_bb_top and not ext_above_ema21 and not vol_drying and not exhaustion_top and rsi_not_overbought
    safe_short = not near_bb_bot and not ext_below_ema21 and not vol_drying and not exhaustion_bot and rsi_not_oversold

    sideways = bb_squeeze and adx < 18
    not_ext_long_tight  = (price - e21) / atr < 2.5 and rsi < 65
    not_ext_short_tight = (e21 - price) / atr < 2.5 and (rsi > 35 or strong_bear_override)

    flex_score = score
    long_flex  = (flex_score > 30 and ha_bull and macd_bull_r and adx >= 14 and
                  not sideways and not_ext_long_tight and safe_long and rsi < 65)
    short_flex = (flex_score < -30 and ha_bear and macd_bear_r and adx >= 14 and
                  not sideways and not_ext_short_tight and safe_short and (rsi > 35 or strong_bear_override))

    trend_bull_relaxed = price > e200 and e10 > e21 and e21 > e50
    long_pullback = (pullback_bull and trend_bull_relaxed and (macd_bull or macd_recovering) and
                     adx > 18 and (f_bull or obv_bull) and v_strong and
                     above_vwap and score > 15 and not any_cross_bull and rsi < 65)
    trend_bear_relaxed = price < e200 and e10 < e21 and e21 < e50
    short_pullback = (pullback_bear and trend_bear_relaxed and (macd_bear or macd_exhausting) and
                      adx > 18 and (f_bear or obv_bear) and v_strong and
                      below_vwap and score < -15 and not any_cross_bear and (rsi > 35 or strong_bear_override))

    long_cross  = (any_cross_bull and score > 10 and adx > 15 and ha_bull and macd_bull and
                   (f_bull or obv_bull) and v_strong and not_ext_long and price > e200 * 0.97 and rsi < 65)
    short_cross = (any_cross_bear and score < -10 and adx > 15 and ha_bear and macd_bear and
                   (f_bear or obv_bear) and v_strong and not_ext_short and price < e200 * 1.03 and (rsi > 35 or strong_bear_override))

    long_bb_break  = (bb_break_long  and kalman_up   and k_short_rising  and flex_score > 20 and
                      adx >= 14 and not sideways and not ext_above_ema21 and not vol_drying and rsi < 80)
    short_bb_break = (bb_break_short and kalman_down and k_short_falling and flex_score < -20 and
                      adx >= 14 and not sideways and not ext_below_ema21 and not vol_drying and rsi > 20)

    sig = None; sig_source = ""
    if long_pullback:   sig = "LONG";  sig_source = "PULLBACK"
    elif short_pullback: sig = "SHORT"; sig_source = "PULLBACK"
    elif long_cross:    sig = "LONG";  sig_source = f"CROSS:{cross_label}"
    elif short_cross:   sig = "SHORT"; sig_source = f"CROSS:{cross_label}"
    elif long_bb_break:  sig = "LONG";  sig_source = "BB_BREAK"
    elif short_bb_break: sig = "SHORT"; sig_source = "BB_BREAK"
    elif long_flex:     sig = "LONG";  sig_source = "FLEX"
    elif short_flex:    sig = "SHORT"; sig_source = "FLEX"

    if not sig: return None

    quality_score = 0
    if sig == "LONG":
        quality_score += 3 if trend_bull else 0
        quality_score += 2 if align_bull else 0
        quality_score += 2 if macd_bull3 else (1 if macd_bull else 0)
        quality_score += 2 if ha_bull else 0
        quality_score += 2 if adx_long_ok else (1 if adx > 15 else 0)
        quality_score += 1 if obv_bull else 0
        quality_score += 1 if above_vwap else 0
        quality_score += 1 if v_strong2 else 0
        quality_score += 1 if kalman_accel_up else 0
        quality_score += 1 if e200_rising else 0
        quality_score += 1 if f_strong else 0
        quality_score += 1 if trend_consistent_bull else 0
    else:
        quality_score += 3 if trend_bear else 0
        quality_score += 2 if align_bear else 0
        quality_score += 2 if macd_bear3 else (1 if macd_bear else 0)
        quality_score += 2 if ha_bear else 0
        quality_score += 2 if adx_short_ok else (1 if adx > 15 else 0)
        quality_score += 1 if obv_bear else 0
        quality_score += 1 if below_vwap else 0
        quality_score += 1 if v_strong2 else 0
        quality_score += 1 if kalman_accel_down else 0
        quality_score += 1 if e200_falling else 0
        quality_score += 1 if f_strong else 0
        quality_score += 1 if trend_consistent_bear else 0

    if quality_score >= 14:   signal_grade = "S"
    elif quality_score >= 10: signal_grade = "A"
    else:                     signal_grade = "B"

    return {
        "sig": sig, "sig_source": sig_source, "signal_grade": signal_grade,
        "price": price, "atr": atr, "score": score,
        "rsi": rsi, "adx": adx,
        "trend": "BULL" if trend_bull else "BEAR" if trend_bear else "NEUTRO",
        "kalman_up": kalman_up,
    }

# ── SIMULAÇÃO DE TRADE ────────────────────────────────────────────────────────

def simulate_trade(signal, future_candles, max_bars=72):
    """
    Simula o trade usando as velas seguintes à entrada.
    Retorna dict com resultado: R múltiplo, saída, duração.
    """
    is_long = signal["sig"] == "LONG"
    entry   = signal["price"]
    atr     = signal["atr"]
    grade   = signal["signal_grade"]
    risk    = 1.2 * atr

    stop  = entry - risk if is_long else entry + risk

    if grade == "S":  r1, r2, r_final = 2.5, 4.5, 8.0
    elif grade == "A": r1, r2, r_final = 2.0, 3.5, 6.0
    else:              r1, r2, r_final = 2.0, 3.0, 5.0

    tp1   = entry + risk * r1    if is_long else entry - risk * r1
    tp2   = entry + risk * r2    if is_long else entry - risk * r2
    final = entry + risk * r_final if is_long else entry - risk * r_final

    tp1_hit = tp2_hit = final_hit = stop_hit = False
    exit_bar = len(future_candles)

    for i, c in enumerate(future_candles[:max_bars]):
        h, l = c["h"], c["l"]

        if is_long:
            if l <= stop:
                stop_hit = True; exit_bar = i + 1; break
            if not tp1_hit and h >= tp1:
                tp1_hit = True
            if tp1_hit and not tp2_hit and h >= tp2:
                tp2_hit = True
            if tp2_hit and not final_hit and h >= final:
                final_hit = True; exit_bar = i + 1; break
        else:
            if h >= stop:
                stop_hit = True; exit_bar = i + 1; break
            if not tp1_hit and l <= tp1:
                tp1_hit = True
            if tp1_hit and not tp2_hit and l <= tp2:
                tp2_hit = True
            if tp2_hit and not final_hit and l <= final:
                final_hit = True; exit_bar = i + 1; break

    # Calcula R médio ponderado (40% TP1 / 35% TP2 / 25% Final)
    if stop_hit and not tp1_hit:
        r_result = -1.0
        outcome  = "STOP"
    elif stop_hit and tp1_hit and not tp2_hit:
        # Stop depois do TP1: 40% em TP1 (+r1), 60% no stop (-1)
        r_result = 0.40 * r1 + 0.60 * (-1.0)
        outcome  = "STOP_AFTER_TP1"
    elif stop_hit and tp2_hit and not final_hit:
        r_result = 0.40 * r1 + 0.35 * r2 + 0.25 * (-1.0)
        outcome  = "STOP_AFTER_TP2"
    elif final_hit:
        r_result = 0.40 * r1 + 0.35 * r2 + 0.25 * r_final
        outcome  = "FULL_TP"
    elif tp2_hit:
        # Tempo esgotado após TP2: sai ao preço de fechamento da última vela
        last = future_candles[min(exit_bar, len(future_candles)) - 1]["c"]
        partial_r = (last - entry) / risk if is_long else (entry - last) / risk
        r_result = 0.40 * r1 + 0.35 * r2 + 0.25 * partial_r
        outcome  = "TIMEOUT_AFTER_TP2"
    elif tp1_hit:
        last = future_candles[min(exit_bar, len(future_candles)) - 1]["c"]
        partial_r = (last - entry) / risk if is_long else (entry - last) / risk
        r_result = 0.40 * r1 + 0.60 * partial_r
        outcome  = "TIMEOUT_AFTER_TP1"
    else:
        # Timeout sem nenhum TP
        last = future_candles[min(exit_bar, len(future_candles)) - 1]["c"]
        r_result = (last - entry) / risk if is_long else (entry - last) / risk
        outcome  = "TIMEOUT"

    return {
        "outcome": outcome,
        "r_result": round(r_result, 3),
        "tp1_hit": tp1_hit, "tp2_hit": tp2_hit, "final_hit": final_hit, "stop_hit": stop_hit,
        "bars_held": exit_bar,
    }

# ── FETCH DADOS ───────────────────────────────────────────────────────────────

async def _bybit_chunk(session, symbol, interval_by, end_ms):
    """Busca 1 chunk de até 1000 velas do Bybit (mais recente primeiro)."""
    url = f"{BYBIT_BASE}/v5/market/kline"
    params = {"category": "spot", "symbol": symbol,
              "interval": interval_by, "limit": 1000, "end": end_ms}
    async with session.get(url, params=params,
                           timeout=aiohttp.ClientTimeout(total=20)) as r:
        if r.status != 200: return []
        data = await r.json()
        if data.get("retCode") != 0: return []
        return [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]),
                 "l": float(k[3]), "c": float(k[4]), "v": float(k[5])}
                for k in data["result"]["list"]]

async def fetch_candles(session, symbol, interval="1h", months=6):
    """
    Busca velas via Bybit (primário, funciona no GitHub Actions)
    com fallback para Binance.
    """
    mins_per_candle = INTERVAL_MINUTES.get(interval, 60)
    target = months * 30 * 24 * 60 // mins_per_candle
    interval_by = BYBIT_INTERVAL.get(interval, "60")

    # ── Bybit com paginação ──────────────────────────────────────────────────
    try:
        all_candles = []
        end_ms = int(_time.time() * 1000)
        for _ in range(12):
            chunk = await _bybit_chunk(session, symbol, interval_by, end_ms)
            if not chunk:
                break
            # Bybit retorna do mais novo pro mais antigo — inverte
            chunk.sort(key=lambda x: x["t"])
            all_candles = chunk + all_candles
            if len(all_candles) >= target:
                break
            end_ms = chunk[0]["t"] - 1
            if len(chunk) < 1000:
                break

        if all_candles:
            # deduplica e ordena
            seen, unique = set(), []
            for c in sorted(all_candles, key=lambda x: x["t"]):
                if c["t"] not in seen:
                    seen.add(c["t"])
                    unique.append(c)
            print(f"  Bybit OK: {len(unique)} velas de {symbol}")
            return unique[-target:] if len(unique) > target else unique
    except Exception as e:
        print(f"  Bybit falhou ({e}), tentando Binance...")

    # ── Binance fallback ─────────────────────────────────────────────────────
    try:
        limit = min(target, 1000)
        url = f"{BINANCE_BASE}/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        async with session.get(url, params=params,
                               timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                print(f"  Binance HTTP {r.status}")
                return []
            data = await r.json()
            candles = [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]),
                        "l": float(k[3]), "c": float(k[4]), "v": float(k[5])}
                       for k in data]
            print(f"  Binance OK: {len(candles)} velas de {symbol}")
            return candles
    except Exception as e:
        print(f"  Binance falhou: {e}")
        return []

async def get_top_usdt_pairs(session, top_n=100):
    """Top N pares USDT por volume — tenta Binance, depois Bybit."""
    # Binance
    try:
        async with session.get(f"{BINANCE_BASE}/api/v3/ticker/24hr",
                               timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                data = await r.json()
                usdt = [d for d in data if d["symbol"].endswith("USDT") and
                        not any(s in d["symbol"] for s in
                                ["BUSD","USDC","EUR","BRL","UP","DOWN","BEAR","BULL"])]
                usdt.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
                return [d["symbol"] for d in usdt[:top_n]]
    except Exception:
        pass

    # Bybit fallback
    try:
        async with session.get(f"{BYBIT_BASE}/v5/market/tickers",
                               params={"category": "spot"},
                               timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                data = await r.json()
                tickers = data.get("result", {}).get("list", [])
                usdt = [t for t in tickers if t["symbol"].endswith("USDT") and
                        not any(s in t["symbol"] for s in
                                ["USDC","EUR","BRL","UP","DOWN","BEAR","BULL"])]
                usdt.sort(key=lambda x: float(x.get("turnover24h", 0)), reverse=True)
                return [t["symbol"] for t in usdt[:top_n]]
    except Exception:
        pass
    return []

# ── BACKTEST DE UM SÍMBOLO ────────────────────────────────────────────────────

def backtest_symbol(symbol, candles, cooldown_bars=12):
    """
    Roda a estratégia FLEX sobre o histórico de velas.
    Retorna lista de trades simulados.
    """
    trades = []
    last_signal_bar = -cooldown_bars  # permite sinal imediatamente

    min_bars = 210  # ~200 EMA + buffer

    for i in range(min_bars, len(candles) - 1):
        if (i - last_signal_bar) < cooldown_bars:
            continue

        window  = candles[max(0, i - 400):i + 1]
        signal  = analyze_flex(window)
        if not signal:
            continue

        future  = candles[i + 1:]
        result  = simulate_trade(signal, future)
        ts      = datetime.utcfromtimestamp(candles[i]["t"] / 1000).strftime("%Y-%m-%d %H:%M")

        trades.append({
            "symbol":   symbol,
            "ts":       candles[i]["t"] // 1000,
            "datetime": ts,
            "sig":      signal["sig"],
            "source":   signal["sig_source"],
            "grade":    signal["signal_grade"],
            "score":    signal["score"],
            "rsi":      round(signal["rsi"], 1),
            "adx":      round(signal["adx"], 1),
            "trend":    signal["trend"],
            "entry":    signal["price"],
            "atr":      round(signal["atr"], 6),
            **result,
        })
        last_signal_bar = i

    return trades

# ── RELATÓRIO ─────────────────────────────────────────────────────────────────

def print_summary(all_trades, elapsed_sec):
    if not all_trades:
        print("Nenhum trade encontrado.")
        return

    wins  = [t for t in all_trades if t["r_result"] > 0]
    losses = [t for t in all_trades if t["r_result"] <= 0]
    full_tp = [t for t in all_trades if t["outcome"] == "FULL_TP"]
    stops   = [t for t in all_trades if "STOP" in t["outcome"]]

    total   = len(all_trades)
    win_rate = len(wins) / total * 100
    avg_r    = sum(t["r_result"] for t in all_trades) / total
    avg_win  = sum(t["r_result"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["r_result"] for t in losses) / len(losses) if losses else 0
    total_r  = sum(t["r_result"] for t in all_trades)

    by_grade = {}
    for t in all_trades:
        g = t["grade"]
        by_grade.setdefault(g, []).append(t["r_result"])

    print("\n" + "=" * 60)
    print("  GAUSS+DNA BACKTEST — RESULTADOS")
    print("=" * 60)
    print(f"  Trades totais : {total}")
    print(f"  Win rate      : {win_rate:.1f}%  ({len(wins)}W / {len(losses)}L)")
    print(f"  R médio/trade : {avg_r:+.2f}R")
    print(f"  R total       : {total_r:+.1f}R")
    print(f"  Média vitórias: {avg_win:+.2f}R")
    print(f"  Média perdas  : {avg_loss:+.2f}R")
    print(f"  Full TP hits  : {len(full_tp)} ({len(full_tp)/total*100:.0f}%)")
    print(f"  Stop losses   : {len(stops)} ({len(stops)/total*100:.0f}%)")
    print()
    print("  Por grade:")
    for g in ["S", "A", "B"]:
        rs = by_grade.get(g, [])
        if rs:
            wr = sum(1 for r in rs if r > 0) / len(rs) * 100
            print(f"    Grade {g}: {len(rs)} trades | WR {wr:.0f}% | R médio {sum(rs)/len(rs):+.2f}")
    print()

    by_sym = {}
    for t in all_trades:
        by_sym.setdefault(t["symbol"], []).append(t["r_result"])
    top5 = sorted(by_sym.items(), key=lambda x: sum(x[1]), reverse=True)[:5]
    bot5 = sorted(by_sym.items(), key=lambda x: sum(x[1]))[:5]
    print("  Top 5 símbolos (R total):")
    for sym, rs in top5:
        print(f"    {sym:12s}: {sum(rs):+.1f}R  ({len(rs)} trades)")
    print("  Bottom 5 símbolos:")
    for sym, rs in bot5:
        print(f"    {sym:12s}: {sum(rs):+.1f}R  ({len(rs)} trades)")
    print(f"\n  Tempo de execução: {elapsed_sec:.0f}s")
    print("=" * 60)

def save_csv(all_trades, filename=None):
    if not all_trades: return
    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        filename = RESULTS_DIR / f"backtest_{ts}.csv"
    keys = list(all_trades[0].keys())
    with open(filename, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(all_trades)
    print(f"  CSV salvo: {filename}")

def save_json(all_trades, filename=None):
    if not all_trades: return
    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        filename = RESULTS_DIR / f"backtest_{ts}.json"
    with open(filename, "w") as f:
        json.dump(all_trades, f, indent=2)
    print(f"  JSON salvo: {filename}")
