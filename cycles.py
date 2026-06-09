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
)
from coins import COINS
from indicators import tf_para_minutos, segundos_ate_fechamento, serie_ema, calcular_rsi
from analyze import analisar, calcular_indicadores
from notify import enviar_sinal, enviar_watchlist, notificar
from scanner import buscar_candles, escanear_melhores_moedas, _prefetch_lote, buscar_funding_rates
from state import carregar_estado, salvar_estado

log = logging.getLogger("GAUSS+DNA")

MAX_SINAIS_POR_CICLO = 3


# ── Filtro horário ────────────────────────────────────────────────────────────

def dentro_horario_operacao():
    """Opera apenas 09h-13h e 14h-21h no horário de Brasília (BRT = UTC-3)."""
    brt = timezone(timedelta(hours=-3))
    h   = datetime.now(brt).hour
    return (9 <= h < 13) or (14 <= h < 21)


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


# ── Ciclo FLEX (por timeframe) ────────────────────────────────────────────────

async def executar_ciclo(session, estado, tf, moedas):
    """Executa um ciclo completo de análise em todas as moedas para um timeframe."""
    agora = time.time(); enviados = 0
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

    funding_rates = await buscar_funding_rates(session)

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
            _inst_min = 40 if fonte in ("REVERSAL", "SM_SWEEP", "DIV") else 50
            if score_inst < _inst_min:
                log.info(f"  ⚠️ {abrev} bloqueado — Score Inst {score_inst} < {_inst_min}")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], f"inst<{_inst_min}"))
                continue

            if tf in ("1h", "15m", "30m") and not _h4_confirma(h4c, result["sinal"]):
                log.info(f"  🚫 {abrev} [{tf}] {result['sinal']} bloqueado — H4 oposto")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], "H4 oposto"))
                continue

            chave_dir = f"{sym}_{tf}_{result['sinal']}"
            chave_any = f"{sym}_{tf}"
            bloq_dir  = agora - estado.get(chave_dir, 0) < cooldown
            bloq_flip = agora - estado.get(chave_any, 0) < 7200
            if bloq_dir or bloq_flip:
                if bloq_dir:
                    mins = int((cooldown - (agora - estado.get(chave_dir, 0))) / 60)
                else:
                    mins = int((7200 - (agora - estado.get(chave_any, 0))) / 60)
                log.info(f"  ⏳ {abrev} [{tf}] cooldown {mins}min")
                candidatos.append((abs(result["score"]), abrev, result["score"],
                                   result["rsi"], result["adx"], "cooldown"))
                continue

            eh_long  = result["sinal"] == "LONG"
            pct_risco = RISK_SCOUT if fonte == "SCOUT" else RISK_BY_GRADE.get(grade, RISK_PCT)

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
            }
            ok = await enviar_sinal(session, sym, label, abrev, result["sinal"],
                                    result["preco"], result["atr"], result["score"],
                                    result["rsi"], result["adx"], result["tendencia"],
                                    result["kalman_subindo"], result["swing_low"],
                                    result["swing_high"], result["fonte_sinal"], tf, grade, extra=extra)
            if ok:
                estado[chave_dir] = agora; estado[chave_any] = agora
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
            if grade == "B" or abs(result["score"]) < 50 or score_inst_mtf < 50:
                motivo = (f"score {result['score']:+d}<50" if abs(result["score"]) < 50 else
                          f"Score Inst {score_inst_mtf}<50" if score_inst_mtf < 50 else "Grade B")
                setups_h4.append((abrev, direcao, r4h["score"], h4_rsi, motivo))
                log.info(f"[MTF] {abrev:7s} | bloqueado — {motivo}")
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
                    "liq_event":    ("LIQ FUNDO ↑" if r4h.get("liq_fundo") else
                                     "LIQ TOPO ↓"  if r4h.get("liq_topo")  else ""),
                }
                ok = await enviar_sinal(session, sym, label, abrev, result["sinal"],
                                        result["preco"], result["atr"], r4h["score"],
                                        result["rsi"], result["adx"], result["tendencia"],
                                        result["kalman_subindo"], result["swing_low"],
                                        result["swing_high"], result["fonte_sinal"], "1h", grade, extra=extra)
                if ok:
                    estado[chave] = agora; enviados += 1
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
    for sym, label, abrev in moedas_teste:
        candles = await buscar_candles(session, sym, "15m")
        if not candles:
            log.warning(f"❌ Sem dados para {abrev}"); continue
        result = analisar(sym, candles)
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
    log.info(f"🚀 GAUSS+DNA v3 | {SIGNAL_MODE} | TFs: {','.join(TIMEFRAMES)} | "
             f"Moedas: {scan_str} | {modo_str}")
    log.info("✅ Bot pronto — enviando apenas sinais reais ao Telegram")

    estado        = carregar_estado()
    ciclo         = 0
    moedas_ativas = list(COINS)
    ultimo_scan   = 0

    async with aiohttp.ClientSession() as session:
        agora_str    = datetime.now().strftime("%H:%M — %d/%m/%Y")
        await notificar(session,
            f"🤖 GAUSS+DNA iniciado\n"
            f"⏰ {agora_str}\n"
            f"📊 TFs: {', '.join(TIMEFRAMES)} | Moedas: {len(COINS)}\n"
            f"🔄 Modo: {modo_str} | Ciclo: {CYCLE_INTERVAL}s"
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
            if resultado: moedas_ativas = resultado
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
                if resultado: moedas_ativas = resultado
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
                if "4h" in TIMEFRAMES:
                    tf_base = next((t for t in TIMEFRAMES if t != "4h"), "1h")
                else:
                    tf_base = next((t for t in TIMEFRAMES if t != "1h"), TIMEFRAMES[0])
                enviados = await executar_ciclo(session, estado, tf_base, moedas_ativas)
                total   += enviados
                log.info(f"✅ Ciclo #{ciclo} concluído. Sinais: {total}")
            except Exception as e:
                log.error(f"❌ FLEX erro ciclo #{ciclo}: {e}")
            finally:
                salvar_estado(estado)

            if LOOP_MODE and ciclo % 5 == 0:
                log.info(f"💓 Heartbeat ciclo #{ciclo} | {len(moedas_ativas)} moedas")

            if not LOOP_MODE:
                break
