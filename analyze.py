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
from config import (
    SIGNAL_MODE, FILTER_LEVEL as _FLV,
    SCORE_BRONZE, SCORE_PRATA, SCORE_OURO,
    RVOL_MIN, ADX_MIN_GLOBAL,
    MIN_FLUXO_LONG, MIN_FLUXO_SHORT,
    RSI_LONG_MIN, RSI_LONG_MAX, RSI_SHORT_MIN, RSI_SHORT_MAX,
    BLOQUEAR_LONG_BB_TOPO, BLOQUEAR_SHORT_BB_FUNDO, PENALIDADE_BB_EXTREMO,
    HA_CONFIRM_BARS, HA_REVERSAL_OK, ADX_NAO_SUBINDO_BLOQUEIA, ADX_FLEX_MARGIN,
    ADX_MIN_FLEX, ADX_MIN_SCOUT,
    STOCH_EXTREMO_BLOQUEAR, VOLUME_SECANDO_BLOQUEAR, MERCADO_LATERAL_BLOQUEAR,
    FLOW_CONFIRMADO, LIQ_SWEEP, DIST_MM21_MAX, BTC_H4_BLOQUEIA_LONG,
    MM200_OBRIGATORIA,
)

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

    # Heikin-Ashi: corpo mínimo (0.2 ATR) filtra dojis
    ha_corpo_ok = abs(fechamentos[-1] - aberturas[-1]) > atr * 0.2
    ha_bull_1 = fechamentos[-1] > aberturas[-1] and ha_corpo_ok
    ha_bear_1 = fechamentos[-1] < aberturas[-1] and ha_corpo_ok
    ha_bull  = ha_bull_1 and (True if HA_CONFIRM_BARS <= 1 else fechamentos[-2] > aberturas[-2])
    ha_bear  = ha_bear_1 and (True if HA_CONFIRM_BARS <= 1 else fechamentos[-2] < aberturas[-2])
    ha_bull2 = ha_bull and ha_corpo_ok
    ha_bear2 = ha_bear and ha_corpo_ok
    ha_bull3 = ha_bull2 and (True if HA_CONFIRM_BARS <= 2 else fechamentos[-3] > aberturas[-3])
    ha_bear3 = ha_bear2 and (True if HA_CONFIRM_BARS <= 2 else fechamentos[-3] < aberturas[-3])

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
    # StochRSI normaliza pela faixa relativa dos últimos 14 períodos e satura em
    # tendências fortes mesmo sem sobrecompra/sobrevenda real (ex: RSI 49 com stoch_rsi>0.95).
    # Exige RSI absoluto elevado/baixo também, evitando bloquear LONG/SHORT válidos por saturação técnica.
    # Afrouxado 23/06 (run pós-merge v5.0 — candidatos fortes GWEI/BDX bloqueados
    # por bb_topo+stoch combinado mesmo sem RSI extremo); REGRA #1/#5 intocadas.
    # 2º ajuste 23/06 — BDX (score+145, RSI70, dentro da zona REGRA #1) ainda
    # bloqueado isolado por stoch=0.93; sobe o teto pra exigir saturação mais
    # extrema antes de travar um candidato que já passou todo o resto do seguro_long.
    stoch_esticado_up   = STOCH_EXTREMO_BLOQUEAR and stoch_rsi > 0.95 and rsi > 65
    stoch_esticado_down = STOCH_EXTREMO_BLOQUEAR and stoch_rsi < 0.05 and rsi < 30
    stoch_extremo = STOCH_EXTREMO_BLOQUEAR and (stoch_rsi <= 0.001 or stoch_rsi >= 0.999)

    if len(_rsi_ser) >= 15:
        _r14a = _rsi_ser[-15:-1]; _rmina = min(_r14a); _rmaxa = max(_r14a)
        stoch_rsi_ant = (_r14a[-1] - _rmina) / (_rmaxa - _rmina) if _rmaxa > _rmina else 0.5
    else:
        stoch_rsi_ant = stoch_rsi
    stoch_subindo = stoch_rsi > stoch_rsi_ant
    stoch_caindo  = stoch_rsi < stoch_rsi_ant
    stoch_momentum_long  = 0.15 <= stoch_rsi <= 0.85 and stoch_subindo
    stoch_momentum_short = 0.15 <= stoch_rsi <= 0.85 and stoch_caindo

    # RSI dinâmico (momentum, GAUSS+DNA v5.0): exige RSI subindo/caindo 3 pontos
    # seguidos dentro de uma janela específica de "espaço pra continuar" — não é o
    # mesmo gate que rsi_zona_long/short (REGRA #1, extremo absoluto 75/25).
    rsi_subindo_3 = len(_rsi_ser) >= 3 and _rsi_ser[-1] > _rsi_ser[-2] > _rsi_ser[-3]
    rsi_caindo_3  = len(_rsi_ser) >= 3 and _rsi_ser[-1] < _rsi_ser[-2] < _rsi_ser[-3]
    rsi_dinamico_long  = 30 <= rsi <= 55 and rsi_subindo_3
    rsi_dinamico_short = 45 <= rsi <= 70 and rsi_caindo_3

    # DMI / ADX
    pdi, mdi, adx, adx_p, adx_p2, adx_p3 = calcular_adx(candles[-60:])
    adx_long_ok  = adx > 22 and pdi > mdi and adx > adx_p
    adx_short_ok = adx > 22 and mdi > pdi and adx > adx_p

    # Volume — RVOL 4 tiers (atual e anterior — pega sinal que ocorreu na vela passada)
    vol_ma = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else sum(volumes[:-1]) / max(len(volumes)-1, 1)
    vol_media5 = sum(volumes[-6:-1]) / 5 if len(volumes) >= 6 else vol_ma
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
    perto_bb_topo = pos_bb > 0.99  # afrouxado 23/06 (caso real KMNO score+120 RSI64 ADX21, bloqueado isolado em bb_topo)
    perto_bb_fund = pos_bb < 0.01
    ext_acima_e21  = (preco - e21) / atr > 3.0
    ext_abaixo_e21 = (e21 - preco) / atr > 3.0
    vol3 = [volumes[-4], volumes[-3], volumes[-2]]
    # Afrouxado 22/06 (pedido do usuário — avaliação de oportunidades perdidas):
    # auditoria de um run real de 55min/12 ciclos achou ZERO sinais disparados;
    # vol_secando isolado respondia por ~40% de todo "seguro=F" (187+ ocorrências
    # de 669 candidatos LONG/SHORT bloqueados) — limiar 0.25/0.5 bloqueava fade de
    # volume moderado, não só o esgotamento extremo que o filtro pretende capturar.
    # Afrouxado de novo 23/06 (run pós-merge v5.0, 11 ciclos, zero sinais — vol_sec
    # ainda era o bloqueador mais frequente mesmo após o primeiro afrouxamento).
    # Afrouxado uma 3ª vez 23/06 (run real pós-merge da alavancagem dinâmica: TEL
    # LONG score+100/RSI65 e NOCK SHORT score-128/RSI31, ambos com score bom e RSI
    # normal, bloqueados isoladamente só por vol_sec — nenhum outro filtro pegou).
    vol_secando = volumes[-1] < vol_ma * 0.06 and volumes[-1] < min(vol3) * 0.15

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
    # Afrouxado 22/06 (pedido do usuário — "o que falta pra dar sinal"): auditoria
    # de um run real de 55min/12 ciclos achou ZERO sinais (já com vol_secando e o
    # filtro de regime BTC afrouxados antes); exaustao_topo/fund isolado respondia
    # por 240/665 (~36%) de todo "seguro=F", 2º maior bloqueador depois de vol_sec.
    # Pavio >40% do range já capturava rejeição moderada, não só exaustão extrema.
    exaustao_topo = sombra_sup > 0.55 and preco < (maximas[-1] - bb_range * 0.02)
    exaustao_fund = sombra_inf > 0.55 and preco > (minimas[-1] + bb_range * 0.02)

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
    # Sweep recente (últimos 12 candles) — usado pelo modo INSTITUCIONAL (pedido 20/06)
    liq_topo_12 = any(maximas[-k] >= sm_swing_h and fechamentos[-k] < sm_swing_h and
                       (maximas[-k] - fechamentos[-k]) > atr * 0.2 for k in range(1, min(13, n)))
    liq_fundo_12 = any(minimas[-k] <= sm_swing_l and fechamentos[-k] > sm_swing_l and
                        (fechamentos[-k] - minimas[-k]) > atr * 0.2 for k in range(1, min(13, n)))

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

    # Estrutura de swing (HH/HL = alta, LH/LL = baixa) via pivôs de 3 velas
    # nos últimos 30 candles — usado pelo modo INSTITUCIONAL (filtro rígido)
    def _pivots(lookback=30):
        ph, pl = [], []
        for k in range(-lookback, -1):
            if maximas[k] > maximas[k-1] and maximas[k] > maximas[k+1]:
                ph.append(maximas[k])
            if minimas[k] < minimas[k-1] and minimas[k] < minimas[k+1]:
                pl.append(minimas[k])
        return ph, pl
    _piv_h, _piv_l = _pivots()
    estrutura_alta  = len(_piv_h) >= 2 and len(_piv_l) >= 2 and _piv_h[-1] > _piv_h[-2] and _piv_l[-1] > _piv_l[-2]
    estrutura_baixa = len(_piv_h) >= 2 and len(_piv_l) >= 2 and _piv_h[-1] < _piv_h[-2] and _piv_l[-1] < _piv_l[-2]

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

    rsi_nao_topo   = rsi < 78
    rsi_nao_fundo  = rsi > 22
    # vol_secando saiu do bloqueio binário (23/06, 4ª rodada): mesmo após 3 afrouxa-
    # mentos de limiar no mesmo dia, continuava sendo o bloqueador isolado dominante
    # de candidatos com score alto e nada mais de errado (GRASS+145, DYDX+130, SUI-130,
    # XPR+98 — run real pós-merge da alavancagem, todos com vol_sec como ÚNICO motivo).
    # Em vez de afrouxar o número de novo (já documentado como esgotado, CLASSIFICAÇÃO
    # INSTITUCIONAL V4 acima), vol_secando passa a contar só como "alerta leve" no
    # sistema de tolerância já existente (seguro_alertas_long/short, GAUSS+DNA v5.0,
    # `classificar_v2()` exige `seguro_alertas <= 1`) — continua penalizando entrada
    # de baixo volume, mas não mata o sinal isoladamente na cascata de detecção.
    _bloq_bb_topo = not perto_bb_topo if BLOQUEAR_LONG_BB_TOPO else True
    seguro_long  = (_bloq_bb_topo and not ext_acima_e21 and
                    not exaustao_topo and rsi_nao_topo)
    seguro_short = (not exaustao_fund and rsi_nao_fundo)

    # SEGURO — contagem de alertas (GAUSS+DNA v5.0): cada booleano abaixo é um
    # "alerta leve" de qualidade de entrada; PRATA/BRONZE toleram no máx. 1.
    _vol_alerta = vol_secando if VOLUME_SECANDO_BLOQUEAR else False
    seguro_alertas_long  = sum([perto_bb_topo, ext_acima_e21, exaustao_topo, _vol_alerta])
    seguro_alertas_short = sum([perto_bb_fund, ext_abaixo_e21, exaustao_fund, _vol_alerta])

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
    lateralizado       = bb_squeeze and adx < 15 and MERCADO_LATERAL_BLOQUEAR
    nao_ext_long_tight = (preco - e21) / atr < 2.5 and (rsi < 65 or (adx > 32 and rsi < 75))
    nao_ext_short_tight = (e21 - preco) / atr < 3.5 and rsi > 27

    # Anti-pump / anti-dump
    raw_c48 = [c["c"] for c in candles[-50:-1]]
    nao_overext_long  = (preco - min(raw_c48)) / max(min(raw_c48), 1e-10) < 0.50
    nao_overext_short = (max(raw_c48) - preco) / max(max(raw_c48), 1e-10) < 0.50
    rsi_nao_chasing_long  = (rsi - rsi_ant) < 18
    rsi_nao_chasing_short = (rsi_ant - rsi) < 18

    rsi_zona_long  = RSI_LONG_MIN <= rsi <= RSI_LONG_MAX
    rsi_zona_short = RSI_SHORT_MIN <= rsi <= RSI_SHORT_MAX

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
        (20 if adx >= 30 else 10 if adx >= 25 else 0) +
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
    # AJUSTE PROFISSIONAL (21/06) — RSI Flex Pro: não bloqueia (REGRA #1 intacta,
    # rsi_zona_long/short continuam <75/>25), só penaliza gradualmente entrada
    # esticada — reduz score na MESMA direção que ele já aponta, puxando o
    # sinal pra mais perto de zero quanto mais perseguido (chasing) o RSI estiver.
    if score > 0:
        if rsi > 70:   score -= 15
        elif rsi > 65: score -= 7
    elif score < 0:
        if rsi < 30:   score += 15
        elif rsi < 35: score += 7
    # CLASSIFICAÇÃO INSTITUCIONAL V3 (22/06) — mercado lateral deixou de ser
    # bloqueio universal (cycles.py) e virou penalidade gradual aqui, puxando
    # pra zero na mesma direção que o score já aponta (mesmo padrão do RSI
    # Flex Pro acima). Sinais que ainda exigem "not lateralizado" na própria
    # condição (BB_BREAK, SCOUT, etc.) continuam bloqueando — isso é só o
    # piso universal pós-cascata que mudou.
    if lateralizado:
        score = score - 10 if score > 0 else score + 10 if score < 0 else score
    if not BLOQUEAR_LONG_BB_TOPO and perto_bb_topo:
        score = score - PENALIDADE_BB_EXTREMO if score > 0 else score + PENALIDADE_BB_EXTREMO if score < 0 else score
    if not BLOQUEAR_SHORT_BB_FUNDO and perto_bb_fund:
        score = score - PENALIDADE_BB_EXTREMO if score > 0 else score + PENALIDADE_BB_EXTREMO if score < 0 else score
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
        "estrutura_alta": estrutura_alta, "estrutura_baixa": estrutura_baixa,
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
        "stoch_extremo": stoch_extremo, "stoch_momentum_long": stoch_momentum_long,
        "stoch_momentum_short": stoch_momentum_short,
        "rsi_dinamico_long": rsi_dinamico_long, "rsi_dinamico_short": rsi_dinamico_short,
        "rsi_nao_chasing_long": rsi_nao_chasing_long, "rsi_nao_chasing_short": rsi_nao_chasing_short,
        "rsi_zona_long": rsi_zona_long, "rsi_zona_short": rsi_zona_short,
        # ADX
        "pdi": pdi, "mdi": mdi, "adx_long_ok": adx_long_ok, "adx_short_ok": adx_short_ok,
        "adx_p": adx_p, "adx_subindo": adx > adx_p,
        "adx_p2": adx_p2, "adx_p3": adx_p3,
        "adx_caindo_3": adx < adx_p < adx_p2 < adx_p3,
        # Volume
        "rvol": rvol, "rvol_tier": rvol_tier, "rvol_tier_max2": rvol_tier_max2, "rvol_label": rvol_label,
        "v_bom": v_bom, "v_forte": v_forte, "v_inst": v_inst, "v_forte2": v_forte2,
        "vol_ma": vol_ma, "vol_media5": vol_media5, "volumes": volumes, "vol_nao_fade": vol_nao_fade,
        "vol_acima_media5": volumes[-1] > vol_media5,
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
        "liq_topo_12": liq_topo_12, "liq_fundo_12": liq_fundo_12,
        "pos_bb": pos_bb,
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
        "seguro_alertas_long": seguro_alertas_long, "seguro_alertas_short": seguro_alertas_short,
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
# CLASSIFICAÇÃO INSTITUCIONAL V3 (autorizado 22/06 — substitui a V2. Motivo:
# auditoria de 3 runs reais seguidos (~3h, 14h-19h44) mostrou ZERO sinais
# enviados — a V2 (Score_inst>=90/80/75 + BRONZE sempre ignorado) tinha
# acumulado filtro sobre filtro a cada incidente até o funil ficar bom demais
# pra deixar passar qualquer coisa, incluindo movimentos reais e fortes (ALLO,
# GWEI, HUS — ver screenshots do usuário). Documento "CLASSIFICAÇÃO
# INSTITUCIONAL V3" do usuário reduz os pisos de Score_inst e adiciona BRONZE
# como executável condicional (antes sempre ignorado). Continua sendo o
# próprio gate de execução (regras em cycles.py) e escolhendo o alvo de saída
# (ver "Saída em 4 estágios" em notify.py/state.py, também V3).
# ══════════════════════════════════════════════════════════════════════════════

def classificar_v2(ind, sinal, ha4_bull=None, ha4_bear=None, h1_aligned=None):
    """Classifica o sinal em OURO/PRATA/BRONZE/None pela configuração do
    usuário (24/06). Tiers com thresholds absolutos, sem bônus.
    """
    if not sinal:
        return None
    eh_long = sinal == "LONG"
    score_inst = ind["score_inst_long"] if eh_long else ind["score_inst_short"]
    rvol, adx, rsi = ind["rvol"], ind["adx"], ind["rsi"]
    preco = ind["preco"]
    e21 = ind["e21"]
    dist_pct = abs((preco - e21) / e21) * 100 if e21 else 999

    # GLOBAIS (aplicam a todos os tiers)
    if not (ind["tendencia_bull"] if eh_long else ind["tendencia_bear"]):
        return None
    if not (ind["ha_bull_1"] if eh_long else ind["ha_bear_1"]):
        return None
    macd_ok = (ind.get("macd_bull_r", False) or ind.get("macd_recuperando", False)) if eh_long else \
              (ind.get("macd_bear_r", False) or ind.get("macd_esgotando", False))
    if not macd_ok:
        return None

    fluxo = (ind["dna_flow_bull"] or ind["trendilo_long"]) if eh_long else \
            (ind["dna_flow_bear"] or ind["trendilo_short"])
    liq = (ind["liq_fundo_12"] if eh_long else ind["liq_topo_12"])
    ex = ind.get("exaustao_topo" if eh_long else "exaustao_fund", False)

    # ── OURO ──
    if (score_inst >= 90 and rvol >= 1.50 and adx >= 28
            and ind.get("adx_subindo", False)
            and (45 <= rsi <= 62 if eh_long else 38 <= rsi <= 55)
            and dist_pct <= 2.5
            and fluxo and liq and not ex):
        return "OURO"

    # ── PRATA ──
    if (score_inst >= 80 and rvol >= 1.00 and adx >= 25
            and (42 <= rsi <= 65 if eh_long else 35 <= rsi <= 58)
            and dist_pct <= 3.5
            and fluxo and liq and not ex):
        return "PRATA"

    # ── BRONZE ──
    if (score_inst >= 72 and rvol >= 0.80 and adx >= 22
            and (40 <= rsi <= 68 if eh_long else 35 <= rsi <= 60)
            and dist_pct <= 4.0
            and not ex):
        return "BRONZE"

    return None


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
                      i["seguro_long"] and i["trendilo_long"] and not i["liq_topo"] and
                      i["nao_overext_long"] and i["rsi_nao_chasing_long"] and i["nao_ext_long_tight"])
    short_pullback = (i["pullback_bear"] and tbear_r and i["preco"] > i["e21"] * 0.97 and
                      i["dna_flow_bear"] and i["adx"] > 18 and i["mdi"] > i["pdi"] and
                      i["rsi_zona_short"] and i["score_inst_short"] >= 50 and
                      i["seguro_short"] and i["trendilo_short"] and not i["liq_fundo"] and
                      i["nao_overext_short"] and i["rsi_nao_chasing_short"] and i["nao_ext_short_tight"])

    # ── CORE — 11 critérios institucionais (adicionado 14/06) ────────────────
    _vol_ok_core = not i["vol_secando"] if VOLUME_SECANDO_BLOQUEAR else True
    long_core  = (45 <= i["rsi"] <= 58 and i["rsi_subindo"] and
                  i["adx"] >= 18 and i["vol_nao_fade"] and _vol_ok_core and
                  i["kalman_subindo"] and i["trendilo_long"] and
                  i["tbull_loose"] and i["ha_bull"] and
                  not i["liq_topo"] and i["preco"] > i["e200"] and
                  i["preco"] <= i["e21"] * 1.02)
    short_core = (42 <= i["rsi"] <= 55 and i["rsi_caindo"] and
                  i["adx"] >= 18 and i["vol_nao_fade"] and _vol_ok_core and
                  not i["kalman_subindo"] and i["trendilo_short"] and
                  i["tbear_loose"] and i["ha_bear"] and
                  not i["liq_fundo"] and i["preco"] < i["e200"] and
                  i["preco"] >= i["e21"] * 0.98)

    # ── Cross ─────────────────────────────────────────────────────────────────
    long_cross  = (i["algum_cross_bull"] and i["dna_flow_bull"] and i["adx_long_ok"] and
                   i["preco"] > i["e200"] and i["score_inst_long"] >= 50 and i["rsi_zona_long"] and
                   i["seguro_long"] and (i["trendilo_long"] or i["kalman_subindo"]) and
                   i["nao_overext_long"] and i["rsi_nao_chasing_long"] and i["nao_ext_long_tight"])
    short_cross = (i["algum_cross_bear"] and i["dna_flow_bear"] and i["adx_short_ok"] and
                   i["preco"] < i["e200"] and i["score_inst_short"] >= 50 and i["rsi_zona_short"] and
                   i["seguro_short"] and (i["trendilo_short"] or not i["kalman_subindo"]) and
                   i["nao_overext_short"] and i["rsi_nao_chasing_short"] and i["nao_ext_short_tight"])

    # ── Variáveis de nível de filtro (usadas em BB_BREAK e SCOUT) ────────────
    _fluxo_min   = 0 if _FLV <= 0 else (1 if _FLV == 1 else 2)
    _adx_sub_ok  = i["adx_subindo"] if (_FLV >= 2 and ADX_NAO_SUBINDO_BLOQUEIA) else True
    _no_liq_topo = (not i["liq_topo"])  if _FLV >= 3 else True
    _no_liq_fund = (not i["liq_fundo"]) if _FLV >= 3 else True

    # ── BB Breakout ───────────────────────────────────────────────────────────
    # preco vs e200 (pedido 20/06 — caso SPCXUSDT: short_bb_break disparou só com
    # rompimento local de banda + Kalman curto, sem checar tendência de fundo, e
    # foi pego por reversão violenta em ativo de baixa liquidez). Mesmo filtro que
    # já existe no SM_SWEEP, evita romper banda contra a tendência maior.
    _rvol_bb      = 0.50 if _FLV <= 1 else (0.65 if _FLV == 2 else 0.80)
    # StochRSI esgotado (pedido 21/06 — casos reais CVX/ASTER: BB_BREAK disparou com
    # StochRSI já saturado <0.05/>0.80 e RSI já no fim da janela, ou seja, depois do
    # movimento em vez de com espaço pra continuar). Só o pedaço de stoch de
    # seguro_long/short — não o seguro_long/short inteiro, que contradiria bb_break_long/
    # short por definição (perto_bb_topo/fund é sempre verdadeiro quando o preço já
    # rompeu a banda).
    # RSI com "espaço pra correr" (pedido 21/06 — 3º caso real, WUSDT LONG RSI=68,
    # rompeu quase encostando no teto da REGRA #1 (75) e devolveu o movimento. Junto
    # com CVX/ASTER (RSI~30, quase no piso 25), os 3 incidentes reais de BB_BREAK
    # nesta sessão entraram a <10 pontos do limite absoluto de rsi_zona — comprando/
    # vendendo exatamente quando o RSI já não tinha mais espaço pra continuar na
    # direção do sinal. Piso/teto adicional só pro BB_BREAK (não altera rsi_zona_long/
    # short, que é REGRA #1 e continua <75/>25 pra todos os outros sinais) — exige
    # pelo menos ~10pts de margem até o teto/piso absoluto antes de disparar.
    long_bb_break  = (i["bb_break_long"] and i["bb_expand"] and i["kalman_subindo"] and
                      i["k_short_subindo"] and i["score"] > 40 and i["adx"] >= 15 and
                      _adx_sub_ok and not i["lateralizado"] and not i["ext_acima_e21"] and
                      i["obv_bull"] and _no_liq_topo and i["preco"] > i["e200"] and
                      i["preco"] > i["e50"] and not i["stoch_esticado_up"] and
                      i["rvol"] >= _rvol_bb and i["rsi_zona_long"] and i["rsi"] < 65 and
                      i["score_inst_long"] >= 50 and
                      i["nao_overext_long"] and i["rsi_nao_chasing_long"])
    short_bb_break = (i["bb_break_short"] and i["bb_expand"] and i["kalman_descendo"] and
                      i["k_short_descendo"] and i["score"] < -40 and i["adx"] >= 15 and
                      _adx_sub_ok and not i["lateralizado"] and not i["ext_abaixo_e21"] and
                      i["obv_bear"] and _no_liq_fund and i["preco"] < i["e200"] and
                      i["preco"] < i["e50"] and not i["stoch_esticado_down"] and
                      i["rvol"] >= _rvol_bb and i["rsi_zona_short"] and i["rsi"] > 35 and
                      i["score_inst_short"] >= 50 and
                      i["nao_overext_short"] and i["rsi_nao_chasing_short"])

    # ── Smart Money ───────────────────────────────────────────────────────────
    long_sm  = (i["sm_bull"] and i["rsi"] > 25 and i["rsi_zona_long"] and
                i["preco"] > i["e200"] and i["score_inst_long"] >= 60 and
                i["nao_overext_long"] and i["rsi_nao_chasing_long"] and i["nao_ext_long_tight"])
    short_sm = (i["sm_bear"] and i["rsi_zona_short"] and i["rsi"] < 75 and
                i["preco"] < i["e200"] and i["score_inst_short"] >= 60 and
                i["nao_overext_short"] and i["rsi_nao_chasing_short"] and i["nao_ext_short_tight"])

    # ── Reversão extrema ──────────────────────────────────────────────────────
    long_reversal  = (i["rsi"] < 30 and (HA_REVERSAL_OK or i["ha_bull"]) and i["v_forte"] and
                      (i["liq_fundo"] or i["absorb_bull"]) and i["macd_recuperando"] and
                      i["adx"] > 12 and i["preco"] > i["e200"] * 0.96 and
                      (i["dna_flow_bull"] or i["obv_bull"]))
    short_reversal = (i["rsi"] > 70 and (HA_REVERSAL_OK or i["ha_bear"]) and i["v_forte"] and
                      (i["liq_topo"] or i["absorb_bear"]) and i["macd_esgotando"] and
                      i["adx"] > 12 and i["preco"] < i["e200"] * 1.04 and
                      (i["dna_flow_bear"] or i["obv_bear"]))

    # ── Surge ─────────────────────────────────────────────────────────────────
    # SURGE — breakout/breakdown explosivo com volume VSTRONG (3x+)
    # surge_break_h/l JÁ implica liq_topo/fundo (rompe máxima/mínima recente),
    # por isso não usar not liq_topo/fundo aqui — seria contradição direta.
    # Usa melhor das 2 últimas velas p/ RVOL (pega sinal da vela anterior).
    # Exige pelo menos 1 de 2 confirmações de fluxo (dna_flow OU trendilo) — pedido
    # 20/06 pós-trade LAB/USDT: SURGE sem nenhuma confirmação de fluxo (ambas "—")
    # foi puro spike de volume na quebra, sem sustentação real, e deu squeeze.
    _surge_vol_ok    = i["rvol_tier_max2"] >= 3
    _surge_flow_long  = i["dna_flow_bull"] or i["trendilo_long"]
    _surge_flow_short = i["dna_flow_bear"] or i["trendilo_short"]
    long_surge  = (_surge_vol_ok and i["candle_bull_pct"] > 0.03 and i["surge_break_h"] and
                   not i["exaustao_topo"] and (i["kalman_subindo"] or i["k_short_subindo"]) and i["ha_bull"] and
                   i["rsi"] < 78 and i["score_inst_long"] >= 50 and _surge_flow_long)
    short_surge = (_surge_vol_ok and i["candle_bear_pct"] > 0.03 and i["surge_break_l"] and
                   not i["exaustao_fund"] and (i["kalman_descendo"] or i["k_short_descendo"]) and i["ha_bear"] and
                   i["rsi"] > 22 and i["score_inst_short"] >= 50 and _surge_flow_short)

    # ── Momentum RSI ──────────────────────────────────────────────────────────
    rsi_fresh_long  = i["rsi_ant"] < 65 <= i["rsi"] < 73
    rsi_fresh_short = i["rsi_ant"] > 42 >= i["rsi"] > 30
    # Exaustão de curtíssimo prazo (sem checagem de teto de RSI — o MOMENTUM entra
    # propositalmente na faixa 65-73, então só barra se já estiver esticado/exausto)
    _mom_vol_ok_l = not i["vol_secando"] if VOLUME_SECANDO_BLOQUEAR else True
    _mom_vol_ok_s = not i["vol_secando"] if VOLUME_SECANDO_BLOQUEAR else True
    mom_seguro_long  = ((not i["perto_bb_topo"] if BLOQUEAR_LONG_BB_TOPO else True) and
                        not i["ext_acima_e21"] and _mom_vol_ok_l and
                        not i["exaustao_topo"] and not i["stoch_esticado_up"])
    mom_seguro_short = ((not i["perto_bb_fund"] if BLOQUEAR_SHORT_BB_FUNDO else True) and
                        not i["ext_abaixo_e21"] and _mom_vol_ok_s and
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
                     i["seguro_long"]  and i["nao_ext_long_tight"] and i["nao_overext_long"])
    short_rebound = (i["rsi_dip_short"]   and i["rsi_rebound_short"] and i["ha_bear"] and
                     i["dna_flow_bear"] and i["trendilo_short"] and i["adx"] > 20 and
                     i["v_bom"] and not i["kalman_subindo"] and not i["lateralizado"] and
                     i["seguro_short"] and (i["e21"] - i["preco"]) / i["atr"] < 2.5 and
                     i["nao_overext_short"])

    # ── Divergência RSI ───────────────────────────────────────────────────────
    # Sem piso de ADX nem checagem de lateralização, "divergência" é só ruído de
    # RSI oscilando num range — por isso exige tendência mínima e mercado fora de squeeze
    long_div  = (i["rsi_div_bull"] and i["ha_bull"] and i["v_bom"] and
                 i["rsi"] > 25 and i["rsi_zona_long"] and not i["exaustao_topo"] and
                 i["adx"] > 15 and not i["lateralizado"] and i["preco"] > i["e200"] and
                 i["score_inst_long"] >= 55 and
                 i["nao_overext_long"] and i["rsi_nao_chasing_long"])
    short_div = (i["rsi_div_bear"] and i["ha_bear"] and i["v_bom"] and
                 i["rsi_zona_short"] and i["rsi"] < 70 and i["preco"] < i["e200"] and
                 not i["exaustao_fund"] and i["adx"] > 15 and not i["lateralizado"] and
                 i["score_inst_short"] >= 55 and
                 i["nao_overext_short"] and i["rsi_nao_chasing_short"])

    # ── FLEX geral ────────────────────────────────────────────────────────────
    # RVOL>=1.2 e ADX>=25 (pedido 20/06 — caso TIA/USDT BRONZE 2/5 com RVOL 0.65/ADX 24 era fraco demais)
    long_flex  = (i["score"] >= 40 and i["ha_bull2"] and i["macd_bull_r"] and i["adx"] >= ADX_MIN_FLEX and
                  not i["lateralizado"] and i["nao_ext_long_tight"] and i["seguro_long"] and
                  i["flex_vol_ok"] and i["rvol"] >= 1.2 and i["rsi_zona_long"] and
                  i["nao_overext_long"] and i["rsi_nao_chasing_long"] and i["score_inst_long"] >= 50 and
                  (i["liq_long"] or i["liq_fundo"] or (i["trendilo_long"] and i["kalman_subindo"])) and
                  (i["trendilo_long"] or i["kalman_subindo"] or i["dna_flex_bull"]))
    short_flex = (i["score"] <= -40 and i["ha_bear2"] and i["macd_bear_r"] and i["adx"] >= ADX_MIN_FLEX and
                  not i["lateralizado"] and i["nao_ext_short_tight"] and i["seguro_short"] and
                  i["flex_vol_ok_s"] and i["rvol"] >= 1.2 and i["rsi_zona_short"] and
                  i["nao_overext_short"] and i["rsi_nao_chasing_short"] and i["score_inst_short"] >= 50 and
                  (i["liq_short"] or i["liq_topo"] or (i["trendilo_short"] and not i["kalman_subindo"])) and
                  (i["trendilo_short"] or not i["kalman_subindo"] or i["dna_flex_bear"]))

    # ── Setup (acumulação antecipada) ─────────────────────────────────────────
    long_setup  = (i["score"] > 50 and i["ha_bull2"] and i["macd_recuperando"] and i["adx"] > 18 and
                   i["obv_bull"] and i["v_bom"] and i["acima_vwap"] and not i["lateralizado"] and
                   i["nao_ext_long_tight"] and i["seguro_long"] and (i["liq_long"] or i["liq_fundo"]) and
                   i["preco"] > i["e200"] and i["score_inst_long"] >= 50 and i["rsi_zona_long"] and
                   i["nao_overext_long"] and i["rsi_nao_chasing_long"])
    short_setup = (i["score"] < -50 and i["ha_bear2"] and i["macd_esgotando"] and i["adx"] > 18 and
                   i["obv_bear"] and i["v_bom"] and i["abaixo_vwap"] and not i["lateralizado"] and
                   i["nao_ext_short_tight"] and i["seguro_short"] and (i["liq_short"] or i["liq_topo"]) and
                   i["preco"] < i["e200"] and i["score_inst_short"] >= 50 and i["rsi_zona_short"] and
                   i["nao_overext_short"] and i["rsi_nao_chasing_short"])

    # ── Scout (sinal secundário) ──────────────────────────────────────────────
    # RVOL>=1.2 e ADX>=25 (pedido 20/06 — mesmo piso do FLEX, caso TRUMP/USDT
    # SCOUT BRONZE 1/5 com RVOL 0.24x passou pelo vol_nao_fade solto demais)
    _sc_min  = 25 if _FLV <= 0 else 40
    _seg_l   = i["seguro_long"]  if _FLV >= 1 else True
    _seg_s   = i["seguro_short"] if _FLV >= 1 else True
    long_scout  = (i["score"] >= _sc_min and i["ha_bull_1"] and i["macd_bull_r"] and i["adx"] >= ADX_MIN_SCOUT and
                   _adx_sub_ok and not i["lateralizado"] and i["nao_ext_long_tight"] and
                   _seg_l and i["vol_nao_fade"] and i["rvol"] >= 1.2 and i["nao_overext_long"] and
                   i["rsi_nao_chasing_long"] and i["rsi_zona_long"] and _no_liq_topo and
                   sum([i["dna_flow_bull"], i["f_bull"], i["trendilo_long"], i["kalman_subindo"]]) >= _fluxo_min)
    short_scout = (i["score"] <= -_sc_min and i["ha_bear_1"] and i["macd_bear_r"] and i["adx"] >= ADX_MIN_SCOUT and
                   _adx_sub_ok and not i["lateralizado"] and i["nao_ext_short_tight"] and
                   _seg_s and i["vol_nao_fade"] and i["rvol"] >= 1.2 and i["nao_overext_short"] and
                   i["rsi_nao_chasing_short"] and i["rsi_zona_short"] and _no_liq_fund and
                   sum([i["dna_flow_bear"], i["f_bear"], i["trendilo_short"], not i["kalman_subindo"]]) >= _fluxo_min)

    # ── INSTITUCIONAL (modo opcional, filtro rígido — evoluído 20/06) ─────────
    # Reaproveita os sinais tipados já detectados acima (SM_SWEEP/MOMENTUM/SURGE/
    # PULLBACK/SETUP/FLEX) mas exige confluência total: tendência+força+fluxo+
    # sweep recente (12 candles)+estrutura de swing+RSI saudável+StochRSI não
    # esticado+volume real+distância segura das BB (anti-topo/anti-fundo).
    # H4 sem nenhuma divergência é checado em cycles.py (_h4_confirma_estrito),
    # fora do escopo desta função. SCOUT/DIV/REBOUND/BB_BREAK/CROSS/REVERSAL/
    # ELITE ficam de fora deste modo (não fazem parte da prioridade 1-6 pedida).
    # AJUSTE INSTITUCIONAL ELITE (21/06 — pedido "foco em qualidade, não
    # quantidade"): RSI LONG sobe piso de 35→45 (ainda preserva a maior parte
    # do pullback clássico, só corta RSI<45 chasing/oversold extremo); RSI
    # SHORT desce teto de 65→50 (evita short com RSI ainda neutro/forte,
    # i.e. perseguir topo de correção). HA passa a ser exigido no piso comum
    # (antes só vinha embutido em alguns sinais individuais, não em todos).
    #
    # DNA+GAUSS INSTITUCIONAL V2 (autorizado 22/06 — doc próprio do usuário,
    # objetivo "menos operações, maior taxa de TP2, winrate 45-55%"): piso de
    # ENTRADA fica mais solto (ADX 25→20, RVOL 1.5→0.70, ADX subindo ganha
    # tolerância de -2 em vez de exigir estritamente crescente, RSI SHORT teto
    # 50→55) e quem passa a filtrar de fato é o Score Inst mínimo (80→75,
    # mais solto também) combinado com a classificação OURO/PRATA/BRONZE
    # (cycles.py, agora endurecida globalmente — ver classificar_v2 acima) e
    # a exceção de lateralização (BB expandindo OU ADX>25, cycles.py) — esse
    # combo é o que de fato deveria reduzir frequência sem duplicar piso de
    # RVOL/ADX em dois lugares com números diferentes.
    _vol_inst_ok     = i["volumes"][-1] > i["vol_ma"] and (not i["vol_secando"] if VOLUME_SECANDO_BLOQUEAR else True)
    _rsi_inst_long   = 45 <= i["rsi"] <= 68
    _rsi_inst_short  = 32 <= i["rsi"] <= 55
    _anti_topo_long  = (1 - i["pos_bb"]) >= 0.01
    _anti_topo_short = i["pos_bb"] >= 0.01
    _adx_subindo_tol = i["adx"] >= i["adx_p"] - 2
    _base_inst_long  = (i["tendencia_bull"] and i["adx"] > 20 and _adx_subindo_tol and
                         i["rvol"] > 0.70 and i["dna_flow_bull"] and i["trendilo_long"] and
                         i["liq_fundo_12"] and _rsi_inst_long and i["stoch_rsi"] < 0.85 and
                         _vol_inst_ok and _anti_topo_long and i["estrutura_alta"] and
                         i["ha_bull"])
    _base_inst_short = (i["tendencia_bear"] and i["adx"] > 20 and _adx_subindo_tol and
                         i["rvol"] > 0.70 and i["dna_flow_bear"] and i["trendilo_short"] and
                         i["liq_topo_12"] and _rsi_inst_short and i["stoch_rsi"] > 0.15 and
                         _vol_inst_ok and _anti_topo_short and i["estrutura_baixa"] and
                         i["ha_bear"])

    sm_inst        = _base_inst_long  and long_sm        and i["score_inst_long"]  >= 75
    momentum_inst  = _base_inst_long  and long_momentum  and i["score_inst_long"]  >= 75
    surge_inst     = _base_inst_long  and long_surge     and i["score_inst_long"]  >= 75
    pullback_inst  = _base_inst_long  and long_pullback  and i["score_inst_long"]  >= 75
    setup_inst     = _base_inst_long  and long_setup     and i["score_inst_long"]  >= 75
    flex_inst      = _base_inst_long  and long_flex      and i["score_inst_long"]  >= 75
    sm_inst_s      = _base_inst_short and short_sm       and i["score_inst_short"] >= 75
    momentum_inst_s= _base_inst_short and short_momentum and i["score_inst_short"] >= 75
    surge_inst_s   = _base_inst_short and short_surge    and i["score_inst_short"] >= 75
    pullback_inst_s= _base_inst_short and short_pullback and i["score_inst_short"] >= 75
    setup_inst_s   = _base_inst_short and short_setup    and i["score_inst_short"] >= 75
    flex_inst_s    = _base_inst_short and short_flex     and i["score_inst_short"] >= 75

    # ── Prioridade de sinais ──────────────────────────────────────────────────
    sinal = None; fonte = ""
    if SIGNAL_MODE == "ELITE":
        if long_elite or early_long:   sinal = "LONG";  fonte = "ELITE"
        elif short_elite or early_short: sinal = "SHORT"; fonte = "ELITE"
    elif SIGNAL_MODE == "INSTITUCIONAL":
        # Prioridade pedida 20/06: SM_SWEEP > MOMENTUM > SURGE > PULLBACK > SETUP > FLEX
        ordem_inst = [
            (sm_inst,        "LONG",  "SM_SWEEP"),
            (sm_inst_s,       "SHORT", "SM_SWEEP"),
            (momentum_inst,  "LONG",  "MOMENTUM"),
            (momentum_inst_s, "SHORT", "MOMENTUM"),
            (surge_inst,     "LONG",  "SURGE"),
            (surge_inst_s,    "SHORT", "SURGE"),
            (pullback_inst,  "LONG",  "PULLBACK"),
            (pullback_inst_s, "SHORT", "PULLBACK"),
            (setup_inst,     "LONG",  "SETUP"),
            (setup_inst_s,    "SHORT", "SETUP"),
            (flex_inst,      "LONG",  "FLEX"),
            (flex_inst_s,     "SHORT", "FLEX"),
        ]
        for condição, dir_, src in ordem_inst:
            if condição:
                sinal = dir_; fonte = src; break
    else:
        ordem = [
            (long_pullback,  "LONG",  "PULLBACK"),
            (short_pullback, "SHORT", "PULLBACK"),
            (long_core,      "LONG",  "CORE"),
            (short_core,     "SHORT", "CORE"),
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
    elif pts >= 11: grade = "A"
    else:           grade = "B"

    # Trava de coerência: "Setup perfeito" não pode conviver com Score Inst
    # MÉDIO/FRACO nem com RSI já esticado na direção da entrada — sinais assim
    # têm convicção real menor e não merecem o selo S/S+ (caso do SOL: Grade S
    # com Score Inst 65 MÉDIO e RSI 69 que reverteu na entrada)
    if grade in ("S", "S+"):
        score_inst = i["score_inst_long"] if sinal == "LONG" else i["score_inst_short"]
        rsi_esticado = (sinal == "LONG" and i["rsi"] > 65) or (sinal == "SHORT" and i["rsi"] < 35)
        if score_inst < 70 or rsi_esticado:
            grade = "A"

    return grade, pts


# ══════════════════════════════════════════════════════════════════════════════
# FUNÇÃO PÚBLICA — ponto de entrada
# ══════════════════════════════════════════════════════════════════════════════

def analisar(simbolo, candles, funding_rate=None, ha4_bull=None, ha4_bear=None):
    """
    Analisa um ativo e retorna dict com sinal, fonte, grade e todos os indicadores.
    Retorna None se não houver candles suficientes.
    """
    ind = calcular_indicadores(candles)
    if ind is None:
        return None

    sinal, fonte = detectar_sinais(ind)
    grade, pts   = graduar_sinal(ind, sinal)

    # Modo INSTITUCIONAL classifica pela própria Score Inst (S>=90, A+>=80, A>=70)
    # em vez da grade por pontos — é o critério pedido nesse modo rígido
    if SIGNAL_MODE == "INSTITUCIONAL" and sinal:
        _si = ind["score_inst_long"] if sinal == "LONG" else ind["score_inst_short"]
        grade = "S" if _si >= 90 else "A+" if _si >= 80 else "A"

    classificacao = classificar_v2(ind, sinal, ha4_bull, ha4_bear)

    # Log de diagnóstico quando há score mas sem sinal — o mesmo detalhamento
    # (bloqueio_detalhe) também vai pro dict de retorno, pra cycles.py poder
    # expor o motivo EXATO por candidato no diagnóstico horário do Telegram,
    # em vez da versão genérica/aproximada que _detectar_bloqueadores_diag()
    # tinha que reconstruir a partir de só um subconjunto de campos do result.
    bloqueio_detalhe = None
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
            if not ind["rsi_zona_long"]:b.append(f"rsi_zona=F(rsi={ind['rsi']:.0f})")
            fluxo = sum([ind["dna_flow_bull"], ind["f_bull"], ind["trendilo_long"], ind["kalman_subindo"]])
            if fluxo < 2:               b.append(f"fluxo={fluxo}/4")
            if not b:
                # candidato passa em todos os checks genéricos acima mas nenhum dos 12
                # sinais tipados disparou — expõe o gatilho específico que falta
                # (pullback/cross/setup/flex/scout), 23/06, casos reais KMNO/ZRO "sem detalhe"
                _trig = []
                if not ind.get("pullback_bull"):    _trig.append("pullback=F")
                if not ind.get("algum_cross_bull"):  _trig.append("cross=F")
                if not ind.get("macd_recuperando"):  _trig.append("macd_rec=F")
                if not (ind.get("liq_long") or ind.get("liq_fundo")): _trig.append("sem_liq")
                if ind["adx"] < 25:                  _trig.append(f"adx={ind['adx']:.1f}<25(flex/scout)")
                b.append("gatilho:" + ",".join(_trig) if _trig else "sem detalhe real")
            bloqueio_detalhe = "; ".join(b) or "sem detalhe"
            log.info(f"  LONG-BLOQ {simbolo}: score={sc:+d} | {bloqueio_detalhe}")
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
            if not ind["rsi_zona_short"]: b.append(f"rsi_zona=F(rsi={ind['rsi']:.0f})")
            fluxo = sum([ind["dna_flow_bear"], ind["f_bear"], ind["trendilo_short"], not ind["kalman_subindo"]])
            if fluxo < 2:                b.append(f"fluxo={fluxo}/4")
            if not b:
                _trig = []
                if not ind.get("pullback_bear"):    _trig.append("pullback=F")
                if not ind.get("algum_cross_bear"):  _trig.append("cross=F")
                if not ind.get("macd_esgotando"):    _trig.append("macd_esg=F")
                if not (ind.get("liq_short") or ind.get("liq_topo")): _trig.append("sem_liq")
                if ind["adx"] < 25:                  _trig.append(f"adx={ind['adx']:.1f}<25(flex/scout)")
                b.append("gatilho:" + ",".join(_trig) if _trig else "sem detalhe real")
            bloqueio_detalhe = "; ".join(b) or "sem detalhe"
            log.info(f"  SHORT-BLOQ {simbolo}: score={sc:+d} | {bloqueio_detalhe}")
        else:
            bloqueio_detalhe = "score insuficiente"
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
        "bloqueio_detalhe": bloqueio_detalhe,
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
        # Expostos pra Classificação Institucional V2 / gating em cycles.py
        # (já existiam dentro de "ind", só faltava propagar pro dict final)
        "classificacao":  classificacao,
        "lateralizado":   ind["lateralizado"],
        "alinhado_bull":  ind["alinhado_bull"],
        "alinhado_bear":  ind["alinhado_bear"],
        "adx_subindo":    ind["adx_subindo"],
        "e21":            ind["e21"],
        "e50":            ind["e50"],
        "bb_expand":      ind["bb_expand"],
    }
