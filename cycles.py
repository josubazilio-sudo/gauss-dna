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

    _sc_min   = 25 if FILTER_LEVEL <= 0 else 30
    _adx_min  = 10 if FILTER_LEVEL <= 0 else 18
    _fluxo_min = 0 if FILTER_LEVEL <= 0 else 1

    vnf    = result.get("vol_nao_fade", False)
    _obv_b = result.get("obv_bull", False)
    _obv_s = result.get("obv_bear", False)
    kal_up = result.get("kalman_subindo", False)
    kal_dn = result.get("kalman_descendo", False)

    if sc < _sc_min:
        motivos.append("score baixo")
        return motivos

    # RSI zona
    if eh_long_cand and rsi >= 60:
        motivos.append(f"RSI {rsi:.0f} sobrecomprado (LONG bloq)")
    elif not eh_long_cand and rsi <= 40:
        motivos.append(f"RSI {rsi:.0f} sobrevendido (SHORT bloq)")

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

    # Volume SCOUT/FLEX: requer rvol>=1.0 (volume mínimo médio)
    # Fallback OBV/Kalman+Trendilo dispensa piso de RVOL
    _fvok  = result.get("flex_vol_ok" if eh_long_cand else "flex_vol_ok_s", False)
    _flex_v = _fvok and rvol >= 1.0
    _rsi_sub = result.get("rsi_subindo", False)
    _rsi_cai = result.get("rsi_caindo", False)
    _vol_scout_l_ok = ((vnf and rvol >= 1.0) or (_obv_b and (trl_l or kal_up)) or
                       (kal_up and trl_l) or (_obv_b and _rsi_sub))
    _vol_scout_s_ok = ((vnf and rvol >= 1.0) or (_obv_s and (trl_s or kal_dn)) or
                       (kal_dn and trl_s) or (_obv_s and _rsi_cai))
    if eh_long_cand:
        if not _vol_scout_l_ok:
            if vnf and rvol < 1.0:
                motivos.append(f"RVOL < 100% (volume abaixo da média, rvol={rvol:.2f}x)")
            else:
                motivos.append("RVOL < 80%" + (" (FLEX vol✓)" if _flex_v else " (sem OBV+Kal alt)"))
    elif not _vol_scout_s_ok:
        if vnf and rvol < 1.0:
            motivos.append(f"RVOL < 100% (volume abaixo da média, rvol={rvol:.2f}x)")
        else:
            motivos.append("RVOL < 80%" + (" (FLEX vol✓)" if _flex_v else " (sem OBV+Kal alt)"))

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
            motivos.append("seguro=F(" + (",".join(_sg) or "?") + ")")
        elif not eh_long_cand and not seg_s:
            _sg = []
            if result.get("vol_secando"):            _sg.append("vol_sec")
            if result.get("exaustao_fund"):          _sg.append("exaust_fund")
            if result.get("stoch_esticado_down"):    _sg.append(f"stoch<{result.get('stoch_rsi',0):.2f}")
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
        if score_inst < 50:
            motivos.append(f"score_inst={score_inst}<50")
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
        if score_inst < 50:
            motivos.append(f"score_inst={score_inst}<50")
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
            marca = "✓" if rsi > 45 else "↓"
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

def _h4_confirma(candles_h4, direcao):
    """Retorna True se H4 confirma a direção do sinal. Sem H4 → não bloqueia.
    Só bloqueia quando H4 está FORTEMENTE oposto (score < -40 / > 40, ADX > 20).
    H4 neutro ou mildly bearish/bullish não bloqueia — deixa TFs menores operarem."""
    if candles_h4 is None:
        return True
    r4 = calcular_indicadores(candles_h4)
    if not r4:
        return True
    h4_rsi  = r4["rsi"]
    h4_vol  = r4.get("v_forte", False) or r4.get("obv_bull", False)
    h4_vols = r4.get("v_forte", False) or r4.get("obv_bear", False)
    h4_bear_strong = (r4.get("tbear_r", False) and r4["adx"] >= 20 and
                      h4_vols and r4["score"] < -40 and h4_rsi > 45)
    h4_bull_strong = (r4.get("tbull_r", False) and r4["adx"] >= 20 and
                      h4_vol and r4["score"] > 40 and h4_rsi < 65)
    if direcao == "LONG"  and h4_bear_strong: return False
    if direcao == "SHORT" and h4_bull_strong: return False
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
        if atr_pct > 4.0:
            log.info(f"[{tf}] {abrev:7s} | ATR {atr_pct:.1f}% > 4% — muito volátil, ignorando")
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
            # Sinais de reversão extrema têm piso de score menor (mercado em pânico/euforia)
            _score_min = 30 if fonte in ("REVERSAL", "SM_SWEEP", "DIV") else 40
            if abs(result["score"]) < _score_min:
                log.info(f"  ⚠️ {abrev} bloqueado — score {result['score']:+d} < {_score_min}")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], f"score<{_score_min}"))
                continue

            eh_long_ = result["sinal"] == "LONG"
            score_inst = result.get("score_inst_long" if eh_long_ else "score_inst_short", 0)
            _hora_c   = datetime.now(timezone.utc).hour
            _sessao_perigosa = _hora_c >= 22 or _hora_c < 8   # Asian / madrugada UTC
            _abertura_falsa  = _hora_c in (8, 13)             # abertura Londres/NY (primeiros 30min)
            _inst_min = (0  if FILTER_LEVEL <= 0 else
                         55 if fonte == "SCOUT" else 50)
            if FILTER_LEVEL >= 1 and (_sessao_perigosa or _abertura_falsa):
                _inst_min = max(_inst_min, 60)   # sessão perigosa: exige confirmação institucional forte
            if score_inst < _inst_min:
                log.info(f"  ⚠️ {abrev} bloqueado — Score Inst {score_inst} < {_inst_min}")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], f"inst<{_inst_min}"))
                continue
            if grade == "B":
                log.info(f"  ⚠️ {abrev} bloqueado — Grade B descartado")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], "Grade B descartado"))
                continue
            if (result["sinal"] == "LONG" and
                    fonte not in ("REBOUND", "REVERSAL") and
                    result.get("rsi_caindo", False)):
                # Exceção breakout: RVOL>=1.5 + score>=75 — movimento institucional forte
                _flex_break_exc = (fonte == "FLEX" and result.get("rvol", 0) >= 1.5 and abs(result.get("score", 0)) >= 75)
                # Exceção zona: RSI já está dentro da janela ideal 45-55 — caindo dentro da zona não invalida
                _flex_zona_exc  = (fonte == "FLEX" and 45 < result.get("rsi", 0) < 55)
                if not _flex_break_exc and not _flex_zona_exc:
                    log.info(f"  🚫 {abrev} LONG bloqueado — RSI caindo ({result['rsi']:.0f} < ant {result.get('rsi_ant',0):.0f})")
                    candidatos.append((abs(result["score"]), abrev, result["score"],
                                       result["rsi"], result["adx"], f"RSI caindo LONG bloq"))
                    continue

            if tf in ("1h", "15m", "30m") and not _h4_confirma(h4c, result["sinal"]):
                log.info(f"  🚫 {abrev} [{tf}] {result['sinal']} bloqueado — H4 oposto")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], "H4 oposto"))
                continue

            chave_dir    = f"{sym}_{tf}_{result['sinal']}"
            chave_any    = f"{sym}_{tf}"
            chave_global = f"{sym}_GLOBAL"
            bloq_global = agora - estado.get(chave_global, 0) < 1800
            bloq_dir  = agora - estado.get(chave_dir, 0) < cooldown
            bloq_flip = agora - estado.get(chave_any, 0) < 7200
            if bloq_global or bloq_dir or bloq_flip:
                if bloq_global:
                    mins = int((1800 - (agora - estado.get(chave_global, 0))) / 60)
                    log.info(f"  ⏳ {abrev} [{tf}] dedup global {mins}min")
                elif bloq_dir:
                    mins = int((cooldown - (agora - estado.get(chave_dir, 0))) / 60)
                    log.info(f"  ⏳ {abrev} [{tf}] cooldown {mins}min")
                else:
                    mins = int((7200 - (agora - estado.get(chave_any, 0))) / 60)
                    log.info(f"  ⏳ {abrev} [{tf}] cooldown {mins}min")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], "cooldown"))
                continue

            eh_long  = result["sinal"] == "LONG"
            pct_risco = RISK_SCOUT if fonte == "SCOUT" else RISK_BY_GRADE.get(grade, RISK_PCT)
            # SURGE: capa risco em 2% — breakout pode reverter com velocidade
            if fonte == "SURGE":
                pct_risco = min(pct_risco, 0.02)

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
            _score_inst = result.get("score_inst_long" if eh_long else "score_inst_short", 0)
            _armadilha = []
            if _rvol < 0.80:
                _armadilha.append("volume fraco")
            if fonte == "BB_BREAK" and _rvol < 1.0:
                _armadilha.append("BB break sem volume")
            if eh_long and _rsi >= 58:
                _armadilha.append(f"RSI {_rsi:.0f} próximo ao limite LONG")
            if not eh_long and _rsi <= 42:
                _armadilha.append(f"RSI {_rsi:.0f} próximo ao limite SHORT")
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
            # ha_bull_1 sem ha_bull = apenas 1 vela confirmada — conta como risco na armadilha
            _ha_1v_only = (eh_long  and result.get("ha_bull_1") and not result.get("ha_bull")) or \
                          (not eh_long and result.get("ha_bear_1") and not result.get("ha_bear"))
            if _ha_1v_only:
                _armadilha.append("HA apenas 1 vela (sem confirmação anterior)")

            # Bloqueia sinais com múltiplas condições de risco por nível de qualidade
            if len(_armadilha) >= 2 and _score_inst < 55:
                log.info(f"  🚫 {abrev} {result['sinal']} BLOQ inst FRACO — {_score_inst} + {len(_armadilha)} risco(s): {'; '.join(_armadilha[:3])}")
                continue
            if len(_armadilha) >= 3 and _score_inst < 70:
                log.info(f"  🚫 {abrev} {result['sinal']} BLOQ inst MÉDIO — {_score_inst} + {len(_armadilha)} risco(s): {'; '.join(_armadilha[:3])}")
                continue

            # FLEX sem fluxo direcional + mercado neutro = TP1 improvável (~50%)
            if fonte == "FLEX" and not _dna and not _trl and _tend == "NEUTRO":
                log.info(f"  🚫 {abrev} FLEX bloqueado — sem fluxo + tendência neutra")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], "FLEX sem fluxo+neutro"))
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
            }
            ok = await enviar_sinal(session, sym, label, abrev, result["sinal"],
                                    result["preco"], result["atr"], result["score"],
                                    result["rsi"], result["adx"], result["tendencia"],
                                    result["kalman_subindo"], result["swing_low"],
                                    result["swing_high"], result["fonte_sinal"], tf, grade, extra=extra)
            if ok:
                _diag_buffer["ultimo_sinal"] = agora
                estado[chave_dir]    = agora
                estado[chave_any]    = agora
                estado[chave_global] = agora
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
            if sc > 12  and rsi < 60 and adx >= 8 and (kal or trl or dfl or sc > 40):
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

    log.info(f"[{tf}] Watchlist: {len(watchlist)} moedas encontradas")
    if watchlist:
        chave_wl = f"_watchlist_{tf}"
        if agora - estado.get(chave_wl, 0) >= 1800:
            ok = await enviar_watchlist(session, tf, watchlist)
            if ok: estado[chave_wl] = agora

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
            _score_min_mtf = 40; _inst_min_mtf = 40
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
                    "inst_score":   r4h.get("score_inst_long" if eh_long else "score_inst_short", 0),
                    "inst_cls":     r4h.get("cls_inst_long"   if eh_long else "cls_inst_short",   ""),
                    "dna_flow":     result.get("dna_flow_bull" if eh_long else "dna_flow_bear", False),
                    "trendilo_dir": result.get("trendilo_long" if eh_long else "trendilo_short", False),
                    "liq_event":    ("LIQ FUNDO ↑" if r4h.get("liq_fundo") else
                                     "LIQ TOPO ↓"  if r4h.get("liq_topo")  else ""),
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

            # Diagnóstico: varredura imediata no 1º ciclo, depois a cada 30 min sem sinais
            _agora_d    = time.time()
            _enviar_diag = False
            if ciclo == 1 and _diag_buffer["total_analisados"] > 0:
                _enviar_diag = True   # varredura imediata ao iniciar
            else:
                if total > 0:
                    _diag_buffer["ultimo_sinal"] = _agora_d
                _sem_sinal = _agora_d - _diag_buffer["ultimo_sinal"] >= 900
                if _agora_d - _diag_buffer["ultimo_envio"] >= 1800 and _sem_sinal:
                    _enviar_diag = True
            if _enviar_diag:
                try:
                    await _enviar_diagnostico(session)
                except Exception as _e:
                    log.error(f"❌ Erro diagnostico: {_e}")
                _diag_buffer.update({
                    "ultimo_envio":     _agora_d,
                    "bloqueadores":     {},
                    "candidatos":       [],
                    "total_analisados": 0,
                    "ciclos":           0,
                })

            if not LOOP_MODE:
                break
