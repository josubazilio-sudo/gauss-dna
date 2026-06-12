"""
GAUSS+DNA — Análise técnica
Dividida em 3 etapas: calcular indicadores → detectar sinais → graduar qualidade.
"""
import math
import logging
from indicators import (
    serie_ema, serie_rma, serie_atr, serie_alma,
    calcular_rsi, serie_rsi, calcular_macd, calcular_adx,
    serie_heikin_ashi, calcular_bb, calcular_obv, calcular_vwap,
    filtro_kalman,
)
from config import SIGNAL_MODE, FILTER_LEVEL as _FLV

log = logging.getLogger("GAUSS+DNA")


# ══════════════════════════════════════════════════════════════════════════════
# ETAPA 1 — CALCULAR INDICADORES
# ══════════════════════════════════════════════════════════════════════════════

def calcular_indicadores(candles):
    """
    Recebe lista de candles reais e retorna dict com todos os indicadores calculados.
    Base é Heikin-Ashi para suavizar ruído, mas preço de entrada/stop usa real.
    """
    n = len(candles)
    if n < 60:
        return None

    ha = serie_heikin_ashi(candles)
    fechamentos = [c["c"] for c in ha]
    maximas     = [c["h"] for c in ha]
    minimas     = [c["l"] for c in ha]
    aberturas   = [c["o"] for c in ha]
    volumes          = [c["v"] for c in candles]   # volume real
    fechamentos_reais = [c["c"] for c in candles]  # closes reais (para OBV)
    preco            = candles[-1]["c"]             # preço real para stops e entradas

    # EMAs com valores anteriores para detectar cruzamentos
    e10_arr = serie_ema(fechamentos, 10);  e10 = e10_arr[-1]; e10_p = e10_arr[-2]
    e21_arr = serie_ema(fechamentos, 21);  e21 = e21_arr[-1]; e21_p = e21_arr[-2]
    e50_arr = serie_ema(fechamentos, 50);  e50 = e50_arr[-1]; e50_p = e50_arr[-2]
    e200_arr = serie_ema(fechamentos, 200); e200 = e200_arr[-1]; e200_p = e200_arr[-4] if n > 4 else e200
    preco_p  = fechamentos[-2]

    # ATR
    atr_arr = serie_atr(candles, 14)
    atr     = max(atr_arr[-1], 1e-10)

    # Kalman (spread crescendo = momentum se fortalecendo)
    ks = filtro_kalman(fechamentos, 50)
    kl = filtro_kalman(fechamentos, 150)
    kalman_subindo  = ks[-1] > kl[-1]
    kalman_descendo = ks[-1] < kl[-1]
    spread_k  = ks[-1] - kl[-1]; spread_k_p = ks[-2] - kl[-2]
    kalman_accel_up   = spread_k  > spread_k_p  > 0
    kalman_accel_down = spread_k  < spread_k_p  < 0
    k_short_subindo  = ks[-1] > ks[-2]
    k_short_descendo = ks[-1] < ks[-2]

    # MACD
    ml, sl_v, hist, hist_p, hist_pp = calcular_macd(fechamentos)
    macd_bull  = ml > sl_v and hist > hist_p and hist > 0
    macd_bear  = ml < sl_v and hist < hist_p and hist < 0
    macd_bull3 = macd_bull and hist_p > hist_pp
    macd_bear3 = macd_bear and hist_p < hist_pp
    # Exige 2 barras seguidas de melhora/piora — uma única barra é ruído e
    # deixa entradas antecipadas (SETUP/EARLY/REVERSAL) vulneráveis a reversões falsas
    macd_recuperando = hist > hist_p and hist_p > hist_pp
    macd_esgotando   = hist < hist_p and hist_p < hist_pp

    # Heikin-Ashi: corpo mínimo filtra dojis nos sinais de 2+ candles
    # ha_bull_1/bear_1 (SCOUT) não exige corpo — direção HA já é suficiente com os outros filtros
    ha_corpo_ok = abs(fechamentos[-1] - aberturas[-1]) > atr * 0.15
    ha_bull  = fechamentos[-1] > aberturas[-1] and fechamentos[-2] > aberturas[-2] and ha_corpo_ok
    ha_bear  = fechamentos[-1] < aberturas[-1] and fechamentos[-2] < aberturas[-2] and ha_corpo_ok
    ha_bull3 = ha_bull and fechamentos[-3] > aberturas[-3]
    ha_bear3 = ha_bear and fechamentos[-3] < aberturas[-3]
    ha_bull2 = ha_bull and ha_corpo_ok
    ha_bear2 = ha_bear and ha_corpo_ok
    ha_bull_1 = fechamentos[-1] > aberturas[-1]
    ha_bear_1 = fechamentos[-1] < aberturas[-1]

    # RSI
    rsi       = calcular_rsi(fechamentos[-50:])
    rsi_ant   = calcular_rsi(fechamentos[-53:-3]) if n >= 53 else rsi
    rsi_6     = calcular_rsi(fechamentos[-56:-6]) if n >= 56 else rsi
    rsi_9     = calcular_rsi(fechamentos[-59:-9]) if n >= 59 else rsi
    rsi_subindo  = rsi > rsi_ant
    rsi_caindo   = rsi < rsi_ant

    rsi_dip_short      = rsi_ant < 35 or rsi_6 < 35 or rsi_9 < 35
    rsi_rebound_short  = 38 <= rsi <= 46 and rsi > rsi_ant
    rsi_spike_long     = rsi_ant > 65 or rsi_6 > 65 or rsi_9 > 65
    rsi_rebound_long   = 46 <= rsi <= 62 and rsi < rsi_ant

    rsi_div_bull = fechamentos[-1] < fechamentos[-4] and rsi > rsi_ant and rsi < 45
    rsi_div_bear = fechamentos[-1] > fechamentos[-4] and rsi < rsi_ant and rsi > 55
    rsi_bull       = 50 < rsi < 65
    rsi_bear       = 35 < rsi < 50
    rsi_bull_elite = 48 < rsi < 65 and rsi_subindo
    rsi_bear_elite = 35 < rsi < 52 and rsi_caindo

    # Stoch RSI
    _rsi_ser = serie_rsi(fechamentos[-45:])
    if len(_rsi_ser) >= 14:
        _r14 = _rsi_ser[-14:]; _rmin = min(_r14); _rmax = max(_r14)
        stoch_rsi = (_r14[-1] - _rmin) / (_rmax - _rmin) if _rmax > _rmin else 0.5
    else:
        stoch_rsi = 0.5
    stoch_esticado_up   = stoch_rsi > 0.80
    stoch_esticado_down = stoch_rsi < 0.05

    # DMI / ADX
    pdi, mdi, adx, adx_p = calcular_adx(candles[-60:])
    adx_long_ok  = adx > 22 and pdi > mdi and adx > adx_p
    adx_short_ok = adx > 22 and mdi > pdi and adx > adx_p

    # Volume — RVOL 4 tiers (atual e anterior — pega sinal que ocorreu na vela passada)
    vol_ma = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else sum(volumes[:-1]) / max(len(volumes)-1, 1)
    rvol       = volumes[-1] / max(vol_ma, 1e-10)
    rvol_prev  = volumes[-2] / max(vol_ma, 1e-10) if len(volumes) >= 2 else rvol
    rvol_max2  = max(rvol, rvol_prev)   # melhor das últimas 2 velas
    rvol_tier  = (4 if rvol >= 3.0 else 3 if rvol >= 2.0 else
                  2 if rvol >= 1.5 else 1 if rvol >= 1.2 else 0)
    rvol_tier_max2 = (4 if rvol_max2 >= 3.0 else 3 if rvol_max2 >= 2.0 else
                      2 if rvol_max2 >= 1.5 else 1 if rvol_max2 >= 1.2 else 0)
    rvol_label = ("INST" if rvol_tier==4 else "VSTRONG" if rvol_tier==3 else
                  "STRONG" if rvol_tier==2 else "BOM"    if rvol_tier==1 else "BAIXO")
    v_bom    = rvol_tier >= 1
    v_forte  = rvol_tier >= 2
    v_inst   = rvol_tier >= 4
    v_forte2 = v_forte and volumes[-2] > vol_ma * 0.9

    # Flow institucional
    flow_raw  = [((c["c"]-c["o"]) / max(c["h"]-c["l"], 1e-10)) * c["v"] for c in candles]
    flow_ema  = serie_ema(flow_raw, 13)
    flow      = flow_ema[-1]
    flow_sma  = sum(abs(f) for f in flow_ema[-20:]) / 20
    f_bull    = flow > 0; f_bear = flow < 0; f_forte = abs(flow) > flow_sma * 1.2
    meio_corpo  = (maximas[-1] + minimas[-1]) / 2
    pressao_bull = preco > meio_corpo
    pressao_bear = preco < meio_corpo
    dna_flow_bull = macd_bull and pressao_bull and v_bom
    dna_flow_bear = macd_bear and pressao_bear and v_bom

    # Bollinger Bands
    bb_sup, bb_inf, bb_base, bb_bw, bb_bw_p = calcular_bb(fechamentos)
    bb_squeeze     = bb_bw < bb_bw_p * 0.95
    bb_expand      = bb_bw > bb_bw_p * 1.02
    bb_break_long  = preco > bb_sup
    bb_break_short = preco < bb_inf

    # OBV
    obv       = calcular_obv(fechamentos_reais, volumes)
    obv_ema   = serie_ema(obv, 20)
    obv_bull  = obv[-1] > obv_ema[-1] and obv[-1] > obv[-6]
    obv_bear  = obv[-1] < obv_ema[-1] and obv[-1] < obv[-6]

    # VWAP
    vwap         = calcular_vwap(candles)
    acima_vwap   = preco > vwap
    abaixo_vwap  = preco < vwap

    # Tendência
    tendencia_bull  = preco > e200 and e10 > e21 and e21 > e50 and e50 > e200
    tendencia_bear  = preco < e200 and e10 < e21 and e21 < e50 and e50 < e200
    alinhado_bull   = preco > e10 and preco > e21 and preco > e50
    alinhado_bear   = preco < e10 and preco < e21 and preco < e50
    e200_subindo    = e200 > e200_p; e200_descendo = e200 < e200_p
    tendencia_forte = abs(e21 - e50) / atr > 0.6
    nao_ext_long    = (preco - e50) / atr < 4.0
    nao_ext_short   = (e50 - preco) / atr < 4.0

    # Anti-topo / Anti-fundo
    bb_range   = max(bb_sup - bb_inf, 1e-10)
    pos_bb     = (preco - bb_inf) / bb_range
    perto_bb_topo = pos_bb > 0.97
    perto_bb_fund = pos_bb < 0.03
    ext_acima_e21  = (preco - e21) / atr > 3.0
    ext_abaixo_e21 = (e21 - preco) / atr > 3.0
    # vol_secando: usa max das 2 últimas velas (igual a rvol_max2/vol_nao_fade)
    # volumes[-1] pode ser candle parcial (recém aberto) → volume artificialmente baixo
    _vol_sec = max(volumes[-1], volumes[-2])
    vol_secando = _vol_sec < vol_ma * 0.25 and _vol_sec < min(volumes[-5], volumes[-4], volumes[-3]) * 0.5

    def _minima_tocou_ema(ema_arr, n=5):
        return any(minimas[i] <= ema_arr[i] * 1.015 for i in range(-n, -1))
    def _maxima_tocou_ema(ema_arr, n=5):
        return any(maximas[i] >= ema_arr[i] * 0.985 for i in range(-n, -1))

    pullback_bull = (_minima_tocou_ema(e10_arr) or _minima_tocou_ema(e21_arr)) and preco > e10 and preco > aberturas[-1] and ha_bull
    pullback_bear = (_maxima_tocou_ema(e10_arr) or _maxima_tocou_ema(e21_arr)) and preco < e10 and preco < aberturas[-1] and ha_bear

    # ── MA50 strategy indicators ──────────────────────────────────────────────
    e200_inclinada_up   = e200_arr[-1] > e200_arr[-6] if len(e200_arr) >= 6 else False
    e200_inclinada_down = e200_arr[-1] < e200_arr[-6] if len(e200_arr) >= 6 else False

    reteste_mm50_bull = any(
        minimas[i] <= e50_arr[i] * 1.015 and minimas[i] >= e50_arr[i] * 0.980
        for i in range(-7, -1)
    )
    reteste_mm50_bear = any(
        maximas[i] >= e50_arr[i] * 0.985 and maximas[i] <= e50_arr[i] * 1.020
        for i in range(-7, -1)
    )

    max_recente6 = max(maximas[-7:-1])
    min_recente6 = min(minimas[-7:-1])
    correcao_bull = 0.02 <= (max_recente6 - preco) / max(max_recente6, 1e-10) <= 0.06
    correcao_bear = 0.02 <= (preco - min_recente6) / max(preco, 1e-10) <= 0.06

    range_vela = maximas[-1] - minimas[-1]
    sombra_sup = (maximas[-1] - max(aberturas[-1], preco)) / max(range_vela, 1e-10)
    sombra_inf = (min(aberturas[-1], preco) - minimas[-1]) / max(range_vela, 1e-10)
    exaustao_topo = sombra_sup > 0.40 and preco < (maximas[-1] - bb_range * 0.02)
    exaustao_fund = sombra_inf > 0.40 and preco > (minimas[-1] + bb_range * 0.02)

    bulls_5 = sum(1 for i in range(-5, 0) if fechamentos[i] > e21_arr[i])
    tend_consistente_bull = bulls_5 >= 4
    tend_consistente_bear = bulls_5 <= 1

    impulso_bull  = preco > maximas[-2] and preco > aberturas[-1] and (preco - aberturas[-1]) > atr * 0.2
    impulso_bear  = preco < minimas[-2] and preco < aberturas[-1] and (aberturas[-1] - preco) > atr * 0.2
    liq_long  = minimas[-1] < minimas[-2] and preco > minimas[-2] and preco > aberturas[-1]
    liq_short = maximas[-1] > maximas[-2] and preco < maximas[-2] and preco < aberturas[-1]

    sm_swing_h = max(maximas[-21:-1]); sm_swing_l = min(minimas[-21:-1])
    liq_topo = ((maximas[-2] >= sm_swing_h or maximas[-1] >= sm_swing_h) and
                fechamentos[-1] < sm_swing_h and (maximas[-1] - fechamentos[-1]) > atr * 0.2)
    liq_fundo = ((minimas[-2] <= sm_swing_l or minimas[-1] <= sm_swing_l) and
                 fechamentos[-1] > sm_swing_l and (fechamentos[-1] - minimas[-1]) > atr * 0.2)

    crange = maximas[-1] - minimas[-1]
    lwick  = min(aberturas[-1], preco) - minimas[-1]
    uwick  = maximas[-1] - max(aberturas[-1], preco)
    absorb_bull = crange > 0 and lwick > crange*0.45 and preco > (minimas[-1]+crange*0.6) and volumes[-1] > vol_ma
    absorb_bear = crange > 0 and uwick > crange*0.45 and preco < (maximas[-1]-crange*0.6) and volumes[-1] > vol_ma

    # Armadilha de liquidez (trap): preço varre o topo/fundo recente para "caçar"
    # stops (liq_topo/fundo), é absorvido por volume forte com pavio de rejeição
    # (absorb) e fecha revertido (ha) — assinatura cirúrgica de smart money,
    # não apenas um cruzamento de cor de vela após o rompimento falso
    sm_bull = liq_fundo and absorb_bull and v_forte and ha_bull and (dna_flow_bull or f_bull)
    sm_bear = liq_topo  and absorb_bear and v_forte and ha_bear and (dna_flow_bear or f_bear)

    exaustao_venda  = hist < hist_p and hist_p < hist_pp and preco < e21 and preco < e50 and preco < e200
    exaustao_compra = hist > hist_p and hist_p > hist_pp and preco > e21 and preco > e50 and preco > e200

    cross_10_21_bull = e10_p <= e21_p and e10 > e21
    cross_10_21_bear = e10_p >= e21_p and e10 < e21
    cross_21_50_bull = e21_p <= e50_p and e21 > e50
    cross_21_50_bear = e21_p >= e50_p and e21 < e50
    px_e50_bull = preco_p <= e50_p and preco > e50
    px_e50_bear = preco_p >= e50_p and preco < e50
    algum_cross_bull = cross_10_21_bull or cross_21_50_bull or px_e50_bull
    algum_cross_bear = cross_10_21_bear or cross_21_50_bear or px_e50_bear

    if cross_21_50_bull:   label_cross = "EMA21 > EMA50"
    elif px_e50_bull:      label_cross = "Preço > EMA50"
    elif cross_10_21_bull: label_cross = "EMA10 > EMA21"
    elif cross_21_50_bear: label_cross = "EMA21 < EMA50"
    elif px_e50_bear:      label_cross = "Preço < EMA50"
    elif cross_10_21_bear: label_cross = "EMA10 < EMA21"
    else:                  label_cross = ""

    swing_low  = min(minimas[-13:-1])
    swing_high = max(maximas[-13:-1])

    # Trendilo (ALMA do % de variação + bandas RMS)
    pch    = [0.0] + [(fechamentos[i]-fechamentos[i-1])/fechamentos[i]*100 for i in range(1, n)]
    avpch  = serie_alma(pch, 50, 0.85, 6)
    rms_v  = [math.sqrt(sum(v*v for v in avpch[max(0,i-49):i+1]) / min(i+1,50)) for i in range(len(avpch))]
    trendilo_long  = not math.isnan(avpch[-1]) and avpch[-1] >  rms_v[-1]
    trendilo_short = not math.isnan(avpch[-1]) and avpch[-1] < -rms_v[-1]

    # Tendência relaxada (FLEX)
    tbull_r     = preco > e200 and e10 > e21 and e21 > e50
    tbear_r     = preco < e200 and e10 < e21 and e21 < e50
    tbull_loose = e10 > e21 and e21 > e50
    tbear_loose = e10 < e21 and e21 < e50

    # Filtros de segurança compostos
    rsi_nao_topo   = rsi < 70
    rsi_nao_fundo  = rsi > 27
    seguro_long  = (not perto_bb_topo and not ext_acima_e21 and not vol_secando and
                    not exaustao_topo and rsi_nao_topo and not stoch_esticado_up)
    seguro_short = (not vol_secando and not exaustao_fund and rsi_nao_fundo and not stoch_esticado_down)

    # Volume FLEX
    vol_avg       = volumes[-1] > vol_ma * 1.1 and volumes[-2] > vol_ma * 0.9
    _vol_thr      = 0.20 if _FLV <= 0 else (0.50 if _FLV == 1 else (0.65 if _FLV == 2 else 0.80))
    vol_nao_fade  = vol_ma > 0 and max(volumes[-1], volumes[-2]) >= vol_ma * _vol_thr
    vol_ok        = v_forte or obv_bull
    vol_ok_s      = v_forte or obv_bear
    flex_vol_ok   = v_bom or (obv_bull and (trendilo_long or kalman_subindo))
    flex_vol_ok_s = v_bom or (obv_bear and (trendilo_short or kalman_descendo))

    # DNA Flow relaxado (FLEX)
    macd_bull_r  = (ml > sl_v) or (hist > hist_p)
    macd_bear_r  = (ml < sl_v) or (hist < hist_p)
    dna_flex_bull = (macd_bull_r and pressao_bull and v_bom) or dna_flow_bull
    dna_flex_bear = (macd_bear_r and pressao_bear and v_bom) or dna_flow_bear

    # Filtros anti-overextension (FLEX)
    lateralizado       = bb_squeeze and adx < 15
    nao_ext_long_tight = (preco - e21) / atr < 2.5 and (rsi < 65 or (adx > 32 and rsi < 75))
    nao_ext_short_tight = (e21 - preco) / atr < 3.5 and rsi > 27

    # Anti-pump / anti-dump
    raw_c48 = [c["c"] for c in candles[-50:-1]]
    nao_overext_long  = (preco - min(raw_c48)) / max(min(raw_c48), 1e-10) < 0.50
    nao_overext_short = (max(raw_c48) - preco) / max(max(raw_c48), 1e-10) < 0.50
    rsi_nao_chasing_long  = (rsi - rsi_ant) < 18
    rsi_nao_chasing_short = (rsi_ant - rsi) < 18

    # RSI zona de entrada — autorizado pelo usuário em 10/06 (era 55/45)
    rsi_zona_long  = rsi < 60
    rsi_zona_short = rsi > 40
    # Janela RSI para entrada — evita comprar em queda livre / vender em recuperação
    # Exceções: REVERSAL (RSI extremo), REBOUND (RSI baixo), SURGE (breakout move RSI)
    rsi_entrada_long  = rsi >= 45   # não comprar quando RSI ainda está no fundo
    rsi_entrada_short = rsi <= 55   # não vender quando RSI ainda está alto

    # SURGE
    candle_bull_pct = (preco - aberturas[-1]) / max(aberturas[-1], 1e-10)
    candle_bear_pct = (aberturas[-1] - preco) / max(aberturas[-1], 1e-10)
    surge_break_h   = preco > max(maximas[-11:-1])
    surge_break_l   = preco < min(minimas[-11:-1])

    # Score de mercado (-145 a +145)
    score = (
        (35 if tendencia_bull else -35 if tendencia_bear else 0) +
        (15 if f_bull else -15 if f_bear else 0) +
        (10 if f_forte else 0) +
        (20 if macd_bull else -20 if macd_bear else 0) +
        (20 if adx > 30 else 10 if adx > 22 else 0) +
        (10 if v_forte else -5) +
        (10 if rsi_bull else -10 if rsi_bear else 0) +
        (10 if e200_subindo else -10 if e200_descendo else 0) +
        (10 if kalman_subindo else -10 if kalman_descendo else 0) +
        (15 if obv_bull else -15 if obv_bear else 0) +
        (5  if acima_vwap else -5) +
        (10 if ha_bull else -10 if ha_bear else 0) +
        (5  if kalman_accel_up else -5 if kalman_accel_down else 0) +
        (5  if tend_consistente_bull else -5 if tend_consistente_bear else 0) +
        (10 if trendilo_long else -10 if trendilo_short else 0)
    )
    score = max(-145, min(145, score))

    # Score institucional 0-100
    def _score_inst(htf_ok, adx_ok, flow, ha, trl, rsi_ok, v_s, div, sm):
        return max(0, min(100,
            (20 if htf_ok else 0) + (15 if adx_ok else 0) + (15 if flow else 0) +
            (10 if ha else 0) + (10 if trl else 0) + (10 if rsi_ok else 0) +
            (10 if v_s else 0) + (5 if div else 0) + (5 if sm else 0)
        ))

    score_inst_long  = _score_inst(tendencia_bull, adx_long_ok,
                                   dna_flow_bull or (f_bull and pressao_bull),
                                   ha_bull, trendilo_long, rsi_subindo,
                                   v_forte, rsi_div_bull, sm_bull)
    score_inst_short = _score_inst(tendencia_bear, adx_short_ok,
                                   dna_flow_bear or (f_bear and pressao_bear),
                                   ha_bear, trendilo_short, rsi_caindo,
                                   v_forte, rsi_div_bear, sm_bear)

    def _cls_inst(s):
        return "ELITE" if s >= 85 else "FORTE" if s >= 70 else "MÉDIO" if s >= 55 else "FRACO"

    return {
        # Preço e estrutura
        "preco": preco, "atr": atr, "score": score, "rsi": rsi, "adx": adx,
        "swing_low": swing_low, "swing_high": swing_high,
        # Tendência
        "tendencia_bull": tendencia_bull, "tendencia_bear": tendencia_bear,
        "alinhado_bull": alinhado_bull, "alinhado_bear": alinhado_bear,
        "e200_subindo": e200_subindo, "e200_descendo": e200_descendo,
        "tendencia_forte": tendencia_forte, "tendencia_str": "ALTA" if tendencia_bull else "BAIXA" if tendencia_bear else "NEUTRO",
        "tbull_r": tbull_r, "tbear_r": tbear_r, "tbull_loose": tbull_loose, "tbear_loose": tbear_loose,
        "tend_consistente_bull": tend_consistente_bull, "tend_consistente_bear": tend_consistente_bear,
        # EMAs
        "e10": e10, "e21": e21, "e50": e50, "e200": e200,
        "e10_arr": e10_arr, "e21_arr": e21_arr,
        # Kalman
        "kalman_subindo": kalman_subindo, "kalman_descendo": kalman_descendo,
        "kalman_accel_up": kalman_accel_up, "kalman_accel_down": kalman_accel_down,
        "k_short_subindo": k_short_subindo, "k_short_descendo": k_short_descendo,
        # MACD
        "ml": ml, "sl_v": sl_v, "hist": hist, "hist_p": hist_p,
        "macd_bull": macd_bull, "macd_bear": macd_bear,
        "macd_bull3": macd_bull3, "macd_bear3": macd_bear3,
        "macd_bull_r": macd_bull_r, "macd_bear_r": macd_bear_r,
        "macd_recuperando": macd_recuperando, "macd_esgotando": macd_esgotando,
        "exaustao_venda": exaustao_venda, "exaustao_compra": exaustao_compra,
        # RSI
        "rsi_ant": rsi_ant, "rsi_subindo": rsi_subindo, "rsi_caindo": rsi_caindo,
        "rsi_bull": rsi_bull, "rsi_bear": rsi_bear,
        "rsi_bull_elite": rsi_bull_elite, "rsi_bear_elite": rsi_bear_elite,
        "rsi_div_bull": rsi_div_bull, "rsi_div_bear": rsi_div_bear,
        "rsi_dip_short": rsi_dip_short, "rsi_rebound_short": rsi_rebound_short,
        "rsi_spike_long": rsi_spike_long, "rsi_rebound_long": rsi_rebound_long,
        "stoch_rsi": stoch_rsi, "stoch_esticado_up": stoch_esticado_up, "stoch_esticado_down": stoch_esticado_down,
        "rsi_nao_chasing_long": rsi_nao_chasing_long, "rsi_nao_chasing_short": rsi_nao_chasing_short,
        "rsi_zona_long": rsi_zona_long, "rsi_zona_short": rsi_zona_short,
        "rsi_entrada_long": rsi_entrada_long, "rsi_entrada_short": rsi_entrada_short,
        # ADX
        "pdi": pdi, "mdi": mdi, "adx_long_ok": adx_long_ok, "adx_short_ok": adx_short_ok,
        "adx_p": adx_p, "adx_subindo": adx > adx_p,
        # Volume
        "rvol": rvol, "rvol_tier": rvol_tier, "rvol_tier_max2": rvol_tier_max2, "rvol_label": rvol_label,
        "v_bom": v_bom, "v_forte": v_forte, "v_inst": v_inst, "v_forte2": v_forte2,
        "vol_ma": vol_ma, "volumes": volumes, "vol_nao_fade": vol_nao_fade,
        "flex_vol_ok": flex_vol_ok, "flex_vol_ok_s": flex_vol_ok_s,
        # Flow
        "f_bull": f_bull, "f_bear": f_bear, "f_forte": f_forte,
        "dna_flow_bull": dna_flow_bull, "dna_flow_bear": dna_flow_bear,
        "dna_flex_bull": dna_flex_bull, "dna_flex_bear": dna_flex_bear,
        # HA
        "ha_bull": ha_bull, "ha_bear": ha_bear, "ha_bull3": ha_bull3, "ha_bear3": ha_bear3,
        "ha_bull2": ha_bull2, "ha_bear2": ha_bear2, "ha_corpo_ok": ha_corpo_ok,
        "ha_bull_1": ha_bull_1, "ha_bear_1": ha_bear_1,
        # OBV / VWAP
        "obv_bull": obv_bull, "obv_bear": obv_bear,
        "acima_vwap": acima_vwap, "abaixo_vwap": abaixo_vwap,
        # BB
        "bb_sup": bb_sup, "bb_inf": bb_inf, "bb_bw": bb_bw, "bb_bw_p": bb_bw_p,
        "bb_squeeze": bb_squeeze, "bb_expand": bb_expand,
        "bb_break_long": bb_break_long, "bb_break_short": bb_break_short,
        # Padrões
        "e200_inclinada_up": e200_inclinada_up, "e200_inclinada_down": e200_inclinada_down,
        "reteste_mm50_bull": reteste_mm50_bull, "reteste_mm50_bear": reteste_mm50_bear,
        "correcao_bull": correcao_bull, "correcao_bear": correcao_bear,
        "pullback_bull": pullback_bull, "pullback_bear": pullback_bear,
        "impulso_bull": impulso_bull, "impulso_bear": impulso_bear,
        "liq_long": liq_long, "liq_short": liq_short,
        "liq_topo": liq_topo, "liq_fundo": liq_fundo,
        "sombra_sup": sombra_sup, "sombra_inf": sombra_inf,
        "sm_bull": sm_bull, "sm_bear": sm_bear,
        "absorb_bull": absorb_bull, "absorb_bear": absorb_bear,
        "exaustao_topo": exaustao_topo, "exaustao_fund": exaustao_fund,
        "nao_ext_long": nao_ext_long, "nao_ext_short": nao_ext_short,
        "nao_ext_long_tight": nao_ext_long_tight, "nao_ext_short_tight": nao_ext_short_tight,
        "nao_overext_long": nao_overext_long, "nao_overext_short": nao_overext_short,
        # Cruzamentos
        "algum_cross_bull": algum_cross_bull, "algum_cross_bear": algum_cross_bear,
        "label_cross": label_cross,
        # Trendilo
        "trendilo_long": trendilo_long, "trendilo_short": trendilo_short,
        # Filtros compostos
        "seguro_long": seguro_long, "seguro_short": seguro_short,
        "perto_bb_topo": perto_bb_topo, "perto_bb_fund": perto_bb_fund,
        "ext_acima_e21": ext_acima_e21, "ext_abaixo_e21": ext_abaixo_e21,
        "vol_secando": vol_secando,
        "lateralizado": lateralizado,
        # Surge
        "candle_bull_pct": candle_bull_pct, "candle_bear_pct": candle_bear_pct,
        "surge_break_h": surge_break_h, "surge_break_l": surge_break_l,
        # Institucional
        "score_inst_long": score_inst_long, "score_inst_short": score_inst_short,
        "cls_inst_long": _cls_inst(score_inst_long), "cls_inst_short": _cls_inst(score_inst_short),
        # Candles originais (para maximas/minimas nos sinais)
        "_maximas": maximas, "_minimas": minimas, "_fechamentos": fechamentos, "_aberturas": aberturas,
    }


# ══════════════════════════════════════════════════════════════════════════════
# ETAPA 2 — DETECTAR SINAIS
# ══════════════════════════════════════════════════════════════════════════════

def detectar_sinais(ind):
    """Aplica toda a lógica de sinais sobre os indicadores calculados. Retorna (sinal, fonte)."""
    i = ind  # alias curto

    # ── ELITE ────────────────────────────────────────────────────────────────
    long_elite = (i["tendencia_forte"] and i["tendencia_bull"] and i["alinhado_bull"] and
                  i["e200_subindo"] and i["macd_bull3"] and i["ha_bull3"] and
                  i["f_bull"] and i["f_forte"] and i["adx_long_ok"] and
                  i["rsi_bull_elite"] and (i["v_forte2"] or i["obv_bull"]) and i["nao_ext_long"] and
                  i["kalman_accel_up"] and i["acima_vwap"] and i["tend_consistente_bull"] and
                  (i["impulso_bull"] or i["liq_long"]) and i["score"] > 65 and i["seguro_long"])

    short_elite = (i["tendencia_forte"] and i["tendencia_bear"] and i["alinhado_bear"] and
                   i["e200_descendo"] and i["macd_bear3"] and i["ha_bear3"] and
                   i["f_bear"] and i["f_forte"] and i["adx_short_ok"] and
                   i["rsi_bear_elite"] and (i["v_forte2"] or i["obv_bear"]) and i["nao_ext_short"] and
                   i["kalman_accel_down"] and i["abaixo_vwap"] and i["tend_consistente_bear"] and
                   (i["impulso_bear"] or i["liq_short"]) and i["score"] < -65 and i["seguro_short"])

    early_long  = (i["adx_long_ok"] and (i["v_forte"] or i["obv_bull"]) and i["exaustao_venda"] and
                   i["liq_long"] and i["absorb_bull"] and i["f_bull"] and i["tendencia_bull"] and
                   i["e200_subindo"] and i["kalman_subindo"] and i["acima_vwap"] and
                   i["macd_recuperando"] and i["seguro_long"])

    early_short = (i["adx_short_ok"] and (i["v_forte"] or i["obv_bear"]) and i["exaustao_compra"] and
                   i["liq_short"] and i["absorb_bear"] and i["f_bear"] and i["tendencia_bear"] and
                   i["e200_descendo"] and i["kalman_descendo"] and i["abaixo_vwap"] and
                   i["macd_esgotando"] and i["seguro_short"])

    # ── FLEX — pullback ───────────────────────────────────────────────────────
    tbull_r = i["tbull_r"]; tbear_r = i["tbear_r"]
    long_pullback  = (i["pullback_bull"] and tbull_r and i["preco"] < i["e21"] * 1.03 and
                      i["dna_flow_bull"] and i["adx"] > 18 and i["pdi"] > i["mdi"] and
                      i["rsi_zona_long"] and i["score_inst_long"] >= 50 and
                      i["seguro_long"] and i["trendilo_long"] and not i["liq_topo"])
    short_pullback = (i["pullback_bear"] and tbear_r and i["preco"] > i["e21"] * 0.97 and
                      i["dna_flow_bear"] and i["adx"] > 18 and i["mdi"] > i["pdi"] and
                      i["rsi_zona_short"] and i["score_inst_short"] >= 50 and
                      i["seguro_short"] and i["trendilo_short"] and not i["liq_fundo"])

    # ── Cross ─────────────────────────────────────────────────────────────────
    long_cross  = (i["algum_cross_bull"] and i["dna_flow_bull"] and i["adx_long_ok"] and
                   i["preco"] > i["e200"] and i["score_inst_long"] >= 50 and i["rsi_zona_long"] and
                   i["rsi_entrada_long"] and i["rsi_subindo"] and i["tbull_loose"] and
                   i["seguro_long"] and (i["trendilo_long"] or i["kalman_subindo"]))
    short_cross = (i["algum_cross_bear"] and i["dna_flow_bear"] and i["adx_short_ok"] and
                   i["preco"] < i["e200"] and i["score_inst_short"] >= 50 and i["rsi_zona_short"] and
                   i["rsi_entrada_short"] and i["rsi_caindo"] and i["tbear_loose"] and
                   i["seguro_short"] and (i["trendilo_short"] or not i["kalman_subindo"]))

    # ── Variáveis de nível de filtro (usadas em BB_BREAK e SCOUT) ────────────
    _fluxo_min   = 0 if _FLV <= 0 else (1 if _FLV == 1 else 2)
    _adx_sub_ok  = i["adx_subindo"] if _FLV >= 2 else True
    _no_liq_topo = (not i["liq_topo"])  if _FLV >= 3 else True
    _no_liq_fund = (not i["liq_fundo"]) if _FLV >= 3 else True

    # ── BB Breakout ───────────────────────────────────────────────────────────
    _rvol_bb      = 0.50 if _FLV <= 1 else (0.65 if _FLV == 2 else 0.80)
    long_bb_break  = (i["bb_break_long"] and i["bb_expand"] and i["kalman_subindo"] and
                      i["k_short_subindo"] and i["score"] > 40 and i["adx"] >= 15 and
                      _adx_sub_ok and not i["lateralizado"] and not i["ext_acima_e21"] and
                      i["obv_bull"] and _no_liq_topo and
                      i["rvol"] >= _rvol_bb and i["rsi_zona_long"] and i["score_inst_long"] >= 50)
    short_bb_break = (i["bb_break_short"] and i["bb_expand"] and i["kalman_descendo"] and
                      i["k_short_descendo"] and i["score"] < -40 and i["adx"] >= 15 and
                      _adx_sub_ok and not i["lateralizado"] and not i["ext_abaixo_e21"] and
                      i["obv_bear"] and _no_liq_fund and
                      i["rvol"] >= _rvol_bb and i["rsi_zona_short"] and i["score_inst_short"] >= 50)

    # ── Smart Money ───────────────────────────────────────────────────────────
    long_sm  = (i["sm_bull"] and i["rsi"] > 25 and i["rsi_zona_long"] and
                i["preco"] > i["e200"] and i["score_inst_long"] >= 60)
    short_sm = (i["sm_bear"] and i["rsi_zona_short"] and i["rsi"] < 75 and
                i["preco"] < i["e200"] and i["score_inst_short"] >= 60)

    # ── Reversão extrema ──────────────────────────────────────────────────────
    long_reversal  = (i["rsi"] < 30 and i["ha_bull"] and i["v_forte"] and
                      (i["liq_fundo"] or i["absorb_bull"]) and i["macd_recuperando"] and
                      i["adx"] > 12 and i["preco"] > i["e200"] * 0.96 and
                      (i["dna_flow_bull"] or i["obv_bull"]))
    short_reversal = (i["rsi"] > 70 and i["ha_bear"] and i["v_forte"] and
                      (i["liq_topo"] or i["absorb_bear"]) and i["macd_esgotando"] and
                      i["adx"] > 12 and i["preco"] < i["e200"] * 1.04 and
                      (i["dna_flow_bear"] or i["obv_bear"]))

    # ── Surge ─────────────────────────────────────────────────────────────────
    # SURGE — breakout/breakdown explosivo com volume VSTRONG (3x+)
    # surge_break_h/l JÁ implica liq_topo/fundo (rompe máxima/mínima recente),
    # por isso não usar not liq_topo/fundo aqui — seria contradição direta.
    # Usa melhor das 2 últimas velas p/ RVOL (pega sinal da vela anterior).
    _surge_vol_ok  = i["rvol_tier_max2"] >= 3
    long_surge  = (_surge_vol_ok and i["candle_bull_pct"] > 0.03 and i["surge_break_h"] and
                   not i["exaustao_topo"] and (i["kalman_subindo"] or i["k_short_subindo"]) and i["ha_bull"] and
                   i["rsi"] < 78 and i["score_inst_long"] >= 50 and
                   i["preco"] > i["e50"] and i["preco"] > i["e200"])
    short_surge = (_surge_vol_ok and i["candle_bear_pct"] > 0.03 and i["surge_break_l"] and
                   not i["exaustao_fund"] and (i["kalman_descendo"] or i["k_short_descendo"]) and i["ha_bear"] and
                   i["rsi"] > 22 and i["score_inst_short"] >= 50 and
                   i["preco"] < i["e50"] and i["preco"] < i["e200"])

    # ── Momentum RSI ──────────────────────────────────────────────────────────
    rsi_fresh_long  = i["rsi_ant"] < 65 <= i["rsi"] < 73
    rsi_fresh_short = i["rsi_ant"] > 42 >= i["rsi"] > 30
    # Exaustão de curtíssimo prazo (sem checagem de teto de RSI — o MOMENTUM entra
    # propositalmente na faixa 65-73, então só barra se já estiver esticado/exausto)
    mom_seguro_long  = (not i["perto_bb_topo"] and not i["ext_acima_e21"] and not i["vol_secando"] and
                        not i["exaustao_topo"] and not i["stoch_esticado_up"])
    mom_seguro_short = (not i["perto_bb_fund"] and not i["ext_abaixo_e21"] and not i["vol_secando"] and
                        not i["exaustao_fund"] and not i["stoch_esticado_down"])
    long_momentum  = (rsi_fresh_long  and i["ha_bull"] and i["dna_flow_bull"] and not i["liq_topo"] and
                      i["adx"] > 22 and i["v_forte"] and i["trendilo_long"]  and i["score_inst_long"]  >= 60 and
                      mom_seguro_long)
    short_momentum = (rsi_fresh_short and i["ha_bear"] and i["dna_flow_bear"] and not i["liq_fundo"] and
                      i["adx"] > 22 and i["v_forte"] and i["trendilo_short"] and i["score_inst_short"] >= 60 and
                      mom_seguro_short)

    # ── Rebound RSI ───────────────────────────────────────────────────────────
    long_rebound  = (i["rsi_spike_long"]  and i["rsi_rebound_long"]  and i["ha_bull"] and
                     i["dna_flow_bull"] and i["trendilo_long"]  and i["adx"] > 20 and
                     i["v_bom"] and i["kalman_subindo"]  and not i["lateralizado"] and
                     i["seguro_long"]  and i["nao_ext_long_tight"])
    short_rebound = (i["rsi_dip_short"]   and i["rsi_rebound_short"] and i["ha_bear"] and
                     i["dna_flow_bear"] and i["trendilo_short"] and i["adx"] > 20 and
                     i["v_bom"] and not i["kalman_subindo"] and not i["lateralizado"] and
                     i["seguro_short"] and (i["e21"] - i["preco"]) / i["atr"] < 2.5)

    # ── Divergência RSI ───────────────────────────────────────────────────────
    # Sem piso de ADX nem checagem de lateralização, "divergência" é só ruído de
    # RSI oscilando num range — por isso exige tendência mínima e mercado fora de squeeze
    long_div  = (i["rsi_div_bull"] and i["ha_bull"] and i["v_bom"] and
                 i["rsi"] > 25 and i["rsi_zona_long"] and not i["exaustao_topo"] and
                 i["adx"] > 15 and not i["lateralizado"] and i["preco"] > i["e200"] and
                 i["score_inst_long"] >= 55)
    short_div = (i["rsi_div_bear"] and i["ha_bear"] and i["v_bom"] and
                 i["rsi_zona_short"] and i["rsi"] < 70 and i["preco"] < i["e200"] and
                 not i["exaustao_fund"] and i["adx"] > 15 and not i["lateralizado"] and
                 i["score_inst_short"] >= 55)

    # ── FLEX geral ────────────────────────────────────────────────────────────
    long_flex  = (i["score"] >= 40 and i["ha_bull2"] and i["macd_bull_r"] and i["adx"] >= 14 and
                  not i["lateralizado"] and i["nao_ext_long_tight"] and i["seguro_long"] and
                  i["flex_vol_ok"] and i["rvol"] >= 1.0 and i["rsi_zona_long"] and i["rsi_entrada_long"] and
                  i["rsi_subindo"] and i["tbull_loose"] and i["nao_overext_long"] and i["rsi_nao_chasing_long"] and
                  i["preco"] > i["e200"] and i["score_inst_long"] >= 50 and
                  (i["liq_long"] or i["liq_fundo"] or (i["trendilo_long"] and i["kalman_subindo"])) and
                  (i["trendilo_long"] or i["kalman_subindo"] or i["dna_flex_bull"]))
    short_flex = (i["score"] <= -40 and i["ha_bear2"] and i["macd_bear_r"] and i["adx"] >= 14 and
                  not i["lateralizado"] and i["nao_ext_short_tight"] and i["seguro_short"] and
                  i["flex_vol_ok_s"] and i["rvol"] >= 1.0 and i["rsi_zona_short"] and i["rsi_entrada_short"] and
                  i["rsi_caindo"] and i["tbear_loose"] and i["nao_overext_short"] and i["rsi_nao_chasing_short"] and
                  i["preco"] < i["e200"] and i["score_inst_short"] >= 50 and
                  (i["liq_short"] or i["liq_topo"] or (i["trendilo_short"] and not i["kalman_subindo"])) and
                  (i["trendilo_short"] or not i["kalman_subindo"] or i["dna_flex_bear"]))

    # ── Setup (acumulação antecipada) ─────────────────────────────────────────
    long_setup  = (i["score"] > 50 and i["ha_bull2"] and i["macd_recuperando"] and i["adx"] > 18 and
                   i["obv_bull"] and i["v_bom"] and i["acima_vwap"] and not i["lateralizado"] and
                   i["nao_ext_long_tight"] and i["seguro_long"] and (i["liq_long"] or i["liq_fundo"]) and
                   i["preco"] > i["e200"] and i["score_inst_long"] >= 50 and i["rsi_zona_long"])
    short_setup = (i["score"] < -50 and i["ha_bear2"] and i["macd_esgotando"] and i["adx"] > 18 and
                   i["obv_bear"] and i["v_bom"] and i["abaixo_vwap"] and not i["lateralizado"] and
                   i["nao_ext_short_tight"] and i["seguro_short"] and (i["liq_short"] or i["liq_topo"]) and
                   i["preco"] < i["e200"] and i["score_inst_short"] >= 50 and i["rsi_zona_short"])

    # ── Scout (sinal secundário) ──────────────────────────────────────────────
    # ADX >= 20: notify.py já comprime alvos 35% abaixo de 20 — entrar sem tendência = stop certo
    _sc_min  = 25 if _FLV <= 0 else 30
    _adx_min = 10 if _FLV <= 0 else 18
    _seg_l   = i["seguro_long"]  if _FLV >= 1 else True
    _seg_s   = i["seguro_short"] if _FLV >= 1 else True
    # vol: vol_nao_fade + RVOL>=0.5 (pico isolado sem volume sustentado não garante TP1)
    # fallback com OBV/Kalman+Trendilo dispensa o piso de RVOL (confirmação independente)
    _vol_scout_l = ((i["vol_nao_fade"] and i["rvol"] >= 0.5) or
                    (i["obv_bull"] and (i["trendilo_long"] or i["kalman_subindo"])) or
                    (i["kalman_subindo"] and i["trendilo_long"]) or
                    (i["obv_bull"] and i["rsi_subindo"]))
    _vol_scout_s = ((i["vol_nao_fade"] and i["rvol"] >= 0.5) or
                    (i["obv_bear"] and (i["trendilo_short"] or i["kalman_descendo"])) or
                    (i["kalman_descendo"] and i["trendilo_short"]) or
                    (i["obv_bear"] and i["rsi_caindo"]))
    # MACD: ao nível FL<=1 é bypassado por qualquer confirmador de fluxo (>= 1)
    # score_inst >= 55 é a guarda de qualidade — MACD sozinho era double-filter redundante
    _fluxo_l = sum([i["dna_flow_bull"], i["f_bull"], i["trendilo_long"], i["kalman_subindo"]])
    _fluxo_s = sum([i["dna_flow_bear"], i["f_bear"], i["trendilo_short"], not i["kalman_subindo"]])
    _macd_l = i["macd_bull_r"] if _FLV >= 2 else (i["macd_bull_r"] or _fluxo_l >= 1)
    _macd_s = i["macd_bear_r"] if _FLV >= 2 else (i["macd_bear_r"] or _fluxo_s >= 1)
    long_scout  = (i["score"] >= _sc_min and i["ha_bull_1"] and _macd_l and i["adx"] >= _adx_min and
                   _adx_sub_ok and not i["lateralizado"] and i["nao_ext_long_tight"] and
                   _seg_l and _vol_scout_l and i["rvol"] >= 1.0 and i["nao_overext_long"] and
                   i["rsi_nao_chasing_long"] and i["rsi_zona_long"] and i["rsi_entrada_long"] and
                   i["rsi_subindo"] and i["tbull_loose"] and i["preco"] > i["e200"] and
                   _no_liq_topo and _fluxo_l >= _fluxo_min)
    short_scout = (i["score"] <= -_sc_min and i["ha_bear_1"] and _macd_s and i["adx"] >= _adx_min and
                   _adx_sub_ok and not i["lateralizado"] and i["nao_ext_short_tight"] and
                   _seg_s and _vol_scout_s and i["rvol"] >= 1.0 and i["nao_overext_short"] and
                   i["rsi_nao_chasing_short"] and i["rsi_zona_short"] and i["rsi_entrada_short"] and
                   i["rsi_caindo"] and i["tbear_loose"] and i["preco"] < i["e200"] and
                   _no_liq_fund and _fluxo_s >= _fluxo_min)

    # ── Prioridade de sinais ──────────────────────────────────────────────────
    sinal = None; fonte = ""
    if SIGNAL_MODE == "ELITE":
        if long_elite or early_long:   sinal = "LONG";  fonte = "ELITE"
        elif short_elite or early_short: sinal = "SHORT"; fonte = "ELITE"
    else:
        ordem = [
            (long_pullback,  "LONG",  "PULLBACK"),
            (short_pullback, "SHORT", "PULLBACK"),
            (long_cross,     "LONG",  f"CROSS:{i['label_cross']}"),
            (short_cross,    "SHORT", f"CROSS:{i['label_cross']}"),
            (long_bb_break,  "LONG",  "BB_BREAK"),
            (short_bb_break, "SHORT", "BB_BREAK"),
            (long_sm,        "LONG",  "SM_SWEEP"),
            (short_sm,       "SHORT", "SM_SWEEP"),
            (long_reversal,  "LONG",  "REVERSAL"),
            (short_reversal, "SHORT", "REVERSAL"),
            (long_surge,     "LONG",  "SURGE"),
            (short_surge,    "SHORT", "SURGE"),
            (long_momentum,  "LONG",  "MOMENTUM"),
            (short_momentum, "SHORT", "MOMENTUM"),
            (long_rebound,   "LONG",  "REBOUND"),
            (short_rebound,  "SHORT", "REBOUND"),
            (long_div,       "LONG",  "DIV"),
            (short_div,      "SHORT", "DIV"),
            (long_flex,      "LONG",  "FLEX"),
            (short_flex,     "SHORT", "FLEX"),
            (long_setup,     "LONG",  "SETUP"),
            (short_setup,    "SHORT", "SETUP"),
            (long_scout,     "LONG",  "SCOUT"),
            (short_scout,    "SHORT", "SCOUT"),
        ]
        for condição, dir_, src in ordem:
            if condição:
                sinal = dir_; fonte = src; break

    return sinal, fonte


# ══════════════════════════════════════════════════════════════════════════════
# ETAPA 3 — GRADUAR QUALIDADE
# ══════════════════════════════════════════════════════════════════════════════

def graduar_sinal(ind, sinal):
    """Conta fatores premium alinhados e retorna grade S / A / B."""
    if not sinal:
        return "B", 0
    i = ind
    pts = 0
    if sinal == "LONG":
        pts += 3 if i["tendencia_bull"]       else 0
        pts += 2 if i["alinhado_bull"]         else 0
        pts += 2 if i["macd_bull3"] else (1 if i["macd_bull"] else 0)
        pts += 2 if i["ha_bull"]               else 0
        pts += 2 if i["adx_long_ok"] else (1 if i["adx"] > 15 else 0)
        pts += 1 if i["obv_bull"]              else 0
        pts += 1 if i["acima_vwap"]            else 0
        pts += 1 if i["v_forte"]               else 0
        pts += 1 if i["kalman_accel_up"]       else 0
        pts += 1 if i["e200_subindo"]          else 0
        pts += 1 if i["f_forte"]               else 0
        pts += 1 if i["tend_consistente_bull"] else 0
    else:
        pts += 3 if i["tendencia_bear"]        else 0
        pts += 2 if i["alinhado_bear"]         else 0
        pts += 2 if i["macd_bear3"] else (1 if i["macd_bear"] else 0)
        pts += 2 if i["ha_bear"]               else 0
        pts += 2 if i["adx_short_ok"] else (1 if i["adx"] > 15 else 0)
        pts += 1 if i["obv_bear"]              else 0
        pts += 1 if i["abaixo_vwap"]           else 0
        pts += 1 if i["v_forte"]               else 0
        pts += 1 if i["kalman_accel_down"]     else 0
        pts += 1 if i["e200_descendo"]         else 0
        pts += 1 if i["f_forte"]               else 0
        pts += 1 if i["tend_consistente_bear"] else 0

    if pts >= 17:   grade = "S+"
    elif pts >= 14: grade = "S"
    elif pts >= 13: grade = "A+"
    elif pts >= 11: grade = "A"
    else:           grade = "B"

    # Trava S/S+: requer inst >= 70 e RSI não esticado
    if grade in ("S", "S+"):
        score_inst = i["score_inst_long"] if sinal == "LONG" else i["score_inst_short"]
        rsi_esticado = (sinal == "LONG" and i["rsi"] > 65) or (sinal == "SHORT" and i["rsi"] < 35)
        if score_inst < 70 or rsi_esticado:
            grade = "A+" if pts >= 13 else "A"

    # Trava A+: requer inst >= 60 (MÉDIO confirmado)
    if grade == "A+":
        score_inst = i["score_inst_long"] if sinal == "LONG" else i["score_inst_short"]
        if score_inst < 60:
            grade = "A"

    return grade, pts


# ══════════════════════════════════════════════════════════════════════════════
# FUNÇÃO PÚBLICA — ponto de entrada
# ══════════════════════════════════════════════════════════════════════════════

def analisar(simbolo, candles, funding_rate=None):
    """
    Analisa um ativo e retorna dict com sinal, fonte, grade e todos os indicadores.
    Retorna None se não houver candles suficientes.
    """
    ind = calcular_indicadores(candles)
    if ind is None:
        return None

    sinal, fonte = detectar_sinais(ind)
    grade, pts   = graduar_sinal(ind, sinal)

    # Log de diagnóstico quando há score mas sem sinal
    if not sinal:
        sc = ind["score"]
        if sc > 25:
            b = []
            if not ind["macd_bull_r"]:  b.append("macd_r=F")
            if not ind["ha_bull_1"]:    b.append("ha1=F")
            if ind["adx"] < 15:         b.append(f"adx={ind['adx']:.1f}<15")
            if ind["lateralizado"]:     b.append("lateral")
            if not ind["seguro_long"]:
                _sg = []
                if ind["perto_bb_topo"]:       _sg.append("bb_topo")
                if ind["ext_acima_e21"]:        _sg.append("ext_e21")
                if ind["vol_secando"]:          _sg.append("vol_sec")
                if ind.get("exaustao_topo"):    _sg.append("exaustao")
                if ind["rsi"] >= 70:            _sg.append(f"rsi={ind['rsi']:.0f}")
                if ind["stoch_esticado_up"]:    _sg.append(f"stoch={ind['stoch_rsi']:.2f}")
                b.append(f"seguro=F({','.join(_sg) or '?'})")
            if ind["rvol"] < 1.0:           b.append(f"rvol_scout=F({ind['rvol']:.2f}x<1.0)")
            if not ind["rsi_zona_long"]:   b.append(f"rsi_zona=F(rsi={ind['rsi']:.0f})")
            if not ind["rsi_entrada_long"]: b.append(f"rsi_entrada=F(rsi={ind['rsi']:.0f}<45)")
            if not ind["rsi_subindo"]:      b.append(f"rsi_dir=F(caindo,rsi={ind['rsi']:.0f}<ant={ind['rsi_ant']:.0f})")
            if not ind["tbull_loose"]:      b.append("tend=F(EMA nao alinhada)")
            if ind["preco"] <= ind["e200"]: b.append(f"e200=F(preco abaixo)")
            fluxo = sum([ind["dna_flow_bull"], ind["f_bull"], ind["trendilo_long"], ind["kalman_subindo"]])
            if fluxo < 2:               b.append(f"fluxo={fluxo}/4")
            log.info(f"  LONG-BLOQ {simbolo}: score={sc:+d} | {'; '.join(b) or 'sem detalhe'}")
        elif sc < -25:
            b = []
            if not ind["macd_bear_r"]:   b.append("macd_r=F")
            if not ind["ha_bear_1"]:     b.append("ha1=F")
            if ind["adx"] < 15:          b.append(f"adx={ind['adx']:.1f}<15")
            if ind["lateralizado"]:      b.append("lateral")
            if not ind["seguro_short"]:
                _sg = []
                if ind["vol_secando"]:          _sg.append("vol_sec")
                if ind.get("exaustao_fund"):     _sg.append("exaustao")
                if ind["rsi"] <= 27:            _sg.append(f"rsi={ind['rsi']:.0f}")
                if ind["stoch_esticado_down"]:  _sg.append(f"stoch={ind['stoch_rsi']:.2f}")
                b.append(f"seguro=F({','.join(_sg) or '?'})")
            if ind["rvol"] < 1.0:            b.append(f"rvol_scout=F({ind['rvol']:.2f}x<1.0)")
            if not ind["rsi_zona_short"]:    b.append(f"rsi_zona=F(rsi={ind['rsi']:.0f})")
            if not ind["rsi_entrada_short"]: b.append(f"rsi_entrada=F(rsi={ind['rsi']:.0f}>55)")
            if not ind["rsi_caindo"]:        b.append(f"rsi_dir=F(subindo,rsi={ind['rsi']:.0f}>ant={ind['rsi_ant']:.0f})")
            if not ind["tbear_loose"]:       b.append("tend=F(EMA nao alinhada)")
            if ind["preco"] >= ind["e200"]: b.append(f"e200=F(preco acima)")
            fluxo = sum([ind["dna_flow_bear"], ind["f_bear"], ind["trendilo_short"], not ind["kalman_subindo"]])
            if fluxo < 2:                b.append(f"fluxo={fluxo}/4")
            log.info(f"  SHORT-BLOQ {simbolo}: score={sc:+d} | {'; '.join(b) or 'sem detalhe'}")
        else:
            log.info(f"  sem-sinal {simbolo}: score={sc:+d} insuficiente")

    return {
        "preco":        ind["preco"],
        "score":        ind["score"],
        "atr":          ind["atr"],
        "rsi":          ind["rsi"],
        "adx":          ind["adx"],
        "kalman_subindo": ind["kalman_subindo"],
        "tendencia":    ind["tendencia_str"],
        "sinal":        sinal,
        "fonte_sinal":  fonte,
        "swing_low":    ind["swing_low"],
        "swing_high":   ind["swing_high"],
        "grade":        grade,
        "pts_grade":    pts,
        # Indicadores para ciclo e envio
        "ha_bull":      ind["ha_bull"],
        "obv_bull":     ind["obv_bull"],
        "acima_vwap":   ind["acima_vwap"],
        "v_forte":      ind["v_forte"],
        "obv_bear":     ind["obv_bear"],
        "rvol":         ind["rvol"],
        "rvol_label":   ind["rvol_label"],
        "rvol_tier":    ind["rvol_tier"],
        "tbull_r":      ind["tbull_r"],
        "tbear_r":      ind["tbear_r"],
        "tbull_loose":  ind["tbull_loose"],
        "tbear_loose":  ind["tbear_loose"],
        "bb_break_long":  ind["bb_break_long"],
        "bb_break_short": ind["bb_break_short"],
        "score_inst_long":  ind["score_inst_long"],
        "score_inst_short": ind["score_inst_short"],
        "cls_inst_long":    ind["cls_inst_long"],
        "cls_inst_short":   ind["cls_inst_short"],
        "liq_fundo":    ind["liq_fundo"],
        "liq_topo":     ind["liq_topo"],
        "sombra_sup":   ind["sombra_sup"],
        "sombra_inf":   ind["sombra_inf"],
        "dna_flow_bull": ind["dna_flow_bull"],
        "dna_flow_bear": ind["dna_flow_bear"],
        "dna_flex_bull": ind["dna_flex_bull"],
        "dna_flex_bear": ind["dna_flex_bear"],
        "trendilo_long":  ind["trendilo_long"],
        "trendilo_short": ind["trendilo_short"],
        "funding_rate":   funding_rate,
    }
