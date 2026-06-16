"""
GAUSS+DNA — Ciclos de execução e main
Orquestra: scan → análise → envio de sinais → controle de loop.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta

import aiohttp

from config import (
    TG_TOKEN, TG_CHATID, TIMEFRAMES, SIGNAL_MODE, LOOP_MODE, TEST_MODE,
    DYNAMIC_SCAN, SCANNER_TOP, SCAN_EVERY, CYCLE_INTERVAL,
    CAPITAL, RISK_BY_GRADE, RISK_SCOUT, RISK_PCT,
    MAX_CYCLE_RISK, MAX_SCOUT_PER_CYCLE, MAX_LONG_PER_CYCLE, MAX_SHORT_PER_CYCLE,
    FILTER_LEVEL,
)
from coins import COINS, PRIORITY_WATCHLIST
from indicators import tf_para_minutos, segundos_ate_fechamento, serie_ema, calcular_rsi
from analyze import analisar, calcular_indicadores
from notify import enviar_sinal, enviar_watchlist, notificar
from scanner import buscar_candles, escanear_melhores_moedas, _prefetch_lote, buscar_contract_data
from state import carregar_estado, salvar_estado

log = logging.getLogger("GAUSS+DNA")

MAX_SINAIS_POR_CICLO = 3


# ── Buffer de diagnóstico (30 min) ────────────────────────────────────────────

_diag_buffer: dict = {
    "bloqueadores":     {},   # motivo -> count
    "candidatos":       [],   # (score_abs, abrev, score, rsi, adx, tf)
    "total_analisados": 0,
    "ciclos":           0,
    "ultimo_sinal":     0.0,
    "ultimo_envio":     0.0,
}

_nearmiss_buffer: list = []  # (score_inst, abrev, tf, bloq_str, rsi, fonte_potencial, direcao)


def _detectar_bloqueadores_diag(result: dict) -> list:
    motivos = []
    sc_raw = result.get("score", 0)
    sc    = abs(sc_raw)
    eh_long_cand = sc_raw > 0
    rsi   = result.get("rsi", 50)
    rsi_ant = result.get("rsi_ant", rsi)
    adx   = result.get("adx", 0)
    rvol  = result.get("rvol", 1.0)
    adx_s = result.get("adx_subindo", True)
    lat   = result.get("lateralizado", False)
    dna_b = result.get("dna_flow_bull", False)
    dna_s = result.get("dna_flow_bear", False)
    trl_l = result.get("trendilo_long", False)
    trl_s = result.get("trendilo_short", False)
    liq_t = result.get("liq_topo", False)
    liq_f = result.get("liq_fundo", False)
    f_b   = result.get("f_bull", False)
    f_s   = result.get("f_bear", False)
    ha1_b = result.get("ha_bull_1", False)
    ha1_s = result.get("ha_bear_1", False)
    preco   = result.get("preco", 0)
    e200    = result.get("e200", 0)
    tbull_l = result.get("tbull_loose", False)
    tbear_l = result.get("tbear_loose", False)
    rsi_sub = result.get("rsi_subindo", False)
    rsi_cai = result.get("rsi_caindo", False)
    rsi_ent_l = result.get("rsi_entrada_long", True)
    rsi_ent_s = result.get("rsi_entrada_short", True)

    _sc_min   = 25 if FILTER_LEVEL <= 0 else 40
    _adx_min  = 10 if FILTER_LEVEL <= 0 else 18
    _fluxo_min = 0 if FILTER_LEVEL <= 0 else 1

    vnf    = result.get("vol_nao_fade", False)
    kal_up = result.get("kalman_subindo", False)

    if sc < _sc_min:
        motivos.append("score baixo")
        return motivos

    # RSI zona
    if eh_long_cand and rsi >= 55:
        motivos.append(f"RSI {rsi:.0f} >= 55 (LONG bloqueado)")
    elif not eh_long_cand and rsi <= 40:
        motivos.append(f"RSI {rsi:.0f} <= 40 (SHORT bloqueado)")

    if adx < _adx_min:
        motivos.append(f"ADX {adx:.1f} < {_adx_min}")
    if FILTER_LEVEL >= 2 and not adx_s:
        motivos.append("ADX nao subindo")
    if lat:
        motivos.append("BB squeeze lateral")

    # Fluxo — calculado cedo porque o bypass de MACD depende dele
    _fl_b = sum([dna_b, f_b, trl_l, kal_up])
    _fl_s = sum([dna_s, f_s, trl_s, not kal_up])

    # MACD — aplica mesmo bypass FL<=1 de analyze.py (fluxo>=1 substitui MACD)
    _macd_b_eff = result.get("macd_bull_r", False) or (FILTER_LEVEL <= 1 and _fl_b >= 1)
    _macd_s_eff = result.get("macd_bear_r", False) or (FILTER_LEVEL <= 1 and _fl_s >= 1)
    if eh_long_cand and not _macd_b_eff:
        motivos.append("MACD nao bull")
    elif not eh_long_cand and not _macd_s_eff:
        motivos.append("MACD nao bear")

    # Volume: vol_nao_fade é o requisito mínimo de qualquer sinal (max das 2 últimas velas >= 80% MA)
    if not vnf:
        motivos.append(f"vol_nao_fade=F (rvol={rvol:.2f}x — max 2 velas < 80% media)")

    # HA (SCOUT usa ha1, FLEX usa ha2)
    ha2_b = result.get("ha_bull2", False)
    ha2_s = result.get("ha_bear2", False)
    if eh_long_cand and not ha1_b:
        motivos.append("HA nao bull" + (" (FLEX ha2✓)" if ha2_b else ""))
    elif not eh_long_cand and not ha1_s:
        motivos.append("HA nao bear" + (" (FLEX ha2✓)" if ha2_s else ""))

    # Extensão de preço (pode bloquear SHORT após dump ou LONG após pump)
    if eh_long_cand:
        if not result.get("nao_ext_long_tight", True):
            motivos.append("ext long bloq")
        if not result.get("nao_overext_long", True):
            motivos.append("overext long")
    else:
        if not result.get("nao_ext_short_tight", True):
            motivos.append("ext short bloq")
        if not result.get("nao_overext_short", True):
            motivos.append("overext short")

    # Seguro (StochRSI e outros filtros de segurança)
    if FILTER_LEVEL >= 1:
        seg_l = result.get("seguro_long", True)
        seg_s = result.get("seguro_short", True)
        if eh_long_cand and not seg_l:
            _sg = []
            if result.get("perto_bb_topo"):         _sg.append("bb_topo")
            if result.get("ext_acima_e21"):          _sg.append("ext_e21")
            if result.get("vol_secando"):            _sg.append("vol_sec")
            if result.get("exaustao_topo"):          _sg.append("exaustao")
            if result.get("stoch_esticado_up"):      _sg.append(f"stoch>{result.get('stoch_rsi',0):.2f}")
            if result.get("pump_rsi_spike_long"):    _sg.append(f"pump_rsi(+{result.get('rsi',50)-result.get('rsi_ant',50):.0f}pt)")
            motivos.append("seguro=F(" + (",".join(_sg) or "?") + ")")
        elif not eh_long_cand and not seg_s:
            _sg = []
            if result.get("vol_secando"):            _sg.append("vol_sec")
            if result.get("exaustao_fund"):          _sg.append("exaust_fund")
            if result.get("stoch_esticado_down"):    _sg.append(f"stoch<{result.get('stoch_rsi',0):.2f}")
            if result.get("dump_rsi_spike_short"):   _sg.append(f"dump_rsi(-{result.get('rsi_ant',50)-result.get('rsi',50):.0f}pt)")
            motivos.append("seguro=F(" + (",".join(_sg) or "?") + ")")

    # Fluxo
    if FILTER_LEVEL >= 1:
        if eh_long_cand and _fl_b < _fluxo_min:
            motivos.append("sem fluxo LONG")
        elif not eh_long_cand and _fl_s < _fluxo_min:
            motivos.append("sem fluxo SHORT")

    if FILTER_LEVEL >= 3 and eh_long_cand and liq_t:
        motivos.append("liq topo SMC")
    elif FILTER_LEVEL >= 3 and not eh_long_cand and liq_f:
        motivos.append("liq fundo SMC")

    # Filtros de qualidade
    e21         = result.get("e21", 0)
    score_inst  = result.get("score_inst_long" if eh_long_cand else "score_inst_short", 0)
    kal_up      = result.get("kalman_subindo", False)
    rsi_sub_real = result.get("rsi_subindo", None)  # None = campo ausente (legado)
    rsi_cai_real = result.get("rsi_caindo", None)
    if eh_long_cand:
        if not rsi_ent_l:
            motivos.append(f"RSI entrada=F({rsi:.0f}<45)")
        # RSI caindo: só mostra se o campo real está disponível E RSI caiu >= 0.3
        if rsi_cai_real is True:
            motivos.append(f"RSI caindo({rsi:.2f}<ant{rsi_ant:.2f})")
        elif rsi_sub_real is False and rsi_cai_real is False:
            motivos.append("RSI estavel (nao subindo)")
        if not tbull_l:
            motivos.append("EMA nao alinhada (long)")
        if e200 > 0 and preco <= e200:
            motivos.append(f"abaixo e200")
        if not kal_up:
            motivos.append("Kalman descendo (LONG bloq)")
        _inst_diag = 35  # <35 bloqueia até CORE na sessão perigosa (25+10)
        if score_inst < _inst_diag:
            motivos.append(f"score_inst={score_inst}<{_inst_diag}")
        if e21 > 0 and preco > e21 * 1.05:
            motivos.append(f"preco>{e21*1.05:.4f} (acima e21+5%)")
    else:
        if not rsi_ent_s:
            motivos.append(f"RSI entrada=F({rsi:.0f}>55)")
        if rsi_sub_real is True:
            motivos.append(f"RSI subindo({rsi:.2f}>ant{rsi_ant:.2f})")
        elif rsi_sub_real is False and rsi_cai_real is False:
            motivos.append("RSI estavel (nao caindo)")
        if not tbear_l:
            motivos.append("EMA nao alinhada (short)")
        if e200 > 0 and preco >= e200:
            motivos.append(f"acima e200")
        if kal_up:
            motivos.append("Kalman subindo (SHORT bloq)")
        _inst_diag = 35  # <35 bloqueia até CORE na sessão perigosa (25+10)
        if score_inst < _inst_diag:
            motivos.append(f"score_inst={score_inst}<{_inst_diag}")
        if e21 > 0 and preco < e21 * 0.95:
            motivos.append(f"preco<{e21*0.95:.4f} (abaixo e21-5%)")

    if not motivos:
        motivos.append("HA/MACD pendente")
    return motivos


async def _enviar_diagnostico(session) -> None:
    """Envia relatório de diagnóstico de bloqueadores ao Telegram."""
    blq    = _diag_buffer["bloqueadores"]
    cand   = _diag_buffer["candidatos"]
    tot    = _diag_buffer["total_analisados"]
    ciclos = _diag_buffer["ciclos"]
    ult_sin = _diag_buffer["ultimo_sinal"]
    sem_min = int((time.time() - ult_sin) / 60) if ult_sin > 0 else 0

    # Detecta contexto de mercado pelos candidatos acumulados
    _rsi_vals = [c[3] for c in cand] if cand else []
    _rsi_med  = sum(_rsi_vals) / len(_rsi_vals) if _rsi_vals else 50
    _n_long   = sum(1 for c in cand if c[2] > 0)
    _n_short  = sum(1 for c in cand if c[2] < 0)
    if _rsi_med < 35 and _n_short > _n_long * 2:
        _ctx = "MERCADO EM QUEDA — RSI medio {:.0f} (dump coordenado)".format(_rsi_med)
    elif _rsi_med > 65 and _n_long > _n_short * 2:
        _ctx = "MERCADO SOBRECOMPRADO — RSI medio {:.0f}".format(_rsi_med)
    elif 40 <= _rsi_med <= 60:
        _ctx = "Mercado neutro — RSI medio {:.0f}".format(_rsi_med)
    else:
        _ctx = "RSI medio {:.0f}".format(_rsi_med)

    linhas = [f"DIAGNOSTICO GAUSS+DNA — sem sinais ha {sem_min}min",
              _ctx, ""]

    if blq:
        top_blq = sorted(blq.items(), key=lambda x: x[1], reverse=True)[:6]
        linhas.append("Bloqueadores mais frequentes:")
        for i, (motivo, cnt) in enumerate(top_blq, 1):
            linhas.append(f"  {i}. {motivo} — {cnt}x")
    else:
        linhas.append("Nenhum bloqueador detectado neste periodo")

    # Prioridade: RSI na zona válida primeiro (mais perto de disparar), depois por score
    def _sort_long(c):
        rsi = c[3]; rsi_ok = 1 if rsi < 55 else 0
        return (rsi_ok, c[0])
    def _sort_short(c):
        rsi = c[3]; rsi_ok = 1 if rsi > 45 else 0
        return (rsi_ok, c[0])
    top_long  = sorted([c for c in cand if c[2] > 0],  key=_sort_long,  reverse=True)[:6]
    top_short = sorted([c for c in cand if c[2] < 0],  key=_sort_short, reverse=True)[:6]
    if top_long or top_short:
        linhas.append("\nCandidatos (por que nao disparou):")
        for entry in top_long:
            _, sym, sc, rsi, adx, tf = entry[:6]
            bloqs = entry[6] if len(entry) > 6 else []
            bloq_str = ", ".join(bloqs[:3]) if bloqs else "HA/MACD pendente"
            marca = "✓" if rsi < 55 else "↑"
            linhas.append(f"  LONG  {sym} {sc:+d} RSI{rsi:.0f}{marca} → {bloq_str}")
        for entry in top_short:
            _, sym, sc, rsi, adx, tf = entry[:6]
            bloqs = entry[6] if len(entry) > 6 else []
            bloq_str = ", ".join(bloqs[:3]) if bloqs else "HA/MACD pendente"
            marca = "✓" if rsi > 40 else "↓"
            linhas.append(f"  SHORT {sym} {sc:+d} RSI{rsi:.0f}{marca} → {bloq_str}")

    linhas.append(f"\nCiclos: {ciclos} | Analises: {tot}")
    await notificar(session, "\n".join(linhas))
    log.info(f"[DIAG] Diagnostico enviado — {len(blq)} bloqueadores, {len(cand)} candidatos")


# ── Filtro horário ────────────────────────────────────────────────────────────

def dentro_horario_operacao():
    """Opera apenas 09h-13h e 14h-21h no horário de Brasília (BRT = UTC-3)."""
    brt = timezone(timedelta(hours=-3))
    h   = datetime.now(brt).hour
    return (9 <= h < 13) or (14 <= h < 21)


# ── Filtro H4 ─────────────────────────────────────────────────────────────────

def _h4_confirma(candles_h4, direcao, score_inst=0, rvol=1.0):
    """Retorna True se o sinal pode prosseguir considerando o H4.

    Três níveis:
    - H4 FORTE oposto (score<-40/>+40 + ADX>=20): bloqueia sempre
    - H4 MODERADO oposto (score<-25/>+25 + ADX>=15): bloqueia se sinal FRACO (score_inst<65 ou rvol<1.2)
    - H4 leve/neutro: não bloqueia
    """
    if candles_h4 is None:
        return True
    r4 = calcular_indicadores(candles_h4)
    if not r4:
        return True
    h4_rsi  = r4["rsi"]
    h4_vol  = r4.get("v_forte", False) or r4.get("obv_bull", False)
    h4_vols = r4.get("v_forte", False) or r4.get("obv_bear", False)
    sinal_forte = score_inst >= 65 and rvol >= 1.2

    if direcao == "LONG":
        h4_strong = (r4.get("tbear_r", False) and r4["adx"] >= 20 and
                     h4_vols and r4["score"] < -40 and h4_rsi > 45)
        h4_mild   = (r4.get("tbear_r", False) and r4["adx"] >= 15 and
                     h4_vols and r4["score"] < -25 and h4_rsi > 43)
        if h4_strong: return False
        if h4_mild and not sinal_forte: return False

    elif direcao == "SHORT":
        h4_strong = (r4.get("tbull_r", False) and r4["adx"] >= 20 and
                     h4_vol and r4["score"] > 40 and h4_rsi < 65)
        h4_mild   = (r4.get("tbull_r", False) and r4["adx"] >= 15 and
                     h4_vol and r4["score"] > 25 and h4_rsi < 68)
        if h4_strong: return False
        if h4_mild and not sinal_forte: return False

    return True


# ── Ciclo FLEX (por timeframe) ────────────────────────────────────────────────

async def executar_ciclo(session, estado, tf, moedas):
    """Executa um ciclo completo de análise em todas as moedas para um timeframe."""
    agora = time.time(); enviados = 0
    _diag_buffer["ciclos"] += 1
    cooldown = max(tf_para_minutos(tf) * 60, 7200)
    candidatos = []
    watchlist  = []
    risco_ciclo  = 0.0; scouts_enviados = 0
    longs_enviados = 0; shorts_enviados = 0

    todos_candles = await _prefetch_lote(session, moedas, tf)
    todos_h4      = None
    if tf in ("1h", "30m", "15m"):
        log.info(f"[{tf}] Buscando H4 de {len(moedas)} moedas para filtro de direção...")
        todos_h4 = await _prefetch_lote(session, moedas, "4h")

    # BTC macro H4 — direção global para bloquear SURGE noturno
    _btc_bull_flex = _btc_bear_flex = False
    btc_c4 = await buscar_candles(session, "BTCUSDT", "4h")
    if btc_c4 and len(btc_c4) >= 50:
        _bc = [c["c"] for c in btc_c4]
        _be21 = serie_ema(_bc, 21)[-1]; _be50 = serie_ema(_bc, 50)[-1]
        _be200 = serie_ema(_bc, 200)[-1]; _bp = _bc[-1]
        _btc_bull_flex = _bp > _be21 > _be50 and _bp > _be200 * 0.98
        _btc_bear_flex = _bp < _be21 < _be50 and _bp < _be200 * 1.02

    # BTC no TF atual — filtro direcional obrigatório para BREAKOUT, SURGE, SCOUT
    _btc15_bull = _btc15_bear = False
    btc_ctf = await buscar_candles(session, "BTCUSDT", tf)
    if btc_ctf and len(btc_ctf) >= 50:
        _bc15 = [c["c"] for c in btc_ctf]
        _be10_tf = serie_ema(_bc15, 10)[-1]
        _be21_tf = serie_ema(_bc15, 21)[-1]
        _be50_tf = serie_ema(_bc15, 50)[-1]
        _bp15    = _bc15[-1]
        _btc15_bull = _bp15 > _be50_tf and _be10_tf > _be21_tf
        _btc15_bear = _bp15 < _be50_tf and _be10_tf < _be21_tf
        log.info(f"[{tf}] BTC {tf}: {'BULL ↑' if _btc15_bull else 'BEAR ↓' if _btc15_bear else 'NEUTRO'} | ${_bp15:.0f}")

    funding_rates, oi_atual = await buscar_contract_data(session)

    # Calcula variação % do OI em relação ao ciclo anterior (persiste no estado)
    oi_change = {}
    for sym_oi, oi in oi_atual.items():
        prev = estado.get(f"oi_{sym_oi}")
        if prev and prev > 0:
            oi_change[sym_oi] = (oi - prev) / prev * 100
        estado[f"oi_{sym_oi}"] = oi

    for (sym, label, abrev), candles, h4c in zip(
            moedas, todos_candles,
            todos_h4 if todos_h4 else [None]*len(moedas)):

        if enviados >= MAX_SINAIS_POR_CICLO:
            log.info(f"[{tf}] Limite de {MAX_SINAIS_POR_CICLO} sinais por ciclo atingido")
            break
        if not candles: continue

        result = analisar(sym, candles, funding_rate=funding_rates.get(sym))
        if not result: continue
        grade = result.get("grade", "B")

        atr_pct = (result["atr"] / result["preco"]) * 100 if result["preco"] else 0
        _fonte_pre  = result.get("fonte_sinal", "")
        _atr_limite = 8.0 if _fonte_pre in ("SURGE", "BREAKOUT", "PUMP", "DUMP") else 6.0 if _fonte_pre == "PREMIUM" else 4.0
        if atr_pct > _atr_limite:
            log.info(f"[{tf}] {abrev:7s} | ATR {atr_pct:.1f}% > {_atr_limite:.0f}% — muito volátil, ignorando")
            continue
        if FILTER_LEVEL >= 1 and atr_pct < 0.30:
            log.info(f"[{tf}] {abrev:7s} | ATR {atr_pct:.2f}% < 0.30% — stop justo demais, TPs inválidos no fill")
            candidatos.append((abs(result["score"]), abrev, result["score"],
                               result["rsi"], result["adx"], f"ATR justo {atr_pct:.2f}%"))
            continue

        log.info(f"[{tf}] {abrev:7s} | Score {result['score']:+4d} | RSI {result['rsi']:5.1f} | "
                 f"ADX {result['adx']:5.1f} | K:{'UP' if result['kalman_subindo'] else 'DN'} | "
                 f"Grade:{grade} | {result['fonte_sinal'] or result['sinal'] or '—'}")

        # Diagnóstico: acumula bloqueadores quando não há sinal
        _diag_buffer["total_analisados"] += 1
        if not result["sinal"] and abs(result.get("score", 0)) >= 30:
            _bloqs = _detectar_bloqueadores_diag(result)
            for _b in _bloqs:
                _diag_buffer["bloqueadores"][_b] = _diag_buffer["bloqueadores"].get(_b, 0) + 1
            _diag_buffer["candidatos"].append(
                (abs(result["score"]), abrev, result["score"], result["rsi"], result["adx"], tf, _bloqs)
            )

        if result["sinal"]:
            fonte    = result.get("fonte_sinal", "")

            # Pump extremo: RVOL ≥3x (tier 4) → sinais normais bloqueados.
            # Só especialistas operam em pump/dump: PUMP, DUMP, SURGE, BREAKOUT, REVERSAL, SM_SWEEP.
            _pump_tier = result.get("rvol_tier_max2", 0)
            _sinais_pump_veto = {"SCOUT", "FLEX", "SETUP", "DIV", "REBOUND", "CROSS"}
            if _pump_tier >= 4 and fonte in _sinais_pump_veto:
                log.info(f"  🚫 {abrev} [{tf}] {fonte} vetado — pump extremo (RVOL tier {_pump_tier}=3x+)")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], f"pump_veto({fonte})"))
                continue

            # Sinais de reversão extrema têm piso de score menor (mercado em pânico/euforia)
            _score_min = 60 if fonte == "PREMIUM" else 20 if fonte == "DUMP" else 30 if fonte in ("REVERSAL", "SM_SWEEP", "DIV", "CORE") else 35 if fonte in ("BREAKOUT", "PUMP") else 40
            if abs(result["score"]) < _score_min:
                log.info(f"  ⚠️ {abrev} bloqueado — score {result['score']:+d} < {_score_min}")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], f"score<{_score_min}"))
                continue

            eh_long_ = result["sinal"] == "LONG"
            score_inst = result.get("score_inst_long" if eh_long_ else "score_inst_short", 0)

            # Near-miss tracking: captura candidatos sérios com ≤2 bloqueadores
            _bloqs_nm = _detectar_bloqueadores_diag(result)
            if len(_bloqs_nm) <= 2 and score_inst >= 45:
                _nearmiss_buffer.append((
                    score_inst, abrev, tf,
                    " + ".join(_bloqs_nm[:2]) if _bloqs_nm else "aguardando confirmacao",
                    result["rsi"], result.get("fonte_sinal", "?"), result["sinal"]
                ))

            # H4 penalidade: não bloqueia, mas aumenta exigência (+5 inst, -10 conf, -25% lev)
            _h4_penalty = (tf in ("1h", "15m", "30m") and
                           not _h4_confirma(h4c, result["sinal"], score_inst, result.get("rvol", 1.0)))
            if _h4_penalty:
                log.info(f"  ⚠️ {abrev} [{tf}] {result['sinal']} H4 oposto — penalidade: inst+5, conf-10, lev-25%")

            _hora_c   = datetime.now(timezone.utc).hour
            _sessao_perigosa = _hora_c >= 22 or _hora_c < 8   # Asian / madrugada UTC
            _abertura_falsa  = _hora_c in (8, 13)             # abertura Londres/NY (primeiros 30min)
            # Piso por tipo de sinal — qualidade exigida proporcional à robustez do setup
            _inst_min = (0   if FILTER_LEVEL <= 0 else
                         70  if fonte == "PREMIUM" else
                         15  if fonte == "EXTREME" else
                         25  if fonte == "CORE" else
                         40  if fonte == "DUMP" else
                         45  if fonte == "REVERSAL" else
                         50  if fonte in ("SM_SWEEP", "DIV") else
                         55  if fonte == "SCOUT" else
                         60  if fonte == "FLEX" else
                         55  if fonte in ("SETUP", "PULLBACK", "CROSS",
                                          "BB_BREAK", "SURGE", "BREAKOUT",
                                          "REBOUND", "PUMP") else
                         60  if fonte == "MOMENTUM" else
                         55)
            if FILTER_LEVEL >= 1 and (_sessao_perigosa or _abertura_falsa):
                _inst_min = min(_inst_min + 10, 70)   # sessão perigosa: +10 pts (cap 70)
            if _h4_penalty:
                _inst_min = min(_inst_min + 5, 70)    # H4 oposto: +5 pts (cap 70)
            # Ajuste profissional: funding rate e OI alinhados confirmam smart money
            _fr = result.get("funding_rate") or 0
            _oi = oi_change.get(sym, 0) or 0
            _eh_long_c = result["sinal"] == "LONG"
            _fr_alinhado = (_fr > 0.0005 and not _eh_long_c) or (_fr < -0.0005 and _eh_long_c)
            _oi_alinhado = _oi > 2.0  # OI cresceu >2% = posições novas sendo abertas
            if FILTER_LEVEL >= 1:
                if _fr_alinhado:   _inst_min = max(0, _inst_min - 5)   # funding confirma = -5 pts exigência
                if _oi_alinhado:   _inst_min = max(0, _inst_min - 5)   # OI confirma = -5 pts exigência
            if score_inst < _inst_min:
                _fr_str = f" fr={_fr*100:.3f}%" if _fr else ""
                log.info(f"  ⚠️ {abrev} bloqueado — Score Inst {score_inst} < {_inst_min}{_fr_str}")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], f"inst<{_inst_min}"))
                continue

            # Confiança mínima 55% para qualquer sinal (exceto REVERSAL e SM_SWEEP)
            _conf_global = max(40, min(95, score_inst * 3 // 4))
            if _h4_penalty:
                _conf_global = max(40, _conf_global - 10)   # H4 oposto: -10% confiança
            if FILTER_LEVEL >= 1 and _conf_global < 55 and fonte not in {"REVERSAL", "SM_SWEEP", "EXTREME"}:
                log.info(f"  ⚠️ {abrev} bloqueado — confiança {_conf_global}% < 55% (inst={score_inst})")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], f"conf<55%({_conf_global}%)"))
                continue

            # ── PROTEÇÃO TOPO/FUNDO REAL: apenas extremo absoluto (5 condições simultâneas) ──
            if FILTER_LEVEL >= 1 and fonte not in {"EXTREME", "REVERSAL", "SM_SWEEP"}:
                _rsi_blq   = result.get("rsi", 50)
                _preco_blq = result.get("preco", 0)
                _e21_blq   = result.get("e21", 0)
                _stoch_blq = result.get("stoch_rsi", 0.5)
                _vsec_blq  = result.get("vol_secando", False)
                _liqt_blq  = result.get("liq_topo", False)
                _liqf_blq  = result.get("liq_fundo", False)
                if _e21_blq > 0:
                    _dist_blq = (_preco_blq - _e21_blq) / _e21_blq
                    if (eh_long_ and _rsi_blq > 75 and _dist_blq > 0.08 and
                            _stoch_blq > 0.95 and _vsec_blq and _liqt_blq):
                        log.info(f"  🚫 {abrev} [{tf}] LONG bloqueado — topo real (5 cond): RSI{_rsi_blq:.0f} +{_dist_blq*100:.1f}%>EMA21 StochRSI{_stoch_blq:.2f} vol_sec liq_topo")
                        candidatos.append((abs(result["score"]), abrev, result["score"],
                                           result["rsi"], result["adx"], f"prot-topo-real(RSI{_rsi_blq:.0f})"))
                        continue
                    if (not eh_long_ and _rsi_blq < 25 and _dist_blq < -0.08 and
                            _stoch_blq < 0.05 and _vsec_blq and _liqf_blq):
                        log.info(f"  🚫 {abrev} [{tf}] SHORT bloqueado — fundo real (5 cond): RSI{_rsi_blq:.0f} {_dist_blq*100:.1f}%<EMA21 StochRSI{_stoch_blq:.2f} vol_sec liq_fundo")
                        candidatos.append((abs(result["score"]), abrev, result["score"],
                                           result["rsi"], result["adx"], f"prot-fundo-real(RSI{_rsi_blq:.0f})"))
                        continue

            # ── Gate qualidade LONG — condições obrigatórias ─────────────────
            if eh_long_ and FILTER_LEVEL >= 1 and fonte not in {"REVERSAL", "SM_SWEEP", "EXTREME"}:
                _e10_g   = result.get("e10", 0)
                _e21_g   = result.get("e21", 0)
                _adx_g   = result.get("adx", 0)
                _rvol_g  = result.get("rvol", 0)
                _preco_g = result.get("preco", 0)
                _atr_g   = result.get("atr", 0)
                _sh_g    = result.get("swing_high", float("inf"))
                _bloq_gate = []
                # Resistência mais urgente — verifica primeiro
                if _sh_g > 0 and _preco_g > 0 and _preco_g > _sh_g * 0.998:
                    _bloq_gate.append(f"ENTRANDO EM RESISTENCIA (preco>{_sh_g:.6f}*0.998)")
                if _e10_g > 0 and _e21_g > 0 and _e10_g <= _e21_g:
                    _bloq_gate.append(f"EMA10 {_e10_g:.4f} <= EMA21 {_e21_g:.4f}")
                if _adx_g <= 18:
                    _bloq_gate.append(f"ADX {_adx_g:.0f}<=18")
                if _rvol_g < 1.3:
                    _bloq_gate.append(f"RVOL {_rvol_g:.2f}x<1.3")
                if _e21_g > 0 and _preco_g > _e21_g * 1.04:
                    _bloq_gate.append(f"preco {_preco_g:.4f} > EMA21*1.04")
                if _sh_g < float("inf") and _preco_g > 0 and _atr_g > 0 and (_sh_g - _preco_g) <= _atr_g * 0.5:
                    _bloq_gate.append(f"resistencia <0.5ATR (dist={(_sh_g-_preco_g)/_atr_g:.2f}ATR)")
                if _bloq_gate:
                    log.info(f"  🚫 {abrev} [{tf}] LONG gate — {_bloq_gate[0]}")
                    candidatos.append((abs(result["score"]), abrev, result["score"],
                                       result["rsi"], result["adx"], f"gate({_bloq_gate[0]})"))
                    continue

            # ── Filtros ANTI-TOPO para sinais LONG ───────────────────────────
            if eh_long_ and FILTER_LEVEL >= 1:
                _rsi_l   = result.get("rsi", 50)
                _rvol_l  = result.get("rvol", 1.0)
                _liq_t   = result.get("liq_topo", False)
                _stoch_l = result.get("stoch_rsi", 0.5)
                _preco_l = result.get("preco", 0)
                _e21_l   = result.get("e21", 0)
                _acima   = result.get("preco_acima_e21", True)
                _bloq_topo = []
                # 1. RSI>68 E preço >EMA21*1.05
                if _rsi_l > 68 and _e21_l > 0 and _preco_l > _e21_l * 1.05:
                    _bloq_topo.append(f"RSI {_rsi_l:.0f}>68 + preco>EMA21*1.05")
                # 2. RSI>72 (sobrecomprado)
                if _rsi_l > 72:
                    _bloq_topo.append(f"RSI {_rsi_l:.0f}>72")
                # 3. LIQ_TOPO ativo
                if _liq_t:
                    _bloq_topo.append("LIQ_TOPO")
                # 4. StochRSI > 0.90
                if _stoch_l > 0.90:
                    _bloq_topo.append(f"StochRSI {_stoch_l:.2f}>0.90")
                if _bloq_topo:
                    log.info(f"  🚫 {abrev} [{tf}] LONG anti-topo — {_bloq_topo[0]}")
                    candidatos.append((abs(result["score"]), abrev, result["score"],
                                       result["rsi"], result["adx"], f"anti-topo({_bloq_topo[0]})"))
                    continue

            # ── Filtros ANTI-FUNDO para sinais SHORT ─────────────────────────
            if not eh_long_ and FILTER_LEVEL >= 1:
                _rsi_s   = result.get("rsi", 50)
                _rvol_s  = result.get("rvol", 1.0)
                _liq_f   = result.get("liq_fundo", False)
                _stoch_s = result.get("stoch_rsi", 0.5)
                _bloq_fundo = []
                _exceto_fundo = {"REVERSAL", "SM_SWEEP", "DUMP"}
                _exceto_rvol  = {"REVERSAL", "SM_SWEEP", "CORE", "DIV"}
                # 1. RSI < 35 (sobrevendido)
                if _rsi_s < 35 and fonte not in _exceto_fundo:
                    _bloq_fundo.append(f"RSI {_rsi_s:.0f}<35 (sobrevendido)")
                # 2. LIQ_FUNDO ativo
                if _liq_f and fonte not in _exceto_fundo:
                    _bloq_fundo.append("LIQ_FUNDO")
                # 3. StochRSI < 0.10
                if _stoch_s < 0.10 and fonte not in _exceto_fundo:
                    _bloq_fundo.append(f"StochRSI {_stoch_s:.2f}<0.10")
                # 4. RVOL < 1.0
                if _rvol_s < 1.0 and fonte not in _exceto_rvol:
                    _bloq_fundo.append(f"RVOL {_rvol_s:.2f}x<1.0")
                if _bloq_fundo:
                    log.info(f"  🚫 {abrev} [{tf}] SHORT anti-fundo — {_bloq_fundo[0]}")
                    candidatos.append((abs(result["score"]), abrev, result["score"],
                                       result["rsi"], result["adx"], f"anti-fundo({_bloq_fundo[0]})"))
                    continue

            # BTC no TF atual: BREAKOUT, SURGE, SCOUT obrigam alinhamento direcional com BTC
            if fonte in ("BREAKOUT", "SURGE", "SCOUT"):
                if eh_long_ and not _btc15_bull:
                    log.info(f"  🚫 {abrev} [{tf}] {fonte} LONG bloq — BTC {tf} não bull")
                    candidatos.append((abs(result["score"]), abrev, result["score"],
                                       result["rsi"], result["adx"], f"BTC não bull"))
                    continue
                if not eh_long_ and not _btc15_bear:
                    log.info(f"  🚫 {abrev} [{tf}] {fonte} SHORT bloq — BTC {tf} não bear")
                    candidatos.append((abs(result["score"]), abrev, result["score"],
                                       result["rsi"], result["adx"], f"BTC não bear"))
                    continue

            chave_dir = f"{sym}_{tf}_{result['sinal']}"
            chave_any = f"{sym}_{tf}"
            bloq_dir  = agora - estado.get(chave_dir, 0) < cooldown
            bloq_flip = agora - estado.get(chave_any, 0) < 7200
            if bloq_dir or bloq_flip:
                if bloq_dir:
                    mins = int((cooldown - (agora - estado.get(chave_dir, 0))) / 60)
                    log.info(f"  ⏳ {abrev} [{tf}] cooldown {mins}min")
                else:
                    mins = int((7200 - (agora - estado.get(chave_any, 0))) / 60)
                    log.info(f"  ⏳ {abrev} [{tf}] cooldown {mins}min")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], "cooldown"))
                continue

            eh_long  = result["sinal"] == "LONG"

            # PREMIUM: grade por inst+ADX+RVOL; risco conservador (S+=3%, S=2%, A=1%)
            if fonte == "PREMIUM":
                _pi = result.get("score_inst_long" if eh_long else "score_inst_short", 0)
                _pa = result.get("adx", 0)
                _pr = result.get("rvol_tier_max2", 0)
                if _pi >= 85 and _pa >= 30 and _pr >= 4:
                    grade = "S+"
                elif _pi >= 75:
                    grade = "S"
                else:
                    grade = "A"
                pct_risco = 0.03 if grade == "S+" else 0.02 if grade == "S" else 0.01
            else:
                pct_risco = RISK_SCOUT if fonte == "SCOUT" else RISK_BY_GRADE.get(grade, RISK_PCT)
            # Sinais de alta volatilidade: capa risco em 2%
            if fonte in ("SURGE", "BREAKOUT", "PUMP", "DUMP"):
                pct_risco = min(pct_risco, 0.02)  # risco máx 2% — moves rápidos e violentos

            if risco_ciclo + pct_risco > MAX_CYCLE_RISK:
                log.info(f"  🛑 {abrev} bloqueado — risco ciclo {risco_ciclo*100:.0f}%+{pct_risco*100:.0f}% > teto")
                continue
            if fonte == "SCOUT" and scouts_enviados >= MAX_SCOUT_PER_CYCLE:
                log.info(f"  🔵 {abrev} SCOUT bloqueado — limite {MAX_SCOUT_PER_CYCLE}/ciclo")
                continue
            if eh_long and longs_enviados >= MAX_LONG_PER_CYCLE:
                log.info(f"  📊 {abrev} LONG bloqueado — correlação ({MAX_LONG_PER_CYCLE}/ciclo)")
                continue
            if not eh_long and shorts_enviados >= MAX_SHORT_PER_CYCLE:
                log.info(f"  📊 {abrev} SHORT bloqueado — correlação ({MAX_SHORT_PER_CYCLE}/ciclo)")
                continue

            _rvol      = result.get("rvol", 1.0)
            _rsi       = result.get("rsi", 50)
            _dna       = result.get("dna_flow_bull" if eh_long else "dna_flow_bear", False)
            _trl       = result.get("trendilo_long" if eh_long else "trendilo_short", False)
            _tend      = result.get("tendencia", "NEUTRO")
            _hora_utc  = datetime.now(timezone.utc).hour
            _baixa_liq    = 22 <= _hora_utc or _hora_utc < 8    # Asian/madrugada UTC
            _aber_falsa   = _hora_utc in (8, 13)               # abertura Londres/NY

            # SURGE noturno: breakout falso em sessão de baixa liquidez sem BTC ALTA
            if fonte == "SURGE" and _baixa_liq:
                if eh_long and not _btc_bull_flex:
                    log.info(f"  🚫 {abrev} SURGE LONG bloq — noturno ({_hora_utc:02d}h UTC) BTC não ALTA")
                    candidatos.append((abs(result["score"]), abrev, result["score"],
                                       result["rsi"], result["adx"], "SURGE noturno"))
                    continue
                if not eh_long and not _btc_bear_flex:
                    log.info(f"  🚫 {abrev} SURGE SHORT bloq — noturno ({_hora_utc:02d}h UTC) BTC não BAIXA")
                    candidatos.append((abs(result["score"]), abrev, result["score"],
                                       result["rsi"], result["adx"], "SURGE noturno"))
                    continue
            _sombra_sup   = result.get("sombra_sup", 0.0)
            _sombra_inf   = result.get("sombra_inf", 0.0)
            _liq_topo_r   = result.get("liq_topo", False)
            _liq_fundo_r  = result.get("liq_fundo", False)
            _armadilha = []
            if _rvol < 0.80:
                _armadilha.append("volume fraco")
            if fonte == "BB_BREAK" and _rvol < 1.0:
                _armadilha.append("BB break sem volume")
            if eh_long and _rsi >= 50:
                _armadilha.append(f"RSI {_rsi:.0f} elevado para LONG")
            if not eh_long and _rsi <= 50:
                _armadilha.append(f"RSI {_rsi:.0f} baixo para SHORT")
            if not _dna and not _trl:
                _armadilha.append("fluxo não confirmado")
            if _tend == "NEUTRO":
                _armadilha.append("tendência lateral")
            if eh_long and _sombra_sup > 0.35:
                _armadilha.append("pavio de rejeição no topo")
            if not eh_long and _sombra_inf > 0.35:
                _armadilha.append("pavio de rejeição no fundo")
            if eh_long and _liq_topo_r:
                _armadilha.append("varredura de topo detectada")
            if not eh_long and _liq_fundo_r:
                _armadilha.append("varredura de fundo detectada")
            if _baixa_liq:
                _armadilha.append(f"sessão baixa liquidez ({_hora_utc:02d}h UTC)")
            if _aber_falsa:
                _armadilha.append(f"abertura {'Londres' if _hora_utc == 8 else 'NY'} — 30min de risco")

            # FLEX: qualidade equilibrada — aberto mas com DNA/Trendilo, RVOL, RSI e estrutura
            if fonte == "FLEX" and FILTER_LEVEL >= 1:
                _rsi_flex  = result.get("rsi", 50)
                _rvol_flex = result.get("rvol", 0.0)
                _adx_flex  = result.get("adx", 0)
                _obv_bull  = result.get("obv_bull", False)
                _obv_bear  = result.get("obv_bear", False)
                _preco_f   = result.get("preco", 0)
                _e50_f     = result.get("e50", 0)
                _tbull     = result.get("tbull_loose", False)
                _tbear     = result.get("tbear_loose", False)
                _liq_t_f   = result.get("liq_topo", False)
                _liq_f_f   = result.get("liq_fundo", False)
                _bloq_flex = []
                # Critérios comuns LONG e SHORT
                if _rvol_flex < 0.8:
                    _bloq_flex.append(f"RVOL {_rvol_flex:.2f}x<0.8")
                if _adx_flex < 16:
                    _bloq_flex.append(f"ADX {_adx_flex:.0f}<16")
                if not _dna and not _trl:
                    _bloq_flex.append("sem DNA Flow nem Trendilo")
                if eh_long:
                    # RSI 38–70 para LONG
                    if not (38 <= _rsi_flex <= 70):
                        _bloq_flex.append(f"RSI {_rsi_flex:.0f} fora 38-70 (LONG)")
                    if _e50_f > 0 and _preco_f < _e50_f:
                        _bloq_flex.append("preco abaixo MM50")
                    if not _tbull:
                        _bloq_flex.append("MM10>MM21>MM50 nao alinhada")
                    if not _obv_bull:
                        _bloq_flex.append("OBV nao positivo")
                    if _liq_t_f:
                        _bloq_flex.append("resistencia <1ATR (liq topo)")
                else:
                    # RSI 32–65 para SHORT
                    if not (32 <= _rsi_flex <= 65):
                        _bloq_flex.append(f"RSI {_rsi_flex:.0f} fora 32-65 (SHORT)")
                    if _e50_f > 0 and _preco_f > _e50_f:
                        _bloq_flex.append("preco acima MM50")
                    if not _tbear:
                        _bloq_flex.append("MM10<MM21<MM50 nao alinhada")
                    if not _obv_bear:
                        _bloq_flex.append("OBV nao negativo")
                    if _liq_f_f:
                        _bloq_flex.append("suporte <1ATR (liq fundo)")
                if _bloq_flex:
                    log.info(f"  🚫 {abrev} FLEX bloqueado — {' | '.join(_bloq_flex)}")
                    candidatos.append((abs(result["score"]), abrev, result["score"],
                                       result["rsi"], result["adx"], f"FLEX({_bloq_flex[0]})"))
                    continue

            # SURGE / BREAKOUT / PUMP: filtros específicos por tipo
            if fonte in ("SURGE", "BREAKOUT", "PUMP") and FILTER_LEVEL >= 1:
                _rsi_exp   = result.get("rsi", 50)
                _rvol_exp  = result.get("rvol", 0.0)
                _adx_exp   = result.get("adx", 0)
                _bloq_exp  = []
                _rvol_min  = 1.3 if fonte == "BREAKOUT" else 2.5  # BREAKOUT: 1.3x; SURGE/PUMP: 2.5x
                _rsi_max   = 68  if fonte == "BREAKOUT" else 65   # BREAKOUT: RSI até 68
                if _rvol_exp < _rvol_min:
                    _bloq_exp.append(f"RVOL {_rvol_exp:.2f}x<{_rvol_min}")
                if _adx_exp < 22:
                    _bloq_exp.append(f"ADX {_adx_exp:.0f}<22")
                if not (45 <= _rsi_exp <= _rsi_max):
                    _bloq_exp.append(f"RSI {_rsi_exp:.0f} fora 45-{_rsi_max}")
                if not _dna:
                    _bloq_exp.append("DNA Flow ausente")
                if _bloq_exp:
                    log.info(f"  🚫 {abrev} {fonte} bloqueado — {' | '.join(_bloq_exp)}")
                    candidatos.append((abs(result["score"]), abrev, result["score"],
                                       result["rsi"], result["adx"], f"{fonte}({_bloq_exp[0]})"))
                    continue

            extra = {
                "rvol_label":   result.get("rvol_label", ""),
                "rvol":         _rvol,
                "inst_score":   result.get("score_inst_long" if eh_long else "score_inst_short", 0),
                "inst_cls":     result.get("cls_inst_long"   if eh_long else "cls_inst_short",   ""),
                "dna_flow":     _dna,
                "trendilo_dir": _trl,
                "liq_event":    ("LIQ FUNDO ↑" if result.get("liq_fundo") else
                                 "LIQ TOPO ↓"  if result.get("liq_topo")  else ""),
                "funding_rate": result.get("funding_rate"),
                "oi_change":    oi_change.get(sym),
                "armadilha":    _armadilha,
                "e21":          result.get("e21", 0),
                "e50":          result.get("e50", 0),
                "high_atual":   result.get("high_atual", 0),
                "low_atual":    result.get("low_atual", 0),
                "h4_penalty":   _h4_penalty,
            }
            ok = await enviar_sinal(session, sym, label, abrev, result["sinal"],
                                    result["preco"], result["atr"], result["score"],
                                    result["rsi"], result["adx"], result["tendencia"],
                                    result["kalman_subindo"], result["swing_low"],
                                    result["swing_high"], result["fonte_sinal"], tf, grade, extra=extra)
            if ok:
                _diag_buffer["ultimo_sinal"] = agora
                estado[chave_dir] = agora
                estado[chave_any] = agora
                salvar_estado(estado)
                risco_ciclo   += pct_risco
                scouts_enviados += 1 if fonte == "SCOUT" else 0
                longs_enviados  += 1 if eh_long else 0
                shorts_enviados += 0 if eh_long else 1
                enviados += 1
        else:
            candidatos.append((result["score"], abrev, result["score"],
                               result["rsi"], result["adx"], result.get("fonte_sinal", "sem-sinal")))
            sc  = result["score"]; rsi = result["rsi"]; adx = result["adx"]
            dfl = result.get("dna_flex_bull", False); dfs = result.get("dna_flex_bear", False)
            trl = result.get("trendilo_long", False);  trs = result.get("trendilo_short", False)
            kal = result.get("kalman_subindo", False)
            if sc > 12  and rsi < 55 and adx >= 8 and (kal or trl or dfl or sc > 40):
                watchlist.append(("LONG",  abrev, sc, rsi, adx, dfl, trl))
            elif sc < -12 and rsi > 40 and adx >= 8 and (not kal or trs or dfs or sc < -40):
                watchlist.append(("SHORT", abrev, sc, rsi, adx, dfs, trs))

    if enviados == 0 and candidatos:
        top_long  = sorted([c for c in candidatos if c[2] > 0],  key=lambda x: x[2], reverse=True)[:3]
        top_short = sorted([c for c in candidatos if c[2] < 0],  key=lambda x: x[2])[:3]
        linhas = []
        if top_long:
            melhor_adx = max(adx for _,_,_,_,adx,_ in top_long)
            motivo = ("🔴 RSI sobrecomprado" if top_long[0][3] >= 65
                      else "📉 ADX baixo" if melhor_adx < 17
                      else "📊 Score baixo" if top_long[0][2] < 50
                      else "⏳ MACD/HA pendente")
            linhas.append(f"📈 LONG — {motivo}")
            linhas += [f"  {s}: {sc:+d} | RSI {rsi:.0f} | ADX {adx:.0f}" for _,s,sc,rsi,adx,_ in top_long]
        if top_short:
            melhor_adx = max(adx for _,_,_,_,adx,_ in top_short)
            motivo = ("🔴 RSI sobrevendido" if top_short[0][3] <= 40
                      else "📉 ADX baixo" if melhor_adx < 17
                      else "📊 Score baixo" if top_short[0][2] > -50
                      else "⏳ MACD/HA pendente")
            linhas.append(f"📉 SHORT — {motivo}")
            linhas += [f"  {s}: {sc:+d} | RSI {rsi:.0f} | ADX {adx:.0f}" for _,s,sc,rsi,adx,_ in top_short]
        if linhas:
            log.info(f"[{tf}] Sem sinais — " + " | ".join(linhas[:3]))

    log.info(f"[{tf}] Watchlist: {len(watchlist)} moedas encontradas (envio desativado)")
    # Watchlist desativada — apenas sinais LONG/SHORT são enviados ao Telegram

    return enviados


# ── Ciclo MTF (H4 → H1) ──────────────────────────────────────────────────────

async def executar_ciclo_mtf(session, estado, moedas):
    """Ciclo multi-timeframe: analisa H4 para direção → entra na H1."""
    agora = time.time(); enviados = 0
    cooldown_mtf = 14400
    setups_h4 = []

    # Filtro BTC macro em H4
    btc_bull = btc_bear = btc_rsi_quente = btc_rsi_panico = False
    btc_rsi  = 50; btc_p = 0
    btc_candles = await buscar_candles(session, "BTCUSDT", "4h")
    if btc_candles and len(btc_candles) >= 50:
        btc_c   = [c["c"] for c in btc_candles]
        btc_e21 = serie_ema(btc_c, 21)[-1]; btc_e50 = serie_ema(btc_c, 50)[-1]
        btc_e200 = serie_ema(btc_c, 200)[-1]; btc_p = btc_c[-1]
        btc_rsi  = calcular_rsi(btc_c[-50:])
        btc_bull = btc_p > btc_e21 > btc_e50 and btc_p > btc_e200 * 0.98
        btc_bear = btc_p < btc_e21 < btc_e50 and btc_p < btc_e200 * 1.02 and btc_rsi < 45
        btc_rsi_quente = btc_rsi > 72; btc_rsi_panico = btc_rsi < 28
        log.info(f"[MTF] BTC H4: {'ALTA ↑' if btc_bull else 'BAIXA ↓' if btc_bear else 'NEUTRO'} | "
                 f"RSI {btc_rsi:.0f}{'🔥' if btc_rsi_quente else '🧊' if btc_rsi_panico else ''} | ${btc_p:.0f}")

    log.info(f"[MTF] Prefetch H4 ({len(moedas)} moedas)...")
    todos_h4 = await _prefetch_lote(session, moedas, "4h")

    filtrados = []
    for (sym, label, abrev), candles_h4 in zip(moedas, todos_h4):
        if not candles_h4: continue
        r4h = calcular_indicadores(candles_h4)
        if not r4h: continue
        h4_rsi   = r4h["rsi"]
        h4_vol   = r4h.get("v_forte", False) or r4h.get("obv_bull", False)
        h4_vol_s = r4h.get("v_forte", False) or r4h.get("obv_bear", False)
        h4_bull  = (r4h["score"] > 15 and r4h.get("tbull_r", False) and
                    r4h["adx"] >= 13 and h4_rsi < (75 if r4h["adx"] > 30 else 65) and h4_vol)
        h4_bear  = (r4h.get("tbear_r", False) and r4h["adx"] >= 13 and
                    h4_vol_s and r4h["score"] < -15 and h4_rsi > 43)
        if not (h4_bull or h4_bear):
            log.info(f"[MTF] {abrev:7s} | H4 sem setup | Score {r4h['score']:+d} RSI {h4_rsi:.0f}")
            continue
        direcao = "ALTA" if h4_bull else "BAIXA"
        if abrev not in ("BTC", "WBTC"):
            if h4_bull and btc_bear:
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, "BTC em queda"))
                log.info(f"[MTF] {abrev:7s} | LONG bloqueado — BTC H4 em queda")
                continue
            if h4_bear and btc_bull:
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, "BTC em alta"))
                log.info(f"[MTF] {abrev:7s} | SHORT bloqueado — BTC H4 em alta")
                continue
            if h4_bull and btc_rsi_quente:
                log.info(f"[MTF] {abrev:7s} | LONG bloqueado — BTC RSI {btc_rsi:.0f} > 72 (sobrecomprado)")
                continue
            if h4_bear and btc_rsi_panico:
                log.info(f"[MTF] {abrev:7s} | SHORT bloqueado — BTC RSI {btc_rsi:.0f} < 28 (sobrevendido)")
                continue
        log.info(f"[MTF] {abrev:7s} | H4 {direcao} ✓BTC | Score {r4h['score']:+d} → buscando entrada H1...")
        filtrados.append((sym, label, abrev, r4h, h4_bull, h4_bear))

    if not filtrados:
        log.info("[MTF] Nenhuma moeda com setup H4 válido")
    else:
        log.info(f"[MTF] Prefetch H1 ({len(filtrados)} moedas com setup H4)...")
        moedas_h1 = [(sym, label, abrev) for sym, label, abrev, _, _, _ in filtrados]
        todos_h1  = await _prefetch_lote(session, moedas_h1, "1h")

        from analyze import analisar as _analisar_mtf

        for (sym, label, abrev, r4h, h4_bull, h4_bear), candles_h1 in zip(filtrados, todos_h1):
            h4_rsi  = r4h["rsi"]
            direcao = "ALTA" if h4_bull else "BAIXA"
            if not candles_h1: continue

            # Análise H1 — usa a função completa em modo H1
            result = _analisar_mtf(sym, candles_h1)
            if not result or not result.get("sinal"):
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, "pullback H1 pendente"))
                log.info(f"[MTF] {abrev:7s} | H1 sem entrada (não está no pullback)")
                continue

            grade   = result.get("grade", "A")
            pts     = result.get("pts_grade", 0)
            log.info(f"[MTF] {abrev:7s} | ✅ H1 {result['sinal']} Grade:{grade} Q:{pts} | "
                     f"{result['fonte_sinal']} | RSI {result['rsi']:.1f} | ADX {result['adx']:.1f}")
            eh_long_mtf = result["sinal"] == "LONG"
            score_inst_mtf = result.get("score_inst_long" if eh_long_mtf else "score_inst_short", 0)
            _fonte_mtf = result.get("fonte_sinal", "")
            _score_min_mtf = 40; _inst_min_mtf = 40 if _fonte_mtf == "CORE" else 60
            if abs(result["score"]) < _score_min_mtf or score_inst_mtf < _inst_min_mtf:
                motivo = (f"score {result['score']:+d}<{_score_min_mtf}" if abs(result["score"]) < _score_min_mtf
                          else f"Score Inst {score_inst_mtf}<{_inst_min_mtf}")
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, motivo))
                log.info(f"[MTF] {abrev:7s} | bloqueado — {motivo}")
                continue

            chave        = f"{sym}_MTF"
            chave_global = f"{sym}_GLOBAL"
            if agora - estado.get(chave_global, 0) < 1800:
                mins = int((1800 - (agora - estado.get(chave_global, 0))) / 60)
                log.info(f"  ⏳ {abrev} [MTF] dedup global {mins}min")
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, f"dedup {mins}min"))
                continue
            if agora - estado.get(chave, 0) >= cooldown_mtf:
                eh_long = result["sinal"] == "LONG"
                extra = {
                    "rvol_label":   result.get("rvol_label", ""),
                    "rvol":         result.get("rvol", 0.0),
                    "inst_score":   result.get("score_inst_long" if eh_long else "score_inst_short", 0),
                    "inst_cls":     r4h.get("cls_inst_long"   if eh_long else "cls_inst_short",   ""),
                    "dna_flow":     result.get("dna_flow_bull" if eh_long else "dna_flow_bear", False),
                    "trendilo_dir": result.get("trendilo_long" if eh_long else "trendilo_short", False),
                    "liq_event":    ("LIQ FUNDO ↑" if r4h.get("liq_fundo") else
                                     "LIQ TOPO ↓"  if r4h.get("liq_topo")  else ""),
                    "e21":          result.get("e21", 0),
                    "e50":          result.get("e50", 0),
                    "high_atual":   result.get("high_atual", 0),
                    "low_atual":    result.get("low_atual", 0),
                }
                ok = await enviar_sinal(session, sym, label, abrev, result["sinal"],
                                        result["preco"], result["atr"], r4h["score"],
                                        result["rsi"], result["adx"], result["tendencia"],
                                        result["kalman_subindo"], result["swing_low"],
                                        result["swing_high"], result["fonte_sinal"], "1h", grade, extra=extra)
                if ok:
                    estado[chave] = agora
                    estado[chave_global] = agora
                    salvar_estado(estado)
                    enviados += 1
            else:
                mins = int((cooldown_mtf - (agora - estado.get(chave, 0))) / 60)
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, f"cooldown {mins}min"))
                log.info(f"  ⏳ {abrev} [MTF] cooldown {mins}min")

    if enviados == 0 and btc_bear:
        log.info("🐻 BTC em queda — LONGs bloqueados")
    if enviados == 0 and setups_h4:
        log.info(f"[MTF] {len(setups_h4)} setup(s) H4 ativos sem entrada H1")

    return enviados


# ── Modo de teste ─────────────────────────────────────────────────────────────

async def executar_teste(session):
    """Modo teste: analisa BTC e SOL em 15m com dados reais e envia sinal forçado."""
    log.info("🧪 MODO TESTE — Analisando BTC e SOL em 15m com dados reais...")
    moedas_teste = [("BTCUSDT","BTC/USDT","BTC"), ("SOLUSDT","SOL/USDT","SOL")]
    funding_rates, oi_atual = await buscar_contract_data(session)
    for sym, label, abrev in moedas_teste:
        candles = await buscar_candles(session, sym, "15m")
        if not candles:
            log.warning(f"❌ Sem dados para {abrev}"); continue
        result = analisar(sym, candles, funding_rate=funding_rates.get(sym))
        if not result:
            log.warning(f"❌ Análise falhou para {abrev}"); continue
        grade  = result.get("grade", "B")
        sinal_forcado = "LONG" if result["score"] >= 0 else "SHORT"
        fonte  = result["fonte_sinal"] or f"TESTE({result['score']:+d})"
        log.info(f"🧪 {abrev} | Score {result['score']:+d} | Grade {grade} | Enviando {sinal_forcado}...")
        eh_long = sinal_forcado == "LONG"
        extra = {
            "rvol_label":   result.get("rvol_label", ""),
            "rvol":         result.get("rvol", 0.0),
            "inst_score":   result.get("score_inst_long" if eh_long else "score_inst_short", 0),
            "inst_cls":     result.get("cls_inst_long"   if eh_long else "cls_inst_short",   ""),
            "dna_flow":     result.get("dna_flow_bull"   if eh_long else "dna_flow_bear",  False),
            "trendilo_dir": result.get("trendilo_long"   if eh_long else "trendilo_short", False),
            "liq_event":    ("LIQ FUNDO ↑" if result.get("liq_fundo") else
                             "LIQ TOPO ↓"  if result.get("liq_topo")  else ""),
            "funding_rate": result.get("funding_rate"),
            "oi_change":    None,
            "e21":          result.get("e21", 0),
            "e50":          result.get("e50", 0),
            "high_atual":   result.get("high_atual", 0),
            "low_atual":    result.get("low_atual", 0),
        }
        await enviar_sinal(session, sym, label, abrev, sinal_forcado,
                           result["preco"], result["atr"], result["score"],
                           result["rsi"], result["adx"], result["tendencia"],
                           result["kalman_subindo"], result["swing_low"],
                           result["swing_high"], f"TESTE — {fonte}", "15m", grade, extra=extra)
        await asyncio.sleep(1)
    log.info("✅ Teste concluído — verifique o Telegram!")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    if not TG_TOKEN or not TG_CHATID:
        log.error("❌ Configure TG_TOKEN e TG_CHATID!"); return

    if TEST_MODE:
        log.info("🧪 GAUSS+DNA — MODO TESTE ATIVADO")
        async with aiohttp.ClientSession() as session:
            await executar_teste(session)
        return

    tf_min_base = min(tf_para_minutos(tf) for tf in TIMEFRAMES)
    scan_tf     = TIMEFRAMES[0]
    modo_str    = "LOOP CONTÍNUO" if LOOP_MODE else "EXECUÇÃO ÚNICA"
    scan_str    = "DINÂMICO" if DYNAMIC_SCAN else "LISTA FIXA"
    _flv_desc = {0: "DEBUG (vol20/score25/sem-seguro)", 1: "MINIMO (vol50/sem-SMC)", 2: "MODERADO (vol65/adx_sub)", 3: "COMPLETO (vol80/SMC)"}
    log.info(f"🚀 GAUSS+DNA v3 | {SIGNAL_MODE} | TFs: {','.join(TIMEFRAMES)} | "
             f"Moedas: {scan_str} | {modo_str} | Filtros: {_flv_desc.get(FILTER_LEVEL, FILTER_LEVEL)}")
    log.info("✅ Bot pronto — enviando apenas sinais reais ao Telegram")

    estado        = carregar_estado()
    ciclo         = 0
    # Priority coins sempre na frente, depois restante da lista estática (sem duplicatas)
    _prio_syms    = {s for s, _, _ in PRIORITY_WATCHLIST}
    moedas_ativas = list(PRIORITY_WATCHLIST) + [c for c in COINS if c[0] not in _prio_syms]
    ultimo_scan   = 0
    _agora_ini    = time.time()
    _diag_buffer["ultimo_sinal"] = _agora_ini
    _diag_buffer["ultimo_envio"] = _agora_ini

    async with aiohttp.ClientSession() as session:
        agora_str    = datetime.now().strftime("%H:%M — %d/%m/%Y")
        await notificar(session,
            f"🤖 GAUSS+DNA iniciado\n"
            f"⏰ {agora_str}\n"
            f"📊 TFs: {', '.join(TIMEFRAMES)} | Moedas: {len(COINS)}\n"
            f"🔄 Modo: {modo_str} | Ciclo: {CYCLE_INTERVAL}s\n"
            f"🔧 Filtros nivel {FILTER_LEVEL}: {_flv_desc.get(FILTER_LEVEL, str(FILTER_LEVEL))}"
        )

        # Teste de conectividade
        for url_teste, nome in [
            ("https://api.mexc.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=250", "MEXC 15m"),
            ("https://api.mexc.com/api/v3/klines?symbol=BTCUSDT&interval=60m&limit=250", "MEXC 60m"),
        ]:
            try:
                async with session.get(url_teste, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    corpo = await r.json()
                    log.info(f"✅ {nome}: {len(corpo) if isinstance(corpo, list) else '?'} velas")
            except Exception as e:
                log.warning(f"⚠️ {nome}: {str(e)[:60]}")

        if DYNAMIC_SCAN:
            resultado = await escanear_melhores_moedas(session, scan_tf, min(50, SCANNER_TOP))
            if resultado:
                _scan_syms = {s for s, _, _ in resultado}
                moedas_ativas = list(PRIORITY_WATCHLIST) + [c for c in resultado if c[0] not in _prio_syms]
            ultimo_scan = 0

        while True:
            ciclo += 1

            if LOOP_MODE and ciclo > 1:
                espera = segundos_ate_fechamento(tf_min_base)
                if CYCLE_INTERVAL > 0:
                    espera = min(espera, CYCLE_INTERVAL)
                if espera > 3:
                    log.info(f"⏳ Próximo ciclo em {espera:.0f}s ({espera/60:.1f}min)...")
                    await asyncio.sleep(espera + 2)

            if DYNAMIC_SCAN and ciclo > 1 and (ciclo - ultimo_scan) >= SCAN_EVERY:
                resultado = await escanear_melhores_moedas(session, scan_tf, SCANNER_TOP)
                if resultado:
                    moedas_ativas = list(PRIORITY_WATCHLIST) + [c for c in resultado if c[0] not in _prio_syms]
                ultimo_scan = ciclo

            log.info(f"── Ciclo #{ciclo} | {datetime.now().strftime('%H:%M:%S %d/%m')} | {len(moedas_ativas)} moedas ──")
            total = 0
            try:
                tem_mtf = (("4h" in TIMEFRAMES and "1h" in TIMEFRAMES) or
                           ("1h" in TIMEFRAMES and ("30m" in TIMEFRAMES or "15m" in TIMEFRAMES)))
                if tem_mtf:
                    enviados_mtf = await executar_ciclo_mtf(session, estado, moedas_ativas)
                    total += enviados_mtf
            except Exception as e:
                log.error(f"❌ MTF erro ciclo #{ciclo}: {e}")

            try:
                # Roda FLEX para cada TF que não é 4h (1h incluído — gera sinais diretos H1)
                _tfs_flex = [tf for tf in TIMEFRAMES if tf != "4h"]
                if not _tfs_flex:
                    _tfs_flex = [TIMEFRAMES[0]]
                for tf_base in _tfs_flex:
                    enviados = await executar_ciclo(session, estado, tf_base, moedas_ativas)
                    total   += enviados
                log.info(f"✅ Ciclo #{ciclo} concluído. Sinais: {total}")
            except Exception as e:
                log.error(f"❌ FLEX erro ciclo #{ciclo}: {e}")
            finally:
                salvar_estado(estado)

            if LOOP_MODE and ciclo % 5 == 0:
                log.info(f"💓 Heartbeat ciclo #{ciclo} | {len(moedas_ativas)} moedas")

            # Near-miss: após 90min sem sinal, avisa candidatos mais próximos
            _agora_d = time.time()
            if total > 0:
                _diag_buffer["ultimo_sinal"] = _agora_d
                _nearmiss_buffer.clear()
            _sem_sinal_min = (_agora_d - _diag_buffer["ultimo_sinal"]) / 60
            if _sem_sinal_min >= 90 and _agora_d - _diag_buffer.get("ultimo_envio", 0) >= 5400:
                if _nearmiss_buffer:
                    # Ordena por score_inst e pega os 5 mais próximos
                    top_nm = sorted(_nearmiss_buffer, key=lambda x: x[0], reverse=True)[:5]
                    linhas = [f"⏱ {int(_sem_sinal_min)}min sem sinal — candidatos mais próximos:\n"]
                    for score_i, abrev_i, tf_i, bloq_i, rsi_i, fonte_i, dir_i in top_nm:
                        seta = "↑" if dir_i == "LONG" else "↓"
                        linhas.append(f"{seta} {abrev_i} [{tf_i}] {fonte_i} RSI{rsi_i:.0f} — falta: {bloq_i}")
                    try:
                        await notificar(session, "\n".join(linhas))
                    except Exception:
                        pass
                _diag_buffer["ultimo_envio"] = _agora_d
                _nearmiss_buffer.clear()

            if not LOOP_MODE:
                break
