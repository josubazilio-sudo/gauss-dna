"""
GAUSS+DNA — Indicadores técnicos
Funções puras de cálculo: EMA, RSI, MACD, ADX, Kalman, BB, OBV, VWAP, Heikin-Ashi.
"""
import math


# ── Médias móveis ─────────────────────────────────────────────────────────────

def serie_ema(arr, periodo):
    k = 2.0 / (periodo + 1)
    out = [arr[0]]
    for v in arr[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out

def serie_rma(arr, periodo):
    out = [sum(arr[:periodo]) / periodo]
    for v in arr[periodo:]:
        out.append((out[-1] * (periodo - 1) + v) / periodo)
    return out

def serie_alma(src, comprimento=50, offset=0.85, sigma=6):
    """Arnaud Legoux Moving Average — igual ao ta.alma() do Pine Script."""
    n = len(src)
    m = math.floor(offset * (comprimento - 1))
    s = comprimento / sigma
    pesos = [math.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(comprimento)]
    soma_pesos = sum(pesos)
    out = [float('nan')] * (comprimento - 1)
    for i in range(comprimento - 1, n):
        val = sum(pesos[j] * src[i - comprimento + 1 + j] for j in range(comprimento)) / soma_pesos
        out.append(val)
    return out

def filtro_kalman(src, comprimento, R=0.01, Q=0.1):
    est = src[0]; err = 1.0; out = []
    for s in src:
        em = R * comprimento
        ganho = err / (err + em)
        est = est + ganho * (s - est)
        err = (1 - ganho) * err + Q / comprimento
        out.append(est)
    return out


# ── ATR ───────────────────────────────────────────────────────────────────────

def serie_atr(candles, periodo=14):
    trs = [candles[0]["h"] - candles[0]["l"]]
    for i in range(1, len(candles)):
        h, l, fc = candles[i]["h"], candles[i]["l"], candles[i-1]["c"]
        trs.append(max(h - l, abs(h - fc), abs(l - fc)))
    rma = serie_rma(trs, periodo)
    return [trs[0]] * periodo + rma[1:]


# ── RSI ───────────────────────────────────────────────────────────────────────

def calcular_rsi(fechamentos, periodo=14):
    ganhos = [0.0]; perdas = [0.0]
    for i in range(1, len(fechamentos)):
        d = fechamentos[i] - fechamentos[i-1]
        ganhos.append(max(d, 0)); perdas.append(max(-d, 0))
    ag = sum(ganhos[1:periodo+1]) / periodo
    al = sum(perdas[1:periodo+1]) / periodo
    for i in range(periodo + 1, len(fechamentos)):
        ag = (ag * (periodo - 1) + ganhos[i]) / periodo
        al = (al * (periodo - 1) + perdas[i]) / periodo
    return 100.0 if al == 0 else 100 - (100 / (1 + ag / al))

def serie_rsi(fechamentos, periodo=14):
    if len(fechamentos) < periodo + 2:
        return []
    ganhos = [0.0]; perdas = [0.0]
    for i in range(1, len(fechamentos)):
        d = fechamentos[i] - fechamentos[i-1]
        ganhos.append(max(d, 0)); perdas.append(max(-d, 0))
    ag = sum(ganhos[1:periodo+1]) / periodo
    al = sum(perdas[1:periodo+1]) / periodo
    out = []
    for i in range(periodo + 1, len(fechamentos)):
        ag = (ag * (periodo - 1) + ganhos[i]) / periodo
        al = (al * (periodo - 1) + perdas[i]) / periodo
        out.append(100.0 if al == 0 else 100 - (100 / (1 + ag / al)))
    return out


# ── MACD ──────────────────────────────────────────────────────────────────────

def calcular_macd(fechamentos, rapida=12, lenta=26, sinal=9):
    ea = serie_ema(fechamentos, rapida)
    eb = serie_ema(fechamentos, lenta)
    linha = [a - b for a, b in zip(ea, eb)]
    sl = serie_ema(linha, sinal)
    hist = [m - s for m, s in zip(linha, sl)]
    h_prev = hist[-2] if len(hist) > 1 else hist[-1]
    h_prev2 = hist[-3] if len(hist) > 2 else hist[-1]
    return linha[-1], sl[-1], hist[-1], h_prev, h_prev2


# ── DMI / ADX ─────────────────────────────────────────────────────────────────

def calcular_adx(candles, periodo=14, suavizacao=14):
    pdm, mdm, tr = [], [], []
    for i in range(1, len(candles)):
        h, l = candles[i]["h"], candles[i]["l"]
        ph, pl, fc = candles[i-1]["h"], candles[i-1]["l"], candles[i-1]["c"]
        sobe, desce = h - ph, pl - l
        pdm.append(sobe if sobe > desce and sobe > 0 else 0)
        mdm.append(desce if desce > sobe and desce > 0 else 0)
        tr.append(max(h - l, abs(h - fc), abs(l - fc)))
    rtr = serie_rma(tr, periodo)
    rpdm = serie_rma(pdm, periodo)
    rmdm = serie_rma(mdm, periodo)
    dx = []
    for i in range(len(rtr)):
        t = rtr[i] or 1e-10
        pdi = (rpdm[i] / t) * 100
        mdi = (rmdm[i] / t) * 100
        dx.append(abs(pdi - mdi) / (pdi + mdi or 1) * 100)
    adx_arr = serie_rma(dx, suavizacao)
    idx = len(adx_arr) - 1
    t = rtr[idx] or 1e-10
    pdi = (rpdm[idx] / t) * 100
    mdi = (rmdm[idx] / t) * 100
    adx_ant = adx_arr[idx - 1] if idx > 0 else adx_arr[idx]
    return pdi, mdi, adx_arr[idx], adx_ant


# ── Heikin-Ashi ───────────────────────────────────────────────────────────────

def serie_heikin_ashi(candles):
    """Converte candles reais em Heikin-Ashi. Open é a média do HA anterior."""
    ha = []
    for i, c in enumerate(candles):
        hc = (c["o"] + c["h"] + c["l"] + c["c"]) / 4
        ho = (c["o"] + c["c"]) / 2 if i == 0 else (ha[-1]["o"] + ha[-1]["c"]) / 2
        ha.append({
            "o": ho,
            "h": max(c["h"], ho, hc),
            "l": min(c["l"], ho, hc),
            "c": hc,
        })
    return ha


# ── Bollinger Bands ───────────────────────────────────────────────────────────

def calcular_bb(fechamentos, periodo=20, mult=2.0):
    """Retorna: superior, inferior, base, largura_atual, largura_anterior."""
    def _bw(data):
        base = sum(data) / periodo
        dp = math.sqrt(sum((c - base) ** 2 for c in data) / periodo)
        return (2 * mult * dp) / (base or 1e-10), base + mult * dp, base - mult * dp, base

    bw, superior, inferior, base = _bw(fechamentos[-periodo:])
    bw_ant, _, _, _ = _bw(fechamentos[-(periodo+1):-1]) if len(fechamentos) >= periodo + 1 else (bw, 0, 0, 0)
    return superior, inferior, base, bw, bw_ant


# ── OBV ───────────────────────────────────────────────────────────────────────

def calcular_obv(fechamentos, volumes):
    """On-Balance Volume: fluxo acumulado de volume."""
    obv = [0.0]
    for i in range(1, len(fechamentos)):
        if fechamentos[i] > fechamentos[i-1]:
            obv.append(obv[-1] + volumes[i])
        elif fechamentos[i] < fechamentos[i-1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


# ── VWAP ──────────────────────────────────────────────────────────────────────

def calcular_vwap(candles, periodo=20):
    """VWAP sobre as últimas N velas."""
    sl = candles[-periodo:]
    vp = sum((c["h"] + c["l"] + c["c"]) / 3 * c["v"] for c in sl)
    tv = sum(c["v"] for c in sl)
    return vp / tv if tv > 0 else sl[-1]["c"]


# ── Utilitários ───────────────────────────────────────────────────────────────

def formatar_preco(preco):
    if preco < 0.0001: return f"{preco:.7f}"
    if preco < 0.01:   return f"{preco:.5f}"
    if preco < 1:      return f"{preco:.4f}"
    if preco < 100:    return f"{preco:.3f}"
    return f"{preco:,.2f}"

def tf_para_minutos(tf):
    """Converte '15m', '1h', '4h' em minutos."""
    tf = tf.lower()
    if tf.endswith('m'): return int(tf[:-1])
    if tf.endswith('h'): return int(tf[:-1]) * 60
    if tf.endswith('d'): return int(tf[:-1]) * 1440
    return 15

def segundos_ate_fechamento(tf_min):
    """Segundos até o fechamento da próxima vela (alinhado ao horário UTC)."""
    import time
    intervalo = tf_min * 60
    decorrido = time.time() % intervalo
    return intervalo - decorrido
