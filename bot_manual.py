"""
GAUSS+DNA — Watchlist Manual
Roda uma vez, envia relatório das 11 moedas monitoradas no Telegram.
"""
import asyncio, os, math, time
from datetime import datetime, timezone
import aiohttp

BASE      = "https://api.mexc.com/api/v3"
TG_TOKEN  = os.environ.get("TG_TOKEN", "")
TG_CHATID = os.environ.get("TG_CHATID", "")
CAPITAL   = float(os.environ.get("CAPITAL", "180"))
RISK_PCT  = float(os.environ.get("RISK_PCT", "0.03"))
INTERVAL  = os.environ.get("INTERVAL", "30m")

WATCHLIST = [
    ("HOMEUSDT",   "HOME",   "✅ BOM"),
    ("EPICUSDT",   "EPIC",   "✅ BOM"),
    ("OPGUSDT",    "OPG",    "🔵 ACEIT"),
    ("PENGUUSDT",  "PENGU",  "🔵 ACEIT"),
    ("ASTERUSDT",  "ASTER",  "🔵 ACEIT"),
    ("IRYSUSDT",   "IRYS",   "🔵 ACEIT"),
    ("ETHFIUSDT",  "ETHFI",  "🔵 ACEIT"),
    ("POLUSDT",    "POL",    "🔵 ACEIT"),
    ("MRVLONUSDT", "MRVLON", "🔵 ACEIT"),
    ("HYPEUSDT",   "HYPE",   "🔵 ACEIT"),
    ("TIAUSDT",    "TIA",    "🔵 ACEIT"),
]

# ── Indicators ───────────────────────────────────────────────────────────────

def ema(arr, n):
    k = 2/(n+1); e = arr[0]; out = [e]
    for v in arr[1:]:
        e = v*k + e*(1-k); out.append(e)
    return out

def rma(arr, n):
    valid = [x for x in arr if x is not None]
    if len(valid) < n: return [None]*len(arr)
    k = 1/n; e = sum(valid[:n])/n
    result = [None]*(len(arr) - len(valid) + n - 1) + [e]
    for v in valid[n:]:
        e = v*k + e*(1-k); result.append(e)
    return result

def calc_rsi(closes, n=14):
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i]-closes[i-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    ag = rma(gains, n); al = rma(losses, n)
    out = [50.0]
    for i in range(len(ag)):
        if ag[i] is None: out.append(50.0); continue
        rs = ag[i]/al[i] if al[i] else 100
        out.append(100 - 100/(1+rs))
    return out

def calc_atr(h, l, c, n=14):
    trs = [h[0]-l[0]]
    for i in range(1, len(c)):
        trs.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    return rma(trs, n)

def calc_macd(closes, fast=12, slow=26, sig=9):
    ef = ema(closes, fast); es = ema(closes, slow)
    macd = [f-s for f,s in zip(ef,es)]
    signal = ema(macd, sig)
    hist = [m-s for m,s in zip(macd, signal)]
    return hist

def calc_adx(h, l, c, n=14):
    pdm, mdm, trs = [], [], []
    for i in range(1, len(c)):
        up = h[i]-h[i-1]; dn = l[i-1]-l[i]
        pdm.append(up if up>dn and up>0 else 0)
        mdm.append(dn if dn>up and dn>0 else 0)
        trs.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    atr14 = rma(trs, n); pdm14 = rma(pdm, n); mdm14 = rma(mdm, n)
    dx_list = []
    for i in range(len(atr14)):
        if atr14[i] is None or atr14[i]==0: dx_list.append(None); continue
        p = 100*pdm14[i]/atr14[i]; m = 100*mdm14[i]/atr14[i]
        dx_list.append(100*abs(p-m)/(p+m) if (p+m) else 0)
    valid_dx = [x for x in dx_list if x is not None]
    if len(valid_dx) < n: return 20.0
    adx_arr = rma(valid_dx, n)
    return adx_arr[-1] or 20.0

def calc_bb(closes, n=20):
    if len(closes) < n: return closes[-1]*1.02, closes[-1]*0.98
    sl = closes[-n:]; m = sum(sl)/n
    sd = math.sqrt(sum((x-m)**2 for x in sl)/n)
    return m+2*sd, m-2*sd

def calc_vwap(h, l, c, v):
    tp = [(hi+li+ci)/3 for hi,li,ci in zip(h,l,c)]
    cum_tv = cum_v = 0; vwap = []
    for t,vol in zip(tp, v):
        cum_tv += t*vol; cum_v += vol
        vwap.append(cum_tv/cum_v if cum_v else t)
    return vwap[-1]

def htf_conditions(candles_1h):
    """Retorna (htf_bull, htf_bear) baseado em Trendilo + RSI + volume do 1H."""
    if not candles_1h or len(candles_1h) < 30:
        return False, False
    c1 = [float(x[4]) for x in candles_1h]
    v1 = [float(x[5]) for x in candles_1h]
    trl1  = ema(ema(c1, 14), 14)
    rsi1  = calc_rsi(c1)
    j     = len(c1) - 1
    # Trendilo direction on 1H
    tl1   = trl1[j] > trl1[max(0, j-2)]
    ts1   = trl1[j] < trl1[max(0, j-2)]
    rsi1v = rsi1[j] if rsi1[j] else 50.0
    # Volume: compare last bar vs avg of previous 5
    vol_avg = sum(v1[max(0,j-5):j]) / max(1, min(5, j))
    vol_up  = v1[j] >= vol_avg * 0.85
    vol_dn  = v1[j] <= vol_avg * 1.15
    # LONG: 1H Trendilo rising + RSI oversold on 1H + volume supportive
    htf_bull = tl1 and rsi1v < 40 and vol_up
    # SHORT: 1H Trendilo falling + RSI overbought on 1H + volume declining
    htf_bear = ts1 and rsi1v > 60 and vol_dn
    return htf_bull, htf_bear

def analyze(candles, candles_1h=None):
    if len(candles) < 60: return None
    o = [float(c[1]) for c in candles]
    h = [float(c[2]) for c in candles]
    l = [float(c[3]) for c in candles]
    c = [float(c[4]) for c in candles]
    v = [float(c[5]) for c in candles]

    ha_c = [(o[i]+h[i]+l[i]+c[i])/4 for i in range(len(c))]
    ha_o = [o[0]]
    for i in range(1, len(o)):
        ha_o.append((ha_o[-1]+ha_c[i-1])/2)

    e9  = ema(c, 9);  e21 = ema(c, 21)
    e50 = ema(c, 50); e200= ema(c, 200)
    trl = ema(ema(c, 14), 14)
    macd_hist = calc_macd(c)
    rsi_arr   = calc_rsi(c)
    atr_arr   = calc_atr(h, l, c)
    bb_up, bb_lo = calc_bb(c)
    vwap = calc_vwap(h, l, c, v)
    adx  = calc_adx(h, l, c)

    i = len(c)-1
    price = c[i]; atr = atr_arr[i] or price*0.01
    rsi   = rsi_arr[i] if rsi_arr[i] else 50.0

    e9v=e9[i]; e21v=e21[i]; e50v=e50[i]; e200v=e200[i]
    trl_v=trl[i]; trl_p=trl[max(0,i-2)]

    tl  = trl_v > trl_p and price > trl_v
    ts  = trl_v < trl_p and price < trl_v
    ab  = e9v > e21v > e50v
    ab2 = e9v < e21v < e50v
    mb  = macd_hist[i] > 0 and macd_hist[i] > macd_hist[i-1]
    mr  = macd_hist[i] < 0 and macd_hist[i] < macd_hist[i-1]
    hb  = ha_c[i] > ha_o[i] and ha_c[i] > ha_c[i-1]
    hr  = ha_c[i] < ha_o[i] and ha_c[i] < ha_c[i-1]
    av  = price > vwap
    bv  = price < vwap

    # Real 1H HTF: Trendilo direction + RSI + volume on 1H candles
    htf_bull, htf_bear = htf_conditions(candles_1h)

    score = 0
    if ab:  score += 20
    elif e9v > e21v: score += 10
    if ab2: score -= 20
    elif e9v < e21v: score -= 10
    if e50v > e200v: score += 10
    else: score -= 10
    if tl:  score += 15
    if ts:  score -= 15
    if mb:  score += 12
    if mr:  score -= 12
    if hb:  score += 10
    if hr:  score -= 10
    if av:  score += 8
    if bv:  score -= 8
    if adx > 20: score = int(score * 1.1)
    score = max(-145, min(145, score))

    sig = None
    if score > 30 and tl and (mb or hb) and av and adx >= 18 and htf_bull and rsi < 74:
        sig = "LONG"
    elif score < -30 and ts and (mr or hr) and bv and adx >= 18 and htf_bear and rsi > 32:
        sig = "SHORT"

    near = None
    if sig is None:
        if score > 15 and adx > 14: near = "LONG"
        elif score < -15 and adx > 14: near = "SHORT"

    atr_pct = (atr/price)*100 if price else 1.0
    tp1_m, tp2_m, tp3_m = 1.5, 3.0, 5.0

    risk_usd  = CAPITAL * RISK_PCT
    stop_dist = 1.2 * atr
    pos_size  = risk_usd / stop_dist if stop_dist else 0
    pos_usd   = pos_size * price

    if sig == "LONG":
        stop_p = price - stop_dist
        tp1_p  = price + tp1_m * stop_dist
        tp2_p  = price + tp2_m * stop_dist
        tp3_p  = price + tp3_m * stop_dist
    elif sig == "SHORT":
        stop_p = price + stop_dist
        tp1_p  = price - tp1_m * stop_dist
        tp2_p  = price - tp2_m * stop_dist
        tp3_p  = price - tp3_m * stop_dist
    else:
        stop_p = tp1_p = tp2_p = tp3_p = 0

    tp1_usd = risk_usd * tp1_m
    tp2_usd = risk_usd * tp2_m
    tp3_usd = risk_usd * tp3_m

    return {
        "price": price, "score": score, "rsi": rsi, "adx": adx,
        "atr": atr, "atr_pct": atr_pct,
        "sig": sig, "near": near,
        "stop_p": stop_p, "tp1_p": tp1_p, "tp2_p": tp2_p, "tp3_p": tp3_p,
        "tp1_usd": tp1_usd, "tp2_usd": tp2_usd, "tp3_usd": tp3_usd,
        "tp1_m": tp1_m, "tp2_m": tp2_m, "tp3_m": tp3_m,
        "pos_usd": pos_usd, "risk_usd": risk_usd,
        "htf_bull": htf_bull, "htf_bear": htf_bear,
        "tl": tl, "ts": ts,
    }

# ── Fetch ────────────────────────────────────────────────────────────────────

async def fetch(session, sym, interval=None, limit=220):
    iv = interval or INTERVAL
    url = f"{BASE}/klines?symbol={sym}&interval={iv}&limit={limit}"
    for _ in range(3):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    if data and isinstance(data, list): return data
        except Exception:
            await asyncio.sleep(1)
    return None

# ── Format ───────────────────────────────────────────────────────────────────

def esc(s):
    for ch in r"\_*[]()~`>#+-=|{}.!":
        s = s.replace(ch, f"\\{ch}")
    return s

def fmt_price(p):
    if p >= 1000:  return f"{p:,.2f}"
    if p >= 1:     return f"{p:.4f}"
    if p >= 0.001: return f"{p:.6f}"
    return f"{p:.8f}"

def fmt_usd(v):
    return f"+${v:.2f}" if v >= 0 else f"-${abs(v):.2f}"

def build_message(results):
    now = datetime.now(timezone.utc).strftime("%d/%m %H:%M UTC")
    lines = [
        f"📊 *GAUSS\\+DNA — Watchlist*",
        f"`{esc(now)}` \\| Timeframe: {esc(INTERVAL)}",
        "",
    ]

    sinais  = [(s,r) for s,r in results if r and r["sig"]]
    proximos= [(s,r) for s,r in results if r and not r["sig"] and r["near"]]
    sem_sig = [(s,r) for s,r in results if r and not r["sig"] and not r["near"]]
    erros   = [(s,r) for s,r in results if not r]

    if sinais:
        lines.append("🚨 *SINAIS ATIVOS*")
        for (sym, label, grade), r in sinais:
            emoji = "🟢" if r["sig"]=="LONG" else "🔴"
            p = fmt_price(r["price"])
            lines.append(f"\n{emoji} *{esc(label)}* — {esc(r['sig'])}")
            lines.append(f"Preço: `${esc(p)}` \\| Score: `{r['score']:+d}` \\| RSI: `{r['rsi']:.0f}` \\| ADX: `{r['adx']:.0f}`")
            if r["sig"]:
                sp = fmt_price(r["stop_p"])
                t1 = fmt_price(r["tp1_p"])
                t2 = fmt_price(r["tp2_p"])
                t3 = fmt_price(r["tp3_p"])
                lines.append(f"Stop: `${esc(sp)}`  Risco: `${r['risk_usd']:.2f}`  Pos: `${r['pos_usd']:.0f}`")
                lines.append(
                    f"TP1 `{r['tp1_m']}R` \\= `${esc(t1)}` \\({esc(fmt_usd(r['tp1_usd']))}\\) \\| "
                    f"TP2 `{r['tp2_m']}R` \\= `${esc(t2)}` \\({esc(fmt_usd(r['tp2_usd']))}\\) \\| "
                    f"TP3 `{r['tp3_m']}R` \\= `${esc(t3)}` \\({esc(fmt_usd(r['tp3_usd']))}\\)"
                )
        lines.append("")

    if proximos:
        lines.append("🟡 *PRÓXIMOS DE SINAL*")
        for (sym, label, grade), r in proximos:
            arrow = "↗" if r["near"]=="LONG" else "↘"
            p = fmt_price(r["price"])
            htf = "✓HTF" if (r["near"]=="LONG" and r["htf_bull"]) or (r["near"]=="SHORT" and r["htf_bear"]) else "✗HTF"
            trl = "✓Trl" if (r["near"]=="LONG" and r["tl"]) or (r["near"]=="SHORT" and r["ts"]) else "✗Trl"
            lines.append(
                f"  {arrow} *{esc(label)}* `${esc(p)}` Score:`{r['score']:+d}` RSI:`{r['rsi']:.0f}` ADX:`{r['adx']:.0f}` {esc(htf)} {esc(trl)}"
            )
        lines.append("")

    lines.append("⚪ *SEM SINAL*")
    for (sym, label, grade), r in sem_sig:
        if r:
            p = fmt_price(r["price"])
            lines.append(
                f"  *{esc(label)}* `${esc(p)}` Score:`{r['score']:+d}` RSI:`{r['rsi']:.0f}` ADX:`{r['adx']:.0f}`"
            )
    for (sym, label, grade), _ in erros:
        lines.append(f"  ⚠️ {esc(label)} — erro ao buscar dados")

    lines.append("")
    lines.append(f"💰 Capital: `${CAPITAL:.0f}` \\| Risco/trade: `{RISK_PCT*100:.0f}%` \\= `${CAPITAL*RISK_PCT:.2f}`")

    return "\n".join(lines)

# ── Telegram ─────────────────────────────────────────────────────────────────

async def send_tg(session, text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHATID, "text": text, "parse_mode": "MarkdownV2",
               "disable_web_page_preview": True}
    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            if not data.get("ok"):
                print(f"TG erro: {data}")
                # retry plain text
                payload2 = {"chat_id": TG_CHATID, "text": text.replace("\\","").replace("*","").replace("`",""),
                            "parse_mode": ""}
                async with session.post(url, json=payload2) as r2:
                    d2 = await r2.json()
                    print("retry:", d2.get("ok"))
    except Exception as e:
        print(f"TG exception: {e}")

# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    if not TG_TOKEN or not TG_CHATID:
        print("❌ TG_TOKEN ou TG_CHATID não configurado!")
        return

    print(f"🔍 Verificando {len(WATCHLIST)} moedas ({INTERVAL})...")
    results = []

    async with aiohttp.ClientSession() as session:
        tasks_30m = [fetch(session, sym, INTERVAL) for sym, _, _ in WATCHLIST]
        tasks_1h  = [fetch(session, sym, '1h', limit=100) for sym, _, _ in WATCHLIST]
        all_30m, all_1h = await asyncio.gather(
            asyncio.gather(*tasks_30m),
            asyncio.gather(*tasks_1h),
        )

        for (sym, label, grade), candles, c1h in zip(WATCHLIST, all_30m, all_1h):
            r = analyze(candles, c1h) if candles else None
            results.append(((sym, label, grade), r))
            sig_str = r["sig"] or r["near"] or "sem sinal" if r else "ERRO"
            score_str = f"score={r['score']:+d}" if r else ""
            print(f"  {label:8s} | {sig_str:10s} | {score_str}")

        msg = build_message(results)
        print("\n📤 Enviando para Telegram...")
        await send_tg(session, msg)
        print("✅ Enviado!")

if __name__ == "__main__":
    asyncio.run(main())
