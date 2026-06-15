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
    aberturas_reais  = [c["o"] for c in candles]
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

    # Heikin-Ashi: corpo mínimo (0.2 ATR) filtra dojis
    ha_corpo_ok = abs(fechamentos[-1] - aberturas[-1]) > atr * 0.2
    ha_bull  = fechamentos[-1] > aberturas[-1] and fechamentos[-2] > aberturas[-2] and ha_corpo_ok
    ha_bear  = fechamentos[-1] < aberturas[-1] and fechamentos[-2] < aberturas[-2] and ha_corpo_ok
    ha_bull3 = ha_bull and fechamentos[-3] > aberturas[-3]
    ha_bear3 = ha_bear and fechamentos[-3] < aberturas[-3]
    ha_bull2 = ha_bull and ha_corpo_ok
    ha_bear2 = ha_bear and ha_corpo_ok
    # Versão mais permissiva: apenas a última vela HA precisa ser bullish/bearish
    # Usa threshold menor (0.1 ATR) pois 1-vela já é mais restritiva por exigir direção
    _ha_c1    = abs(fechamentos[-1] - aberturas[-1]) > atr * 0.1
    ha_bull_1 = fechamentos[-1] > aberturas[-1] and _ha_c1
    ha_bear_1 = fechamentos[-1] < aberturas[-1] and _ha_c1

    # RSI
    rsi       = calcular_rsi(fechamentos[-50:])
    rsi_ant   = calcular_rsi(fechamentos[-53:-3]) if n >= 53 else rsi
    rsi_6     = calcular_rsi(fechamentos[-56:-6]) if n >= 56 else rsi
    rsi_9     = calcular_rsi(fechamentos[-59:-9]) if n >= 59 else rsi
    rsi_subindo  = rsi > rsi_ant + 0.3   # delta mínimo 0.3 para evitar falso-positivo float
    rsi_caindo   = rsi < rsi_ant - 0.3

    rsi_dip_short      = rsi_ant < 35 or rsi_6 < 35 or rsi_9 < 35
    rsi_rebound_short  = 38 <= rsi <= 46 and rsi > rsi_ant
    rsi_spike_long     = rsi_ant > 65 or rsi_6 > 65 or rsi_9 > 65
    rsi_rebound_long   = 54 <= rsi <= 62 and rsi < rsi_ant

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
    stoch_esticado_up   = stoch_rsi > 0.80 and rsi > 58   # só bloqueia LONG quando RSI também está elevado
    stoch_esticado_down = stoch_rsi < 0.05 and rsi < 42   # só bloqueia SHORT quando RSI também está deprimido

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
    vol3 = [volumes[-4], volumes[-3], volumes[-2]]
    vol_secando = volumes[-1] < vol_ma * 0.25 and volumes[-1] < min(vol3) * 0.5

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
    liq_topo = (maximas[-1] >= sm_swing_h and
                fechamentos[-1] < sm_swing_h and (maximas[-1] - fechamentos[-1]) > atr * 0.2)
    liq_fundo = (minimas[-1] <= sm_swing_l and
                 fechamentos[-1] > sm_swing_l and (fechamentos[-1] - minimas[-1]) > atr * 0.2)

    # Varredura de topo/fundo histórica (filtro baleia) — padrão: nova extrema + rejeição/absorção
    _atr_liq = atr * 0.2
    liq_fundo_hist10 = liq_fundo or any(
        (minimas[i] < minimas[i-1] and fechamentos[i] > minimas[i-1] and
         fechamentos[i] > aberturas[i] and (fechamentos[i] - minimas[i]) > _atr_liq)
        for i in range(-10, -1)
    )
    liq_topo_hist10 = liq_topo or any(
        (maximas[i] > maximas[i-1] and fechamentos[i] < maximas[i-1] and
         fechamentos[i] < aberturas[i] and (maximas[i] - fechamentos[i]) > _atr_liq)
        for i in range(-10, -1)
    )
    liq_fundo_hist5 = liq_fundo or any(
        (minimas[i] < minimas[i-1] and fechamentos[i] > minimas[i-1] and
         (fechamentos[i] - minimas[i]) > _atr_liq)
        for i in range(-5, -1)
    )
    liq_topo_hist5 = liq_topo or any(
        (maximas[i] > maximas[i-1] and fechamentos[i] < maximas[i-1] and
         (maximas[i] - fechamentos[i]) > _atr_liq)
        for i in range(-5, -1)
    )
    # Distância da EMA21 — gate de qualidade
    dist_e21_long  = preco <= e21 * 1.03   # LONG: preço até 3% acima da EMA21
    dist_e21_short = preco >= e21 * 0.97   # SHORT: preço até 3% abaixo da EMA21

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
    # Anti-pump: RSI disparou >15 pts em 3 velas E já está rente ao teto de 55 — não perseguir
    # (apenas para LONG — o SHORT oposto não se aplica: RSI caindo de 65→47 É um bom SHORT)
    pump_rsi_spike_long  = (rsi - rsi_ant) > 15 and rsi > 54
    dump_rsi_spike_short = (rsi_ant - rsi) > 15 and rsi < 41  # apenas caso extremo já próximo do piso 40

    rsi_nao_topo   = rsi < 70
    rsi_nao_fundo  = rsi > 27
    seguro_long  = (not perto_bb_topo and not ext_acima_e21 and not vol_secando and
                    not exaustao_topo and rsi_nao_topo and not stoch_esticado_up and
                    not pump_rsi_spike_long)
    seguro_short = (not vol_secando and not exaustao_fund and rsi_nao_fundo and
                    not stoch_esticado_down)

    # Volume FLEX
    vol_avg       = volumes[-1] > vol_ma * 1.1 and volumes[-2] > vol_ma * 0.9
    _vol_thr      = 0.20 if _FLV <= 0 else (0.50 if _FLV == 1 else (0.65 if _FLV == 2 else 0.80))
    vol_nao_fade  = max(volumes[-1], volumes[-2]) >= vol_ma * _vol_thr  # usa melhor das 2 últimas velas
    vol_ok        = v_forte or obv_bull
    vol_ok_s      = v_forte or obv_bear
    flex_vol_ok   = v_bom or (obv_bull and trendilo_long)
    flex_vol_ok_s = v_bom or (obv_bear and trendilo_short)

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

    # RSI zona de entrada — corte rígido sem exceção, aplicado a todos os tipos de sinal
    # LONG: RSI < 55 (não comprar topo — restaurado 14/06)
    # SHORT: RSI > 40 (não vender fundo)
    rsi_zona_long  = rsi < 55
    rsi_zona_short = rsi > 40
    rsi_entrada_long  = rsi >= 45   # RSI mínimo para entrar LONG (diagnóstico)
    rsi_entrada_short = rsi <= 55   # RSI máximo para entrar SHORT (diagnóstico)

    # SURGE
    candle_bull_pct = (preco - aberturas[-1]) / max(aberturas[-1], 1e-10)
    candle_bear_pct = (aberturas[-1] - preco) / max(aberturas[-1], 1e-10)
    surge_break_h   = preco > max(maximas[-11:-1])
    surge_break_l   = preco < min(minimas[-11:-1])

    # Anti-FOMO
    tres_bull_exp = (
        aberturas_reais[-3] < fechamentos_reais[-3] and fechamentos_reais[-3] - aberturas_reais[-3] > atr * 0.35 and
        aberturas_reais[-2] < fechamentos_reais[-2] and fechamentos_reais[-2] - aberturas_reais[-2] > atr * 0.35 and
        aberturas_reais[-1] < fechamentos_reais[-1] and fechamentos_reais[-1] - aberturas_reais[-1] > atr * 0.35
    ) if n >= 4 else False
    tres_bear_exp = (
        aberturas_reais[-3] > fechamentos_reais[-3] and aberturas_reais[-3] - fechamentos_reais[-3] > atr * 0.35 and
        aberturas_reais[-2] > fechamentos_reais[-2] and aberturas_reais[-2] - fechamentos_reais[-2] > atr * 0.35 and
        aberturas_reais[-1] > fechamentos_reais[-1] and aberturas_reais[-1] - fechamentos_reais[-1] > atr * 0.35
    ) if n >= 4 else False
    preco_longe_e21_up   = preco > e21 * 1.05
    preco_longe_e21_down = preco < e21 * 0.95
    vol_crescente = volumes[-1] > volumes[-2] if n >= 2 else False

    # Scout FLEX score (5 de 8 itens)
    _rompimento_rec_l = surge_break_h
    _rompimento_rec_s = surge_break_l
    scout_score_long = sum([
        dna_flow_bull,               # 1. Fluxo institucional positivo
        obv_bull,                    # 2. OBV positivo
        e10 > e21,                   # 3. MM10 acima de MM21
        e21 > e50,                   # 4. MM21 acima de MM50
        volumes[-1] > vol_ma * 0.8,  # 5. Volume crescente
        tbull_r,                     # 6. Estrutura de alta preservada
        _rompimento_rec_l,           # 7. Rompimento recente
        ha_bull,                     # 8. HA Bull
    ])
    scout_score_short = sum([
        dna_flow_bear,               # 1. Fluxo institucional negativo
        obv_bear,                    # 2. OBV negativo
        e10 < e21,                   # 3. MM10 abaixo de MM21
        e21 < e50,                   # 4. MM21 abaixo de MM50
        volumes[-1] > vol_ma * 0.8,  # 5. Volume crescente
        tbear_r,                     # 6. Estrutura de baixa preservada
        _rompimento_rec_s,           # 7. Rompimento recente
        ha_bear,                     # 8. HA Bear
    ])

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
                                   ha_bull_1, trendilo_long, rsi_subindo,
                                   v_forte, rsi_div_bull, sm_bull)
    score_inst_short = _score_inst(tendencia_bear, adx_short_ok,
                                   dna_flow_bear or (f_bear and pressao_bear),
                                   ha_bear_1, trendilo_short, rsi_caindo,
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
        "rvol_max2": rvol_max2,
        "v_bom": v_bom, "v_forte": v_forte, "v_inst": v_inst, "v_forte2": v_forte2,
        "vol_ma": vol_ma, "volumes": volumes, "vol_nao_fade": vol_nao_fade,
        "flex_vol_ok": flex_vol_ok, "flex_vol_ok_s": flex_vol_ok_s,
        # Flow
        "f_bull": f_bull, "f_bear": f_bear, "f_forte": f_forte,
        "pressao_bull": pressao_bull, "pressao_bear": pressao_bear,
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
        "liq_fundo_hist10": liq_fundo_hist10, "liq_topo_hist10": liq_topo_hist10,
        "liq_fundo_hist5": liq_fundo_hist5, "liq_topo_hist5": liq_topo_hist5,
        "dist_e21_long": dist_e21_long, "dist_e21_short": dist_e21_short,
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
        "pump_rsi_spike_long": pump_rsi_spike_long, "dump_rsi_spike_short": dump_rsi_spike_short,
        "perto_bb_topo": perto_bb_topo, "perto_bb_fund": perto_bb_fund,
        "ext_acima_e21": ext_acima_e21, "ext_abaixo_e21": ext_abaixo_e21,
        "vol_secando": vol_secando,
        "lateralizado": lateralizado,
        # Surge
        "candle_bull_pct": candle_bull_pct, "candle_bear_pct": candle_bear_pct,
        "surge_break_h": surge_break_h, "surge_break_l": surge_break_l,
        # Anti-FOMO / Scout FLEX
        "tres_bull_exp": tres_bull_exp, "tres_bear_exp": tres_bear_exp,
        "preco_longe_e21_up": preco_longe_e21_up, "preco_longe_e21_down": preco_longe_e21_down,
        "vol_crescente": vol_crescente,
        "scout_score_long": scout_score_long, "scout_score_short": scout_score_short,
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
    i = ind

    _fluxo_inst_l = i["dna_flow_bull"] or (i["f_bull"] and i["pressao_bull"])
    _fluxo_inst_s = i["dna_flow_bear"] or (i["f_bear"] and i["pressao_bear"])

    # ── PREMIUM ───────────────────────────────────────────────────────────────
    long_premium  = (i["score_inst_long"] >= 70 and
                     45 <= i["rsi"] <= 65 and
                     i["rvol_max2"] >= 1.8 and
                     i["e10"] > i["e21"] and i["e21"] > i["e50"] and
                     i["preco"] > i["e50"] and
                     i["obv_bull"] and
                     i["adx"] > 20 and
                     _fluxo_inst_l and
                     i["ha_bull"] and
                     i["vol_crescente"] and
                     not i["liq_topo"] and
                     not i["lateralizado"] and
                     not i["tres_bull_exp"] and
                     not i["preco_longe_e21_up"])

    short_premium = (i["score_inst_short"] >= 70 and
                     35 <= i["rsi"] <= 55 and
                     i["rvol_max2"] >= 1.8 and
                     i["e10"] < i["e21"] and i["e21"] < i["e50"] and
                     i["preco"] < i["e50"] and
                     i["obv_bear"] and
                     i["adx"] > 20 and
                     _fluxo_inst_s and
                     i["ha_bear"] and
                     i["vol_crescente"] and
                     not i["liq_fundo"] and
                     not i["lateralizado"] and
                     not i["tres_bear_exp"] and
                     not i["preco_longe_e21_down"])

    # ── SCOUT FLEX ────────────────────────────────────────────────────────────
    long_scout_flex  = (i["score_inst_long"] >= 60 and
                        40 <= i["rsi"] <= 75 and
                        i["rvol_max2"] >= 1.2 and
                        i["adx"] > 15 and
                        not i["lateralizado"] and
                        not i["tres_bull_exp"] and
                        not i["preco_longe_e21_up"] and
                        not i["liq_topo"] and
                        i["scout_score_long"] >= 5)

    short_scout_flex = (i["score_inst_short"] >= 60 and
                        25 <= i["rsi"] <= 60 and
                        i["rvol_max2"] >= 1.2 and
                        i["adx"] > 15 and
                        not i["lateralizado"] and
                        not i["tres_bear_exp"] and
                        not i["preco_longe_e21_down"] and
                        not i["liq_fundo"] and
                        i["scout_score_short"] >= 5)

    # ── Prioridade ────────────────────────────────────────────────────────────
    sinal = None; fonte = ""
    for condição, dir_, src in [
        (long_premium,     "LONG",  "PREMIUM"),
        (short_premium,    "SHORT", "PREMIUM"),
        (long_scout_flex,  "LONG",  "SCOUT_FLEX"),
        (short_scout_flex, "SHORT", "SCOUT_FLEX"),
    ]:
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
    elif pts >= 11: grade = "A"
    else:           grade = "B"

    # Trava de coerência: "Setup perfeito" não pode conviver com Score Inst
    # MÉDIO/FRACO nem com RSI já esticado na direção da entrada — sinais assim
    # têm convicção real menor e não merecem o selo S/S+ (caso do SOL: Grade S
    # com Score Inst 65 MÉDIO e RSI 69 que reverteu na entrada)
    if grade in ("S", "S+"):
        score_inst = i["score_inst_long"] if sinal == "LONG" else i["score_inst_short"]
        rsi_esticado = (sinal == "LONG" and i["rsi"] > 65) or (sinal == "SHORT" and i["rsi"] < 35)
        # 1 vela HA sem confirmação na anterior não merece alavancagem S (exige ha_bull/ha_bear)
        ha_fraco = (sinal == "LONG"  and i["ha_bull_1"] and not i["ha_bull"]) or \
                   (sinal == "SHORT" and i["ha_bear_1"] and not i["ha_bear"])
        if score_inst < 70 or rsi_esticado or ha_fraco:
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

    # Confiança 0-100
    if not sinal:
        confianca = 0
    else:
        _si = ind["score_inst_long"] if sinal == "LONG" else ind["score_inst_short"]
        if fonte == "PREMIUM":
            _rv_bonus = 5 if ind["rvol_max2"] >= 2.5 else 2 if ind["rvol_max2"] >= 1.8 else 0
            _adx_bonus = 3 if ind["adx"] > 30 else 1
            confianca = min(100, _si + _rv_bonus + _adx_bonus)
        else:
            _sc_fl = ind["scout_score_long"] if sinal == "LONG" else ind["scout_score_short"]
            confianca = min(85, 60 + (_sc_fl - 5) * 8)

    # Log de diagnóstico quando há score mas sem sinal
    if not sinal:
        sc = ind["score"]
        if abs(sc) > 25:
            b = []
            eh_l = sc > 0
            _si = ind["score_inst_long"] if eh_l else ind["score_inst_short"]
            _rsi = ind["rsi"]
            if eh_l:
                if _si < 60:       b.append(f"inst={_si:.0f}<60")
                if not (40 <= _rsi <= 75): b.append(f"rsi={_rsi:.0f}(fora 40-75)")
                if ind["rvol_max2"] < 1.2: b.append(f"rvol={ind['rvol_max2']:.2f}<1.2")
                if ind["adx"] <= 15:       b.append(f"adx={ind['adx']:.1f}<=15")
                if ind["lateralizado"]:    b.append("lateral")
                if ind["tres_bull_exp"]:   b.append("3velas_exp")
                if ind["preco_longe_e21_up"]: b.append("ext_e21>5%")
                if ind.get("liq_topo"):    b.append("liq_topo")
                sc_fl = ind["scout_score_long"]
                if sc_fl < 5:              b.append(f"scout={sc_fl}/8<5")
                if not ind["ha_bull_1"]:   b.append("ha=F")
            else:
                if _si < 60:       b.append(f"inst={_si:.0f}<60")
                if not (25 <= _rsi <= 60): b.append(f"rsi={_rsi:.0f}(fora 25-60)")
                if ind["rvol_max2"] < 1.2: b.append(f"rvol={ind['rvol_max2']:.2f}<1.2")
                if ind["adx"] <= 15:       b.append(f"adx={ind['adx']:.1f}<=15")
                if ind["lateralizado"]:    b.append("lateral")
                if ind["tres_bear_exp"]:   b.append("3velas_exp")
                if ind["preco_longe_e21_down"]: b.append("ext_e21<-5%")
                if ind.get("liq_fundo"):   b.append("liq_fundo")
                sc_fl = ind["scout_score_short"]
                if sc_fl < 5:              b.append(f"scout={sc_fl}/8<5")
                if not ind["ha_bear_1"]:   b.append("ha=F")
            dir_ = "LONG-BLOQ" if eh_l else "SHORT-BLOQ"
            log.info(f"  {dir_} {simbolo}: score={sc:+d} | {'; '.join(b) or 'sem detalhe'}")
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
        "confianca":    confianca,
        # Indicadores para ciclo e envio
        "ha_bull":      ind["ha_bull"],  "ha_bear":   ind["ha_bear"],
        "ha_bull_1":    ind["ha_bull_1"], "ha_bear_1": ind["ha_bear_1"],
        "obv_bull":     ind["obv_bull"],
        "acima_vwap":   ind["acima_vwap"],
        "v_forte":      ind["v_forte"],
        "obv_bear":     ind["obv_bear"],
        "rvol":          ind["rvol"],
        "rvol_label":    ind["rvol_label"],
        "rvol_tier":     ind["rvol_tier"],
        "rvol_tier_max2": ind["rvol_tier_max2"],
        "rvol_max2":     ind["rvol_max2"],
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
        "liq_fundo_hist10": ind["liq_fundo_hist10"],
        "liq_topo_hist10":  ind["liq_topo_hist10"],
        "liq_fundo_hist5":  ind["liq_fundo_hist5"],
        "liq_topo_hist5":   ind["liq_topo_hist5"],
        "dist_e21_long":    ind["dist_e21_long"],
        "dist_e21_short":   ind["dist_e21_short"],
        "sombra_sup":   ind["sombra_sup"],
        "sombra_inf":   ind["sombra_inf"],
        "dna_flow_bull": ind["dna_flow_bull"],
        "dna_flow_bear": ind["dna_flow_bear"],
        "dna_flex_bull": ind["dna_flex_bull"],
        "dna_flex_bear": ind["dna_flex_bear"],
        "trendilo_long":  ind["trendilo_long"],
        "trendilo_short": ind["trendilo_short"],
        "funding_rate":   funding_rate,
        # Campos para diagnóstico detalhado
        "rsi_ant":        ind["rsi_ant"],
        "rsi_subindo":    ind["rsi_subindo"],
        "rsi_caindo":     ind["rsi_caindo"],
        "e21":            ind["e21"],
        "adx_subindo":    ind["adx_subindo"],
        "f_bull":         ind["f_bull"],
        "f_bear":         ind["f_bear"],
        "seguro_long":    ind["seguro_long"],
        "seguro_short":   ind["seguro_short"],
        "lateralizado":   ind["lateralizado"],
        "vol_nao_fade":   ind["vol_nao_fade"],
        "nao_ext_long_tight":  ind["nao_ext_long_tight"],
        "nao_ext_short_tight": ind["nao_ext_short_tight"],
        "nao_overext_long":    ind["nao_overext_long"],
        "nao_overext_short":   ind["nao_overext_short"],
        "rsi_zona_long":  ind["rsi_zona_long"],
        "rsi_zona_short": ind["rsi_zona_short"],
        "macd_bull_r":    ind["macd_bull_r"],
        "macd_bear_r":    ind["macd_bear_r"],
        "rsi_entrada_long":  ind["rsi_entrada_long"],
        "rsi_entrada_short": ind["rsi_entrada_short"],
        # Sub-campos de seguro (diagnóstico mostra causa real em vez de "?")
        "perto_bb_topo":     ind["perto_bb_topo"],
        "ext_acima_e21":     ind["ext_acima_e21"],
        "vol_secando":       ind["vol_secando"],
        "exaustao_topo":     ind["exaustao_topo"],
        "exaustao_fund":     ind["exaustao_fund"],
        "stoch_rsi":         ind["stoch_rsi"],
        "stoch_esticado_up": ind["stoch_esticado_up"],
        "stoch_esticado_down": ind["stoch_esticado_down"],
        "pump_rsi_spike_long":  ind["pump_rsi_spike_long"],
        "dump_rsi_spike_short": ind["dump_rsi_spike_short"],
        # Outros campos usados no diagnóstico
        "e200":              ind["e200"],
        "kalman_descendo":   ind["kalman_descendo"],
        "ha_bull2":          ind["ha_bull2"],
        "ha_bear2":          ind["ha_bear2"],
        "flex_vol_ok":       ind["flex_vol_ok"],
        "flex_vol_ok_s":     ind["flex_vol_ok_s"],
        # PRO V2 — Anti-FOMO / Scout FLEX
        "tres_bull_exp":     ind["tres_bull_exp"],
        "tres_bear_exp":     ind["tres_bear_exp"],
        "preco_longe_e21_up":  ind["preco_longe_e21_up"],
        "preco_longe_e21_down": ind["preco_longe_e21_down"],
        "vol_crescente":     ind["vol_crescente"],
        "scout_score_long":  ind["scout_score_long"],
        "scout_score_short": ind["scout_score_short"],
    }
