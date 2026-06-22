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
    RISK_INSTITUCIONAL_POR_GRADE, MAX_CYCLE_RISK_INSTITUCIONAL, MAX_POSICOES_INSTITUCIONAL,
    COOLDOWN_INSTITUCIONAL_MESMA_DIR, COOLDOWN_INSTITUCIONAL_OPOSTA,
    RVOL_MIN_BY_TF, ADX_MIN_GLOBAL, GRAUS_PERMITIDOS, INST_MIN_EXEC, RVOL_MIN_EXEC,
    BTC_REGIME_ADX_MAX, BTC_REGIME_RSI_MIN, BTC_REGIME_RSI_MAX,
    GRAUS_PERMITIDOS_INSTITUCIONAL, STOPS_CONSECUTIVOS_PAUSA,
)
from coins import COINS, PRIORITY_WATCHLIST
from indicators import tf_para_minutos, segundos_ate_fechamento, serie_ema, calcular_rsi
from analyze import analisar, calcular_indicadores
from notify import enviar_sinal, notificar
from scanner import buscar_candles, escanear_melhores_moedas, _prefetch_lote, buscar_contract_data, buscar_preco_atual
from state import (carregar_estado, salvar_estado, registrar_posicao_aberta,
                   verificar_posicoes_abertas, registrar_resultado, resumo_resultados,
                   fechar_runner)
from auto_backtest import backtest_sinal, resumo_backtest

log = logging.getLogger("GAUSS+DNA")

MAX_SINAIS_POR_CICLO = 3


# ── Buffer de diagnóstico (30 min) ────────────────────────────────────────────

_diag_buffer: dict = {
    "bloqueadores":            {},   # motivo -> count (pré-cascata, genérico)
    "bloqueadores_pos_cascata": {},  # motivo -> count (sinal já detectado, bloqueado depois)
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
    eh_long_cand = sc_raw > 0   # usa score como proxy de direção (não kalman)
    rsi   = result.get("rsi", 50)
    adx   = result.get("adx", 0)
    rvol  = result.get("rvol", 1.0)
    adx_s = result.get("adx_subindo", True)
    lat   = result.get("tendencia", "NEUTRO") == "NEUTRO"
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

    _sc_min  = 25 if FILTER_LEVEL <= 0 else 40
    _vol_thr = 0.20 if FILTER_LEVEL <= 0 else (0.50 if FILTER_LEVEL == 1 else (0.65 if FILTER_LEVEL == 2 else 0.80))

    if sc < _sc_min:
        motivos.append("score baixo")
        return motivos

    # RSI zona — FLEX PRO 15/06 (CLAUDE.md REGRA #1): bloqueia só extremos absolutos
    if eh_long_cand and rsi >= 75:
        motivos.append(f"RSI {rsi:.0f} sobrecomprado (LONG bloq)")
    elif not eh_long_cand and rsi <= 25:
        motivos.append(f"RSI {rsi:.0f} sobrevendido (SHORT bloq)")

    if adx < (10 if FILTER_LEVEL <= 0 else 15):
        motivos.append("ADX baixo")
    if FILTER_LEVEL >= 2 and not adx_s:
        motivos.append("ADX nao subindo")
    if lat:
        motivos.append("mercado lateral")
    if rvol < _vol_thr:
        motivos.append(f"RVOL < {_vol_thr*100:.0f}%")
    if eh_long_cand and not ha1_b:
        motivos.append("HA nao bull")
    elif not eh_long_cand and not ha1_s:
        motivos.append("HA nao bear")
    if eh_long_cand and not dna_b and not trl_l and not f_b:
        motivos.append("sem fluxo LONG")
    elif not eh_long_cand and not dna_s and not trl_s and not f_s:
        motivos.append("sem fluxo SHORT")
    if FILTER_LEVEL >= 3 and eh_long_cand and liq_t:
        motivos.append("liq topo SMC")
    elif FILTER_LEVEL >= 3 and not eh_long_cand and liq_f:
        motivos.append("liq fundo SMC")
    if not motivos:
        motivos.append("HA/MACD pendente")
    return motivos


def _diag_pos_cascata(motivo: str) -> None:
    """Registra no buffer do diagnostico horario um bloqueio que so acontece
    DEPOIS que um sinal ja foi detectado pela cascata (grade/ADX/RVOL/inst/H4/
    classificacao V2/regime BTC/etc, em executar_ciclo e executar_ciclo_mtf) —
    sem isso esses motivos so apareciam no log do ciclo (stdout), nunca no
    diagnostico enviado ao Telegram (gap documentado no CLAUDE.md, virou
    bloqueador frequente — ex: regime BTC H1 neutro bloqueando 100% dos ciclos)."""
    _b = _diag_buffer["bloqueadores_pos_cascata"]
    _b[motivo] = _b.get(motivo, 0) + 1


async def _atualizar_resultados(session, estado) -> None:
    """Confere o preço atual das posições em acompanhamento e fecha (TP1_BE/TP2/STOP/
    EXPIRADO) as que já resolveram, gravando em resultados_log.csv — pedido 20/06,
    pra ter dado real de winrate em vez de impressão sobre 'perder boas entradas'."""
    posicoes = estado.get("_posicoes_abertas", [])
    if not posicoes:
        return
    simbolos = list({p["simbolo"] for p in posicoes})
    tarefas  = [buscar_preco_atual(session, sym) for sym in simbolos]
    valores  = await asyncio.gather(*tarefas)
    precos   = {sym: val for sym, val in zip(simbolos, valores) if val is not None}

    fechados = verificar_posicoes_abertas(estado, precos)
    for f in fechados:
        registrar_resultado(f)
        log.info(f"📈 Resultado: {f['simbolo']} {f['direcao']} [{f['fonte']}] → {f['resultado']}")
        # Circuit breaker do modo INSTITUCIONAL (pedido 21/06) — só conta posições
        # abertas sob esse modo; vitória (TP1_BE/TP2/TP2_RUNNER) zera o contador, STOP soma.
        if f.get("modo") == "INSTITUCIONAL":
            if f["resultado"] == "STOP":
                estado["_stops_consecutivos_inst"] = estado.get("_stops_consecutivos_inst", 0) + 1
            elif f["resultado"] in ("TP1_BE", "TP2", "TP2_RUNNER"):
                estado["_stops_consecutivos_inst"] = 0


async def _checar_runners(session, estado) -> None:
    """Resolve posições no estágio 'runner' (já bateram TP1 e TP2 — 20% restante
    da Estratégia de Saída V2, autorizado 22/06): 'segue MM10/MM21 e perda de
    estrutura'. Ticker simples (usado em _atualizar_resultados) não basta aqui —
    precisa de candle fresco pra calcular EMA/estrutura, por isso roda separado."""
    posicoes = estado.get("_posicoes_abertas", [])
    runners  = [p for p in posicoes if p.get("tp1_atingido") and p.get("tp2_atingido")]
    if not runners:
        return
    for p in runners:
        try:
            candles = await buscar_candles(session, p["simbolo"], p["tf"])
            if not candles or len(candles) < 60:
                continue
            ind = calcular_indicadores(candles)
            if not ind:
                continue
            eh_long = p["direcao"] == "LONG"
            preco   = ind["preco"]
            perdeu_mm        = (preco < ind["e10"] and preco < ind["e21"]) if eh_long else \
                                (preco > ind["e10"] and preco > ind["e21"])
            perdeu_estrutura = (not ind["estrutura_alta"]) if eh_long else (not ind["estrutura_baixa"])
            if perdeu_mm or perdeu_estrutura:
                risco_unid = abs(p["entrada"] - p["stop"]) or 1e-9
                r_runner = ((preco - p["entrada"]) if eh_long else (p["entrada"] - preco)) / risco_unid
                fechado = fechar_runner(estado, p, preco, r_runner)
                if fechado:
                    registrar_resultado(fechado)
                    motivo = "MM10/MM21" if perdeu_mm else "estrutura"
                    log.info(f"🏁 Runner encerrado: {p['simbolo']} {p['direcao']} → {motivo} | R extra {r_runner:+.2f}")
                    if fechado.get("modo") == "INSTITUCIONAL":
                        estado["_stops_consecutivos_inst"] = 0
        except Exception as e:
            log.warning(f"⚠️ Erro checando runner {p['simbolo']}: {e}")


async def _enviar_diagnostico(session) -> None:
    """Envia relatório de diagnóstico de bloqueadores ao Telegram."""
    blq    = _diag_buffer["bloqueadores"]
    blq_pc = _diag_buffer["bloqueadores_pos_cascata"]
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

    # Bloqueios PÓS-cascata — sinal já tinha sido detectado (PULLBACK/CROSS/
    # SM_SWEEP/BB_BREAK/etc) e foi rejeitado depois (grade/ADX/RVOL/Score Inst/
    # H4/cooldown/fluxo SMC/classificação V2/regime BTC). Seção separada da
    # "Bloqueadores mais frequentes" acima de propósito: esses motivos são raros
    # comparados aos bloqueios genéricos pré-cascata (centenas de ocorrências),
    # então misturados no mesmo top-6 por frequência eles nunca apareciam —
    # mesmo já estando registrados no buffer (gap real, corrigido 22/06).
    if blq_pc:
        top_blq_pc = sorted(blq_pc.items(), key=lambda x: x[1], reverse=True)[:6]
        linhas.append("\nSinais detectados mas bloqueados depois:")
        for i, (motivo, cnt) in enumerate(top_blq_pc, 1):
            linhas.append(f"  {i}. {motivo} — {cnt}x")

    top_long  = sorted([c for c in cand if c[2] > 0],  key=lambda x: x[0], reverse=True)[:4]
    top_short = sorted([c for c in cand if c[2] < 0],  key=lambda x: x[0], reverse=True)[:4]
    if top_long or top_short:
        linhas.append("\nCandidatos (por que nao disparou):")
        for entry in top_long:
            _, sym, sc, rsi, adx, tf = entry[:6]
            bloqs    = entry[6] if len(entry) > 6 else []
            detalhe  = entry[7] if len(entry) > 7 else None
            bloq_str = detalhe or (", ".join(bloqs[:2]) if bloqs else "HA/MACD pendente")
            linhas.append(f"  LONG  {sym} {sc:+d} RSI{rsi:.0f} → {bloq_str}")
        for entry in top_short:
            _, sym, sc, rsi, adx, tf = entry[:6]
            bloqs    = entry[6] if len(entry) > 6 else []
            detalhe  = entry[7] if len(entry) > 7 else None
            bloq_str = detalhe or (", ".join(bloqs[:2]) if bloqs else "HA/MACD pendente")
            linhas.append(f"  SHORT {sym} {sc:+d} RSI{rsi:.0f} → {bloq_str}")

    linhas.append(f"\nCiclos: {ciclos} | Analises: {tot}")

    # Resultado real dos sinais fechados nas últimas 24h (rastreamento, pedido 20/06)
    _resumo = resumo_resultados(horas=24)
    if _resumo:
        _c = _resumo["contagem"]
        _partes = [f"{v}x {k}" for k, v in sorted(_c.items(), key=lambda x: -x[1])]
        linhas.append(f"\nResultados (24h): {_resumo['total']} fechados — {', '.join(_partes)} "
                      f"— winrate {_resumo['winrate']:.0f}% — R medio {_resumo['r_medio']:+.2f}")
        # Detalhamento por fonte/grade (observabilidade — não altera gestão, só
        # acelera o diagnóstico quando a amostra chegar nos 30-50 trades)
        for _rotulo, _grupo in (("fonte", _resumo.get("por_fonte", {})),
                                 ("grade", _resumo.get("por_grade", {})),
                                 ("timeframe", _resumo.get("por_timeframe", {}))):
            if len(_grupo) > 1:
                _det = [f"{k}:{d['stop']}/{d['total']}STOP"
                        for k, d in sorted(_grupo.items(), key=lambda x: -x[1]["total"])]
                linhas.append(f"  por {_rotulo}: {', '.join(_det)}")

    # Backtest automático por sinal (22/06) — dado de calibração rápido (sliding
    # window no histórico), não substitui o resultado real acima, é só leading indicator
    _bt = resumo_backtest(horas=24)
    if _bt:
        _det_bt = [f"{f}:{d['winrate_medio']:.0f}%win/{d['r_medio']:+.2f}R({d['amostras']}am)"
                   for f, d in sorted(_bt.items(), key=lambda x: -x[1]["amostras"])]
        linhas.append(f"\nBacktest auto (24h): {', '.join(_det_bt)}")

    _texto_diag = "\n".join(linhas)
    log.info(f"[DIAG]\n{_texto_diag}")
    await notificar(session, _texto_diag)


# ── Filtro horário ────────────────────────────────────────────────────────────

def dentro_horario_operacao():
    """Opera apenas 09h-13h e 14h-21h no horário de Brasília (BRT = UTC-3)."""
    brt = timezone(timedelta(hours=-3))
    h   = datetime.now(brt).hour
    return (9 <= h < 13) or (14 <= h < 21)


# ── Filtro de Regime Global (AJUSTE PROFISSIONAL 21/06) ──────────────────────

async def _btc_h1_regime_neutro(session) -> bool:
    """BTC H1 sem direção clara (ADX baixo + RSI no meio da faixa) = mercado
    neutro de mercado total — bloqueia TODAS as moedas, LONG e SHORT, até o
    regime mudar. Sem dado de BTC, falha aberto (não bloqueia)."""
    candles = await buscar_candles(session, "BTCUSDT", "1h")
    if not candles:
        return False
    r = calcular_indicadores(candles)
    if not r:
        return False
    neutro = (r["adx"] < BTC_REGIME_ADX_MAX and
              BTC_REGIME_RSI_MIN <= r["rsi"] <= BTC_REGIME_RSI_MAX)
    if neutro:
        log.info(f"🧊 BTC H1 regime NEUTRO — ADX {r['adx']:.1f} | RSI {r['rsi']:.1f} — "
                 f"LONG e SHORT bloqueados neste ciclo")
    return neutro


# ── Filtro H4 ─────────────────────────────────────────────────────────────────

def _h4_confirma(candles_h4, direcao):
    """Retorna True se H4 confirma a direção do sinal. Sem H4 → não bloqueia."""
    if candles_h4 is None:
        return True
    r4 = calcular_indicadores(candles_h4)
    if not r4:
        return True
    h4_rsi  = r4["rsi"]
    h4_vol  = r4.get("v_forte", False) or r4.get("obv_bull", False)
    h4_vols = r4.get("v_forte", False) or r4.get("obv_bear", False)
    h4_bull = (r4["score"] > 15 and r4.get("tbull_r", False) and
               r4["adx"] >= 13 and h4_rsi < (75 if r4["adx"] > 30 else 65) and h4_vol)
    h4_bear = (r4.get("tbear_r", False) and r4["adx"] >= 13 and
               h4_vols and r4["score"] < -15 and h4_rsi > 43)
    if direcao == "LONG"  and h4_bear and r4["score"] < -30: return False
    if direcao == "SHORT" and h4_bull and r4["score"] >  30: return False
    return True


def _h4_confirma_estrito(candles_h4, direcao):
    """Versão rígida usada pelo modo INSTITUCIONAL: H4 precisa CONFIRMAR a
    direção (não basta ausência de divergência forte) — qualquer H4 oposto
    bloqueia, mesmo sem score extremo. Sem H4 disponível, bloqueia também
    (modo institucional não opera sem confirmação multi-timeframe)."""
    if candles_h4 is None:
        return False
    r4 = calcular_indicadores(candles_h4)
    if not r4:
        return False
    h4_rsi  = r4["rsi"]
    h4_vol  = r4.get("v_forte", False) or r4.get("obv_bull", False)
    h4_vols = r4.get("v_forte", False) or r4.get("obv_bear", False)
    h4_bull = (r4["score"] > 15 and r4.get("tbull_r", False) and
               r4["adx"] >= 13 and h4_rsi < (75 if r4["adx"] > 30 else 65) and h4_vol)
    h4_bear = (r4.get("tbear_r", False) and r4["adx"] >= 13 and
               h4_vols and r4["score"] < -15 and h4_rsi > 43)
    if direcao == "LONG":  return h4_bull
    if direcao == "SHORT": return h4_bear
    return False


# ── Ciclo FLEX (por timeframe) ────────────────────────────────────────────────

async def executar_ciclo(session, estado, tf, moedas, btc_neutro=False):
    """Executa um ciclo completo de análise em todas as moedas para um timeframe."""
    if btc_neutro:
        log.info(f"[{tf}] Ciclo pulado — regime BTC H1 neutro (filtro de regime global)")
        _diag_pos_cascata("regime BTC H1 neutro")
        return 0
    agora = time.time(); enviados = 0
    _diag_buffer["ciclos"] += 1
    cooldown = (COOLDOWN_INSTITUCIONAL_MESMA_DIR if SIGNAL_MODE == "INSTITUCIONAL"
                else max(tf_para_minutos(tf) * 60, 7200))
    cooldown_oposta = (COOLDOWN_INSTITUCIONAL_OPOSTA if SIGNAL_MODE == "INSTITUCIONAL" else 7200)
    candidatos = []
    watchlist  = []
    risco_ciclo  = 0.0; scouts_enviados = 0
    longs_enviados = 0; shorts_enviados = 0

    todos_candles = await _prefetch_lote(session, moedas, tf)
    todos_h4      = None
    if tf in ("1h", "30m", "15m"):
        log.info(f"[{tf}] Buscando H4 de {len(moedas)} moedas para filtro de direção...")
        todos_h4 = await _prefetch_lote(session, moedas, "4h")

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
                (abs(result["score"]), abrev, result["score"], result["rsi"], result["adx"], tf, _bloqs,
                 result.get("bloqueio_detalhe"))
            )

        if result["sinal"]:
            fonte    = result.get("fonte_sinal", "")
            # Sinais de reversão extrema têm piso de score menor (mercado em pânico/euforia)
            _score_min = 30 if fonte in ("REVERSAL", "SM_SWEEP", "DIV") else 40
            if abs(result["score"]) < _score_min:
                log.info(f"  ⚠️ {abrev} bloqueado — score {result['score']:+d} < {_score_min}")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], f"score<{_score_min}"))
                _diag_pos_cascata(f"score<{_score_min}")
                continue

            # AJUSTE PROFISSIONAL (21/06) — qualidade mínima: só grade A/S, ADX>=20
            # universal (piso geral, alguns sinais já exigem mais na própria condição),
            # RVOL adaptativo por timeframe (30m mais solto que 1h).
            # AJUSTE INSTITUCIONAL ELITE (21/06): nesse modo a barra sobe mais —
            # grade A (que ainda passa no FLEX/ELITE) é bloqueada, só S/A+.
            _graus_ok = GRAUS_PERMITIDOS_INSTITUCIONAL if SIGNAL_MODE == "INSTITUCIONAL" else GRAUS_PERMITIDOS
            if grade not in _graus_ok:
                log.info(f"  ⚠️ {abrev} bloqueado — grade {grade} abaixo do mínimo ({'/'.join(sorted(_graus_ok))})")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], f"grade={grade}"))
                _diag_pos_cascata(f"grade={grade} insuficiente")
                continue
            if result["adx"] < ADX_MIN_GLOBAL:
                log.info(f"  ⚠️ {abrev} bloqueado — ADX {result['adx']:.1f} < piso global {ADX_MIN_GLOBAL}")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], f"adx<{ADX_MIN_GLOBAL}"))
                _diag_pos_cascata(f"adx<{ADX_MIN_GLOBAL} (piso global)")
                continue
            _rvol_min_tf = max(RVOL_MIN_BY_TF.get(tf, 0.80), RVOL_MIN_EXEC)
            if result.get("rvol", 1.0) < _rvol_min_tf:
                log.info(f"  ⚠️ {abrev} bloqueado — RVOL {result.get('rvol', 0):.2f} < {_rvol_min_tf} ({tf})")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], f"rvol<{_rvol_min_tf}"))
                _diag_pos_cascata(f"rvol<{_rvol_min_tf} ({tf})")
                continue

            # CLASSIFICAÇÃO INSTITUCIONAL V2 (autorizado 22/06) — bloqueios universais
            # explícitos do pedido (RSI/ADX/lateral já são cobertos em boa parte pela
            # REGRA #1/ADX_MIN_GLOBAL, mas o pedido pede checagem explícita também aqui).
            _eh_long_uni = result["sinal"] == "LONG"
            if _eh_long_uni and result["rsi"] > 75:
                log.info(f"  ⚠️ {abrev} bloqueado — RSI {result['rsi']:.0f} > 75 (LONG)")
                _diag_pos_cascata("RSI>75 pos-sinal (LONG)")
                continue
            if not _eh_long_uni and result["rsi"] < 25:
                log.info(f"  ⚠️ {abrev} bloqueado — RSI {result['rsi']:.0f} < 25 (SHORT)")
                _diag_pos_cascata("RSI<25 pos-sinal (SHORT)")
                continue
            if result.get("lateralizado"):
                # DNA+GAUSS INSTITUCIONAL V2 (22/06): só nesse modo, lateral
                # ainda passa se BB Width estiver expandindo OU ADX>25 (sinal
                # de que o squeeze já está rompendo, não é mais lateral "morto")
                _lateral_exc = (SIGNAL_MODE == "INSTITUCIONAL" and
                                 (result.get("bb_expand") or result["adx"] > 25))
                if not _lateral_exc:
                    log.info(f"  ⚠️ {abrev} bloqueado — mercado lateral (V2)")
                    _diag_pos_cascata("mercado lateral (V2)")
                    continue

            eh_long_ = result["sinal"] == "LONG"
            score_inst = result.get("score_inst_long" if eh_long_ else "score_inst_short", 0)
            _hora_c   = datetime.now(timezone.utc).hour
            _sessao_perigosa = _hora_c >= 22 or _hora_c < 8   # Asian / madrugada UTC
            _abertura_falsa  = _hora_c in (8, 13)             # abertura Londres/NY (primeiros 30min)
            _inst_min = (0  if FILTER_LEVEL <= 0 else
                         35 if fonte == "SCOUT" else
                         40 if fonte in ("REVERSAL", "SM_SWEEP", "DIV") else 45)
            if FILTER_LEVEL >= 1 and (_sessao_perigosa or _abertura_falsa):
                _inst_min = max(_inst_min, 60)   # sessão perigosa: exige confirmação institucional forte
            if FILTER_LEVEL >= 1:
                _inst_min = max(_inst_min, INST_MIN_EXEC)  # filtro de execução V2 (21/06)
            if score_inst < _inst_min:
                log.info(f"  ⚠️ {abrev} bloqueado — Score Inst {score_inst} < {_inst_min}")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], f"inst<{_inst_min}"))
                _diag_pos_cascata(f"inst<{_inst_min}")
                continue

            _h4_check = _h4_confirma_estrito if SIGNAL_MODE == "INSTITUCIONAL" else _h4_confirma
            if tf in ("1h", "15m", "30m") and not _h4_check(h4c, result["sinal"]):
                log.info(f"  🚫 {abrev} [{tf}] {result['sinal']} bloqueado — H4 oposto")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], "H4 oposto"))
                _diag_pos_cascata("H4 oposto")
                continue

            chave_dir = f"{sym}_{tf}_{result['sinal']}"
            chave_any = f"{sym}_{tf}"
            bloq_dir  = agora - estado.get(chave_dir, 0) < cooldown
            bloq_flip = agora - estado.get(chave_any, 0) < cooldown_oposta
            if bloq_dir or bloq_flip:
                if bloq_dir:
                    mins = int((cooldown - (agora - estado.get(chave_dir, 0))) / 60)
                else:
                    mins = int((cooldown_oposta - (agora - estado.get(chave_any, 0))) / 60)
                log.info(f"  ⏳ {abrev} [{tf}] cooldown {mins}min")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], "cooldown"))
                _diag_pos_cascata("cooldown")
                continue

            eh_long  = result["sinal"] == "LONG"
            _modo_inst = SIGNAL_MODE == "INSTITUCIONAL"
            pct_risco = (RISK_INSTITUCIONAL_POR_GRADE.get(grade, 0.01) if _modo_inst else
                         RISK_SCOUT if fonte == "SCOUT" else RISK_BY_GRADE.get(grade, RISK_PCT))
            _teto_ciclo = MAX_CYCLE_RISK_INSTITUCIONAL if _modo_inst else MAX_CYCLE_RISK

            if risco_ciclo + pct_risco > _teto_ciclo:
                log.info(f"  🛑 {abrev} bloqueado — risco ciclo {risco_ciclo*100:.0f}%+{pct_risco*100:.0f}% > teto")
                continue
            if _modo_inst and len(estado.get("_posicoes_abertas", [])) >= MAX_POSICOES_INSTITUCIONAL:
                log.info(f"  🛑 {abrev} bloqueado — {MAX_POSICOES_INSTITUCIONAL} posições já abertas (modo INSTITUCIONAL)")
                continue
            # Circuit breaker (pedido 21/06): após N stops consecutivos no modo
            # institucional, pausa novas entradas até a primeira posição fechar como
            # vencedora (TP1_BE ou TP2) — contador atualizado em _atualizar_resultados().
            if _modo_inst and estado.get("_stops_consecutivos_inst", 0) >= STOPS_CONSECUTIVOS_PAUSA:
                log.info(f"  🛑 {abrev} bloqueado — circuit breaker ({estado.get('_stops_consecutivos_inst', 0)} stops consecutivos, aguardando vitória)")
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
            _dna       = result.get("dna_flow_bull" if eh_long else "dna_flow_bear", False)
            _trl       = result.get("trendilo_long" if eh_long else "trendilo_short", False)

            # Smart Money Flow (AJUSTE PROFISSIONAL 21/06) — fluxo institucional
            # obrigatório na direção do sinal, pra TODOS os tipos (antes só valia
            # pra FLEX e só em tendência neutra). Sem DNA Flow nem Trendilo
            # alinhados na direção do sinal, bloqueia.
            if not _dna and not _trl:
                log.info(f"  🚫 {abrev} bloqueado — sem fluxo institucional (DNA Flow/Trendilo) na direção do sinal")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], "sem fluxo SMC"))
                _diag_pos_cascata("sem fluxo SMC")
                continue

            # REGRAS DE EXECUÇÃO da Classificação Institucional V2 (autorizado
            # 22/06) — OURO sempre opera, PRATA só com H1 alinhado, BRONZE/sem
            # classificação é ignorado. Esta classificação É o gate final de
            # entrada (substitui o selo antigo, que era só informativo).
            classificacao = result.get("classificacao")
            if classificacao not in ("OURO", "PRATA"):
                log.info(f"  🥉 {abrev} bloqueado — classificação V2 {classificacao or 'nenhuma'} (ignorado)")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], f"v2={classificacao or 'none'}"))
                _diag_pos_cascata(f"v2={classificacao or 'none'}")
                continue
            if classificacao == "PRATA":
                # H1 alinhado pro gate PRATA (V2) — em tf=="1h" o próprio result já é
                # H1. Em 30m, busca H1 só pra este símbolo aqui (lazy — antes era
                # prefetch de TODAS as moedas do ciclo, autorizado 22/06 a remover
                # após caso real de HTTP 429 em excesso: a maioria das moedas nem
                # chega até esta checagem, prefetch em massa desperdiçava chamada).
                if tf == "1h":
                    _h1_ok = result.get("alinhado_bull" if eh_long else "alinhado_bear", False)
                else:
                    h1c = await buscar_candles(session, sym, "1h")
                    _r1h = calcular_indicadores(h1c) if h1c else None
                    _h1_ok = _r1h.get("alinhado_bull" if eh_long else "alinhado_bear", False) if _r1h else False
                if not _h1_ok:
                    log.info(f"  🥈 {abrev} bloqueado — PRATA exige H1 alinhado")
                    candidatos.append((abs(result["score"]), abrev, result["score"],
                                       result["rsi"], result["adx"], "prata sem H1"))
                    _diag_pos_cascata("prata sem H1")
                    continue

            extra = {
                "rvol_label":   result.get("rvol_label", ""),
                "rvol":         _rvol,
                "inst_score":   result.get("score_inst_long" if eh_long else "score_inst_short", 0),
                "inst_cls":     result.get("cls_inst_long"   if eh_long else "cls_inst_short",   ""),
                "dna_flow":     _dna,
                "trendilo_dir": _trl,
                "adx_subindo":  result.get("adx_subindo", False),
                "liq_event":    ("LIQ FUNDO ↑" if result.get("liq_fundo") else
                                 "LIQ TOPO ↓"  if result.get("liq_topo")  else ""),
                "funding_rate": result.get("funding_rate"),
                "oi_change":    oi_change.get(sym),
                "classificacao": classificacao,
            }
            ok = await enviar_sinal(session, sym, label, abrev, result["sinal"],
                                    result["preco"], result["atr"], result["score"],
                                    result["rsi"], result["adx"], result["tendencia"],
                                    result["kalman_subindo"], result["swing_low"],
                                    result["swing_high"], result["fonte_sinal"], tf, grade, extra=extra)
            if ok:
                _diag_buffer["ultimo_sinal"] = agora
                estado[chave_dir] = agora; estado[chave_any] = agora
                risco_ciclo   += pct_risco
                scouts_enviados += 1 if fonte == "SCOUT" else 0
                longs_enviados  += 1 if eh_long else 0
                shorts_enviados += 0 if eh_long else 1
                enviados += 1
                registrar_posicao_aberta(estado, sym, tf, result["sinal"], result["preco"],
                                         ok["stop"], ok["tp1"], ok["tp2"], ok["r1"], ok["r_final"],
                                         grade, result["fonte_sinal"], modo=SIGNAL_MODE,
                                         classificacao=classificacao)
                await backtest_sinal(session, sym, tf, result["fonte_sinal"], result["sinal"])
        else:
            candidatos.append((result["score"], abrev, result["score"],
                               result["rsi"], result["adx"], result.get("fonte_sinal", "sem-sinal")))
            sc  = result["score"]; rsi = result["rsi"]; adx = result["adx"]
            dfl = result.get("dna_flex_bull", False); dfs = result.get("dna_flex_bear", False)
            trl = result.get("trendilo_long", False);  trs = result.get("trendilo_short", False)
            kal = result.get("kalman_subindo", False)
            if sc > 12  and rsi < 72 and adx >= 8 and (kal or trl or dfl or sc > 40):
                watchlist.append(("LONG",  abrev, sc, rsi, adx, dfl, trl))
            elif sc < -12 and rsi > 35 and adx >= 8 and (not kal or trs or dfs or sc < -40):
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

    # Watchlist fica só no log — não envia Telegram (pedido 20/06: só sinal real
    # e o diagnóstico horário de ausência de sinal chegam ao usuário)
    log.info(f"[{tf}] Watchlist: {len(watchlist)} moedas encontradas")

    return enviados


# ── Ciclo MTF (H4 → H1) ──────────────────────────────────────────────────────

async def executar_ciclo_mtf(session, estado, moedas, btc_neutro=False):
    """Ciclo multi-timeframe: analisa H4 para direção → entra na H1."""
    if btc_neutro:
        log.info("[MTF] Ciclo pulado — regime BTC H1 neutro (filtro de regime global)")
        _diag_pos_cascata("regime BTC H1 neutro")
        return 0
    agora = time.time(); enviados = 0
    _diag_buffer["ciclos"] += 1
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
                _diag_pos_cascata("BTC H4 em queda (bloqueia LONG)")
                continue
            if h4_bear and btc_bull:
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, "BTC em alta"))
                log.info(f"[MTF] {abrev:7s} | SHORT bloqueado — BTC H4 em alta")
                _diag_pos_cascata("BTC H4 em alta (bloqueia SHORT)")
                continue
            if h4_bull and btc_rsi_quente:
                log.info(f"[MTF] {abrev:7s} | LONG bloqueado — BTC RSI {btc_rsi:.0f} > 72 (sobrecomprado)")
                _diag_pos_cascata("BTC RSI>72 (bloqueia LONG)")
                continue
            if h4_bear and btc_rsi_panico:
                log.info(f"[MTF] {abrev:7s} | SHORT bloqueado — BTC RSI {btc_rsi:.0f} < 28 (sobrevendido)")
                _diag_pos_cascata("BTC RSI<28 (bloqueia SHORT)")
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
                _diag_pos_cascata("H1 sem entrada (MTF)")
                continue

            grade   = result.get("grade", "A")
            pts     = result.get("pts_grade", 0)
            log.info(f"[MTF] {abrev:7s} | ✅ H1 {result['sinal']} Grade:{grade} Q:{pts} | "
                     f"{result['fonte_sinal']} | RSI {result['rsi']:.1f} | ADX {result['adx']:.1f}")
            eh_long_mtf = result["sinal"] == "LONG"
            score_inst_mtf = result.get("score_inst_long" if eh_long_mtf else "score_inst_short", 0)
            _score_min_mtf = 40
            _inst_min_mtf = max(40, INST_MIN_EXEC) if FILTER_LEVEL >= 1 else 40
            if abs(result["score"]) < _score_min_mtf or score_inst_mtf < _inst_min_mtf:
                motivo = (f"score {result['score']:+d}<{_score_min_mtf}" if abs(result["score"]) < _score_min_mtf
                          else f"Score Inst {score_inst_mtf}<{_inst_min_mtf}")
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, motivo))
                log.info(f"[MTF] {abrev:7s} | bloqueado — {motivo}")
                _diag_pos_cascata(f"{motivo} (MTF)")
                continue

            # AJUSTE PROFISSIONAL (21/06) — mesma qualidade mínima do ciclo FLEX:
            # só grade A/S, ADX>=20 universal, RVOL>=0.80 (piso H1) e fluxo SMC
            # (DNA Flow/Trendilo) obrigatório na direção do sinal.
            # AJUSTE INSTITUCIONAL ELITE (21/06): mesmo piso institucional-aware do
            # ciclo FLEX (só S/A+ neste modo).
            _graus_ok_mtf = GRAUS_PERMITIDOS_INSTITUCIONAL if SIGNAL_MODE == "INSTITUCIONAL" else GRAUS_PERMITIDOS
            if grade not in _graus_ok_mtf:
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, f"grade={grade}"))
                log.info(f"[MTF] {abrev:7s} | bloqueado — grade {grade} abaixo do mínimo ({'/'.join(sorted(_graus_ok_mtf))})")
                _diag_pos_cascata(f"grade={grade} insuficiente (MTF)")
                continue
            if result["adx"] < ADX_MIN_GLOBAL:
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, f"adx<{ADX_MIN_GLOBAL}"))
                log.info(f"[MTF] {abrev:7s} | bloqueado — ADX {result['adx']:.1f} < piso global {ADX_MIN_GLOBAL}")
                _diag_pos_cascata(f"adx<{ADX_MIN_GLOBAL} (piso global, MTF)")
                continue
            _rvol_mtf = result.get("rvol", 1.0)
            _rvol_min_mtf = max(RVOL_MIN_BY_TF.get("1h", 0.80), RVOL_MIN_EXEC)
            if _rvol_mtf < _rvol_min_mtf:
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, f"rvol<{_rvol_min_mtf}"))
                log.info(f"[MTF] {abrev:7s} | bloqueado — RVOL {_rvol_mtf:.2f} < {_rvol_min_mtf}")
                _diag_pos_cascata(f"rvol<{_rvol_min_mtf} (1h MTF)")
                continue
            _dna_mtf = result.get("dna_flow_bull" if eh_long_mtf else "dna_flow_bear", False)
            _trl_mtf = result.get("trendilo_long" if eh_long_mtf else "trendilo_short", False)
            if not _dna_mtf and not _trl_mtf:
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, "sem fluxo SMC"))
                log.info(f"[MTF] {abrev:7s} | bloqueado — sem fluxo institucional (DNA Flow/Trendilo)")
                _diag_pos_cascata("sem fluxo SMC (MTF)")
                continue

            # CLASSIFICAÇÃO INSTITUCIONAL V2 (autorizado 22/06) — entrada no MTF é
            # sempre H1, então "H1 alinhado" reusa result["alinhado_bull/bear"] direto
            # (sem prefetch extra, diferente do caminho FLEX em 30m).
            classificacao_mtf = result.get("classificacao")
            if classificacao_mtf not in ("OURO", "PRATA"):
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, f"v2={classificacao_mtf or 'none'}"))
                log.info(f"[MTF] {abrev:7s} | bloqueado — classificação V2 {classificacao_mtf or 'nenhuma'} (ignorado)")
                _diag_pos_cascata(f"v2={classificacao_mtf or 'none'} (MTF)")
                continue
            if classificacao_mtf == "PRATA":
                _h1_ok_mtf = result.get("alinhado_bull") if eh_long_mtf else result.get("alinhado_bear")
                if not _h1_ok_mtf:
                    setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, "prata sem H1"))
                    log.info(f"[MTF] {abrev:7s} | bloqueado — PRATA exige H1 alinhado")
                    _diag_pos_cascata("prata sem H1 (MTF)")
                    continue

            # AJUSTE INSTITUCIONAL ELITE (21/06): mesmo teto de posições simultâneas
            # e circuit breaker de stops consecutivos do ciclo FLEX, aplicado também
            # aqui — MTF é o outro caminho que pode abrir posição em modo INSTITUCIONAL.
            if SIGNAL_MODE == "INSTITUCIONAL":
                if len(estado.get("_posicoes_abertas", [])) >= MAX_POSICOES_INSTITUCIONAL:
                    log.info(f"[MTF] {abrev:7s} | bloqueado — {MAX_POSICOES_INSTITUCIONAL} posições já abertas (modo INSTITUCIONAL)")
                    continue
                if estado.get("_stops_consecutivos_inst", 0) >= STOPS_CONSECUTIVOS_PAUSA:
                    log.info(f"[MTF] {abrev:7s} | bloqueado — circuit breaker ({estado.get('_stops_consecutivos_inst', 0)} stops consecutivos, aguardando vitória)")
                    continue

            chave = f"{sym}_MTF"
            if agora - estado.get(chave, 0) >= cooldown_mtf:
                eh_long = result["sinal"] == "LONG"
                extra = {
                    "rvol_label":   result.get("rvol_label", ""),
                    "rvol":         result.get("rvol", 0.0),
                    "inst_score":   r4h.get("score_inst_long" if eh_long else "score_inst_short", 0),
                    "inst_cls":     r4h.get("cls_inst_long"   if eh_long else "cls_inst_short",   ""),
                    "dna_flow":     result.get("dna_flow_bull" if eh_long else "dna_flow_bear", False),
                    "trendilo_dir": result.get("trendilo_long" if eh_long else "trendilo_short", False),
                    "adx_subindo":  result.get("adx_subindo", False),
                    "liq_event":    ("LIQ FUNDO ↑" if r4h.get("liq_fundo") else
                                     "LIQ TOPO ↓"  if r4h.get("liq_topo")  else ""),
                    "classificacao": classificacao_mtf,
                }
                ok = await enviar_sinal(session, sym, label, abrev, result["sinal"],
                                        result["preco"], result["atr"], r4h["score"],
                                        result["rsi"], result["adx"], result["tendencia"],
                                        result["kalman_subindo"], result["swing_low"],
                                        result["swing_high"], result["fonte_sinal"], "1h", grade, extra=extra)
                if ok:
                    estado[chave] = agora; enviados += 1
                    registrar_posicao_aberta(estado, sym, "1h", result["sinal"], result["preco"],
                                             ok["stop"], ok["tp1"], ok["tp2"], ok["r1"], ok["r_final"],
                                             grade, result["fonte_sinal"], modo=SIGNAL_MODE,
                                             classificacao=classificacao_mtf)
                    await backtest_sinal(session, sym, "1h", result["fonte_sinal"], result["sinal"])
            else:
                mins = int((cooldown_mtf - (agora - estado.get(chave, 0))) / 60)
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, f"cooldown {mins}min"))
                log.info(f"  ⏳ {abrev} [MTF] cooldown {mins}min")
                _diag_pos_cascata("cooldown (MTF)")

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
            "adx_subindo":  result.get("adx_subindo", False),
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
        # Início do bot fica só no log — não envia Telegram (pedido 20/06: só
        # sinal real e o diagnóstico horário de ausência de sinal chegam ao usuário)
        agora_str = datetime.now().strftime("%H:%M — %d/%m/%Y")
        log.info(f"🤖 GAUSS+DNA iniciado | {agora_str} | TFs: {', '.join(TIMEFRAMES)} | "
                 f"Moedas: {len(COINS)} | Modo: {modo_str} | Ciclo: {CYCLE_INTERVAL}s | "
                 f"Filtros nivel {FILTER_LEVEL}: {_flv_desc.get(FILTER_LEVEL, str(FILTER_LEVEL))}")

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

            # Filtro de Regime Global (AJUSTE PROFISSIONAL 21/06) — calculado uma
            # vez por ciclo e repassado pros dois caminhos (MTF e FLEX) abaixo.
            try:
                btc_neutro = await _btc_h1_regime_neutro(session)
            except Exception as e:
                log.warning(f"⚠️ Filtro de regime BTC H1 falhou — não bloqueando: {e}")
                btc_neutro = False

            try:
                tem_mtf = (("4h" in TIMEFRAMES and "1h" in TIMEFRAMES) or
                           ("1h" in TIMEFRAMES and ("30m" in TIMEFRAMES or "15m" in TIMEFRAMES)))
                if tem_mtf:
                    enviados_mtf = await executar_ciclo_mtf(session, estado, moedas_ativas, btc_neutro)
                    total += enviados_mtf
            except Exception as e:
                log.error(f"❌ MTF erro ciclo #{ciclo}: {e}")

            try:
                # Roda FLEX para cada TF que não é coberto pelo caminho MTF (4h/1h)
                _tfs_flex = [tf for tf in TIMEFRAMES if tf not in ("4h", "1h")]
                if not _tfs_flex:
                    _tfs_flex = [t for t in TIMEFRAMES if t != "4h"] or [TIMEFRAMES[0]]
                for tf_base in _tfs_flex:
                    enviados = await executar_ciclo(session, estado, tf_base, moedas_ativas, btc_neutro)
                    total   += enviados
                log.info(f"✅ Ciclo #{ciclo} concluído. Sinais: {total}")
                await _atualizar_resultados(session, estado)
                await _checar_runners(session, estado)
            except Exception as e:
                log.error(f"❌ FLEX erro ciclo #{ciclo}: {e}")
            finally:
                salvar_estado(estado)

            if LOOP_MODE and ciclo % 5 == 0:
                log.info(f"💓 Heartbeat ciclo #{ciclo} | {len(moedas_ativas)} moedas")

            # Diagnóstico: varredura imediata no 1º ciclo, depois a cada 1h sem sinais
            # (única mensagem secundária enviada ao usuário, além do sinal — pedido 20/06)
            _agora_d    = time.time()
            _enviar_diag = False
            if ciclo == 1 and _diag_buffer["total_analisados"] > 0:
                _enviar_diag = True   # varredura imediata ao iniciar
            else:
                if total > 0:
                    _diag_buffer["ultimo_sinal"] = _agora_d
                _sem_sinal = _agora_d - _diag_buffer["ultimo_sinal"] >= 3600
                if _agora_d - _diag_buffer["ultimo_envio"] >= 3600 and _sem_sinal:
                    _enviar_diag = True
            if _enviar_diag:
                try:
                    await _enviar_diagnostico(session)
                except Exception as _e:
                    log.error(f"❌ Erro diagnostico: {_e}")
                _diag_buffer.update({
                    "ultimo_envio":     _agora_d,
                    "bloqueadores":     {},
                    "bloqueadores_pos_cascata": {},
                    "candidatos":       [],
                    "total_analisados": 0,
                    "ciclos":           0,
                })

            if not LOOP_MODE:
                break
