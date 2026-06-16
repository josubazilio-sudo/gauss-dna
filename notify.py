"""
GAUSS+DNA — Notificações
Envio de sinais e alertas via Telegram e WhatsApp.
"""
import logging
import aiohttp
from datetime import datetime
from config import (TG_TOKEN, TG_CHATID, WA_PHONE, WA_APIKEY,
                    CAPITAL, RISK_PCT, RISK_BY_GRADE, RISK_SCOUT, SIGNAL_MODE)
from indicators import formatar_preco
from state import registrar_trade

log = logging.getLogger("GAUSS+DNA")


# ── Helpers de formatação ─────────────────────────────────────────────────────

def _fmt(v):
    return f"{v:.6f}" if v < 0.01 else f"{v:.4f}" if v < 1 else f"{v:.2f}"

def _escapar(v):
    """Escape para texto fora de backticks (MarkdownV2)."""
    s = str(v).replace('\\', '\\\\')
    for ch in r"_*[]()~`>#+=|{}.!-":
        s = s.replace(ch, f"\\{ch}")
    return s

def _bruto(v):
    """Dentro de backticks só backslash precisa ser escapado."""
    return str(v).replace('\\', '\\\\')

def _label_tf(tf):
    tf = tf.lower()
    if tf.endswith('d'): return f"D{tf[:-1]}"
    if tf.endswith('h'): return f"H{tf[:-1]}"
    return tf.upper()


# ── WhatsApp ──────────────────────────────────────────────────────────────────

async def enviar_whatsapp(session, texto):
    """Envia mensagem via CallMeBot. Requer WA_PHONE e WA_APIKEY configurados."""
    if not WA_PHONE or not WA_APIKEY:
        return
    import urllib.parse
    url = (f"https://api.callmebot.com/whatsapp.php"
           f"?phone={WA_PHONE}&text={urllib.parse.quote(texto)}&apikey={WA_APIKEY}")
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status == 200:
                log.info("✅ WhatsApp enviado")
            else:
                corpo = await r.text()
                log.warning(f"⚠️ WhatsApp status {r.status}: {corpo[:80]}")
    except Exception as e:
        log.warning(f"WhatsApp erro (não crítico): {e}")


# ── Watchlist ─────────────────────────────────────────────────────────────────

async def enviar_watchlist(session, tf, watchlist):
    """Mensagem consolidada com moedas próximas de sinal — aviso, não sinal."""
    if not TG_TOKEN or not TG_CHATID or not watchlist:
        return False

    tf_lbl = _label_tf(tf)
    agora  = datetime.now().strftime("%H:%M - %d/%m/%Y")

    def fmt_item(simbolo, score, rsi, adx, dna_flow, trendilo):
        sinal = "+" if score >= 0 else "-"
        dna   = "DNA✅" if dna_flow else "DNA-"
        trl   = "Trl✅" if trendilo else "Trl-"
        return f"• {simbolo} {sinal}{abs(score)} | RSI {rsi:.0f} | ADX {adx:.0f} | {dna} {trl}"

    longs  = [(s,sc,rsi,adx,df,trl) for d,s,sc,rsi,adx,df,trl in watchlist if d == "LONG"]
    shorts = [(s,sc,rsi,adx,df,trl) for d,s,sc,rsi,adx,df,trl in watchlist if d == "SHORT"]

    linhas = [f"📡 SETUP EM FORMAÇÃO | {tf_lbl}\n"]
    if longs:
        linhas.append("🟢 Aguardando LONG:")
        linhas += [fmt_item(*e) for e in longs[:5]]
    if shorts:
        if longs: linhas.append("")
        linhas.append("🔴 Aguardando SHORT:")
        linhas += [fmt_item(*e) for e in shorts[:5]]
    linhas += ["", "⚠️ Aguardar confirmação — ainda não é sinal", f"⏰ {agora}"]

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with session.post(url, json={"chat_id": TG_CHATID, "text": "\n".join(linhas)},
                                timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            if data.get("ok"):
                nomes = ", ".join(s for _,s,*_ in watchlist[:6])
                log.info(f"📡 Watchlist [{tf}]: {len(watchlist)} moedas — {nomes}")
                return True
            else:
                log.warning(f"Watchlist erro API: {data.get('description','?')} — código {data.get('error_code','?')}")
    except Exception as e:
        log.warning(f"Watchlist erro: {e}")
    return False


# ── Telegram — sinal principal ────────────────────────────────────────────────

async def enviar_sinal(session, simbolo, label, abrev, direcao, preco, atr, score,
                       rsi, adx, tendencia, kalman_subindo, swing_low, swing_high,
                       fonte, tf, grade, extra=None):
    """Monta e envia o sinal completo para o Telegram."""
    eh_long = direcao == "LONG"
    if extra is None:
        extra = {}

    rvol_lbl    = extra.get("rvol_label", "")
    rvol_val    = extra.get("rvol", 0.0)
    score_inst  = extra.get("inst_score", 0)
    cls_inst    = extra.get("inst_cls", "")
    dna_flow_ok = extra.get("dna_flow", False)
    trendilo_ok = extra.get("trendilo_dir", False)
    evento_liq  = extra.get("liq_event", "")
    funding_rate = extra.get("funding_rate")
    oi_change    = extra.get("oi_change")

    # ── Stop adaptativo ───────────────────────────────────────────────────────
    mult_atr = (2.0 if fonte in ("SURGE", "DUMP")              else
                1.2 if fonte == "SM_SWEEP"                   else
                1.8 if fonte in ("FLEX", "SETUP")            else
                1.5 if fonte in ("CORE", "BREAKOUT", "PUMP") else 1.5)

    stop_atr = preco - mult_atr * atr if eh_long else preco + mult_atr * atr
    stop_estrutural = swing_low - atr * 0.3 if eh_long else swing_high + atr * 0.3
    dist_swing = abs(preco - stop_estrutural)

    usar_estrutural = (fonte not in ("SURGE", "BB_BREAK", "MOMENTUM") and
                       atr * 0.3 < dist_swing < atr * 2.5 and
                       (stop_estrutural < preco if eh_long else stop_estrutural > preco))

    if usar_estrutural:
        stop = min(stop_atr, stop_estrutural) if eh_long else max(stop_atr, stop_estrutural)
        label_stop = "Estrutura"
    else:
        stop = stop_atr
        label_stop = f"{mult_atr:.1f} ATR"

    risco = abs(preco - stop)
    # Rede de segurança: mínimo 0.5% (cobre risco=0 e stops ultra-apertados)
    _risco_min = preco * 0.005
    if risco < _risco_min:
        risco = _risco_min
        stop = preco - risco if eh_long else preco + risco
        label_stop = "Min 0.5%"
    if risco <= 0:
        log.warning(f"⚠️ {abrev} risco=0 (stop={stop:.8f} == preco={preco:.8f}) — sinal ignorado")
        return False
    _risco_pct = risco / preco * 100

    # ── Alvos base por grade e tipo de sinal ─────────────────────────────────
    if fonte == "SCOUT":
        r1, r_final = 1.2, 2.0
    elif grade == "S+":
        r1, r_final = 2.5, 5.0
    elif grade == "S":
        r1, r_final = 2.2, 4.5
    elif grade == "A+":
        r1, r_final = 2.0, 4.0
    elif grade == "A":
        r1, r_final = 1.8, 3.5
    else:
        r1, r_final = 1.5, 2.5

    if fonte == "SURGE":
        r1      = max(1.5, r1 - 0.5)
        r_final = max(3.0, r_final - 1.0)
    elif fonte == "DIV":
        r_final = max(2.5, r_final - 0.5)

    # ── Amplificação por timeframe: TF maior = tendência com mais espaço ─────
    # 15m: base | 30m: +10% | 1h: +30% | 4h: +60%
    _tf_mult = {"15m": 1.0, "30m": 1.1, "1h": 1.3, "4h": 1.6}
    _m = _tf_mult.get(tf.lower(), 1.0)
    r1      = round(r1 * _m, 1)
    r_final = round(r_final * _m, 1)

    # ── Calibração por fase de mercado (ADX) ─────────────────────────────────
    # ADX < 20: mercado lateral/oscilando — saída rápida antes da reversão
    # ADX 20-24: tendência moderada — alvos ligeiramente comprimidos
    # ADX >= 25: tendência forte — manter alvos originais
    if adx < 20:
        r1      = max(1.0, round(r1 * 0.65, 1))
        r_final = max(1.5, round(r_final * 0.75, 1))
    elif adx < 25:
        r1      = max(1.0, round(r1 * 0.85, 1))
        r_final = max(2.0, round(r_final * 0.90, 1))

    # ── Teto estrutural: TP1 não ultrapassa próximo swing high/low ────────────
    if risco > 0:
        if eh_long and swing_high > preco:
            dist_r = (swing_high - preco) / risco
            if dist_r < r1:
                r1 = max(1.0, round(dist_r * 0.92, 1))
        elif not eh_long and swing_low < preco:
            dist_r = (preco - swing_low) / risco
            if dist_r < r1:
                r1 = max(1.0, round(dist_r * 0.92, 1))

    tp1   = preco + risco * r1      if eh_long else preco - risco * r1
    final = preco + risco * r_final if eh_long else preco - risco * r_final

    # ── Tamanho da posição ────────────────────────────────────────────────────
    if fonte == "PREMIUM":
        pct_risco = 0.03 if grade == "S+" else 0.02 if grade == "S" else 0.01
    elif fonte == "SCOUT":
        pct_risco = RISK_SCOUT
    else:
        pct_risco = RISK_BY_GRADE.get(grade, RISK_PCT)
    if fonte in ("SURGE", "BREAKOUT", "PUMP", "DUMP"):
        pct_risco = min(pct_risco, 0.02)
    valor_risco  = CAPITAL * pct_risco
    contratos    = valor_risco / risco if risco > 0 else 0
    valor_pos    = contratos * preco

    # Alavancagem dinâmica 3x–20x por qualidade do sinal
    _lev = {"S+": 20, "S": 16, "A+": 13, "A": 10, "B": 7}.get(grade, 7)
    if score_inst >= 80:   _lev += 2   # confirmação institucional forte
    elif score_inst >= 70: _lev += 1   # institucional bom
    elif score_inst < 55:  _lev -= 2   # institucional fraco
    if rvol_val >= 1.5:    _lev += 1   # volume muito acima da média
    elif rvol_val < 0.80:  _lev -= 1   # volume fraco
    if fonte == "PREMIUM":               _lev = min(_lev, 15)  # institucional: risco menor, cap 15x
    elif fonte == "SCOUT":               _lev = min(_lev, 5)   # sinal secundário: teto 5x
    elif fonte == "MOMENTUM":           _lev = min(_lev, 10)  # momentum rápido: teto 10x
    elif fonte == "SURGE":              _lev = min(_lev, 12)  # breakout explosivo: teto 12x
    elif fonte in ("BREAKOUT", "PUMP"): _lev = min(_lev, 10)  # breakout nascente: teto 10x
    elif fonte == "DUMP":               _lev = min(_lev, 8)   # pós-pump: alta volatilidade, conservador
    elif fonte == "BB_BREAK":           _lev = min(_lev, 8)   # rompimento BB: risco de falso break, cap 8x
    # Cap final por confiança (prevalece sobre grade)
    _conf_lev = max(40, min(95, score_inst * 3 // 4))
    if   _conf_lev < 60: _lev = min(_lev, 5)
    elif _conf_lev < 70: _lev = min(_lev, 10)
    elif _conf_lev < 80: _lev = min(_lev, 15)
    # conf>=80 (score>=107, impossível): cap 20x pelo clamp final
    alavancagem = max(3, min(20, _lev))              # clamp 3x–20x

    pos_alav     = valor_pos / alavancagem
    ganho_tp1    = valor_risco * r1 * 0.5       # 50% fechado em TP1
    ganho_total  = valor_risco * r_final * 0.5  # 50% restante fechado em TP2

    # ── Labels de modo ────────────────────────────────────────────────────────
    tf_lbl = _label_tf(tf)
    modos = {
        "PREMIUM":   "🏆 PREMIUM INSTITUCIONAL",
        "CORE":      "🏛 DNA CORE",
        "BREAKOUT":  "🔥 BREAKOUT INICIAL",
        "PUMP":      "🌋 PUMP DETECTADO",
        "DUMP":      "💣 DUMP PÓS-PUMP",
        "PULLBACK":  "🎯 DNA PULLBACK",
        "SM_SWEEP":  "🏦 SMART MONEY SWEEP",
        "SURGE":     "⚡ DNA SURGE",
        "MOMENTUM":  "🚀 DNA MOMENTUM",
        "REBOUND":   "↩️ RSI REBOUND",
        "DIV":       "📐 RSI DIVERGÊNCIA",
        "REVERSAL":  "🔄 REVERSÃO EXTREMA",
        "SETUP":     "🔭 DNA SETUP",
        "SCOUT":     "🔵 DNA SCOUT",
        "BB_BREAK":  "💥 BB BREAKOUT",
    }
    if fonte.startswith("TESTE"):
        tag_modo = "🧪 TESTE — NÃO OPERAR"; info_cross = ""
    elif fonte.startswith("MTF"):
        tag_modo = f"📡 MTF PULLBACK H4→{tf_lbl}"; info_cross = ""
    elif fonte.startswith("CROSS"):
        tag_modo = "🔀 DNA CROSS"; info_cross = fonte.split(":", 1)[1]
    elif SIGNAL_MODE == "ELITE":
        tag_modo = "🔬 DNA ELITE KALMAN"; info_cross = ""
    else:
        tag_modo = modos.get(fonte, "⚡ DNA FLEX"); info_cross = ""

    labels_grade = {
        "S+": "💎 GRADE S+ — Setup institucional",
        "S":  "🏆 GRADE S — Setup perfeito",
        "A+": "🔥 GRADE A+ — Setup excelente",
        "A":  "⭐ GRADE A — Setup sólido",
        "B":  "📊 GRADE B — Setup básico",
    }
    label_grade = labels_grade.get(grade, f"📊 GRADE {grade}")

    # ── Montagem da mensagem ──────────────────────────────────────────────────
    agora    = datetime.now().strftime("%H:%M — %d/%m/%Y")
    k_str    = "↑" if kalman_subindo else "↓"
    linha_cross = f"📉 Cruzamento: {_escapar(info_cross)}\n" if info_cross else ""

    _confianca = max(40, min(95, score_inst * 3 // 4))
    _fluxo_ico = "🟢" if (dna_flow_ok and trendilo_ok) else ("🟡" if (dna_flow_ok or trendilo_ok) else "🔴")
    _fluxo_str = "Completo" if (dna_flow_ok and trendilo_ok) else ("Parcial" if (dna_flow_ok or trendilo_ok) else "Ausente")
    _grade_ico = {"S+": "💎", "S": "🏆", "A+": "🔥", "A": "⭐", "B": "📊"}.get(grade, "📊")

    if funding_rate is not None:
        fr_pct = funding_rate * 100
        if eh_long:
            fr_ico = "✅" if funding_rate < -0.0001 else ("⚠️" if funding_rate > 0.0001 else "—")
        else:
            fr_ico = "✅" if funding_rate > 0.0001 else ("⚠️" if funding_rate < -0.0001 else "—")
        linha_funding = f"💹 Funding: `{_bruto(f'{fr_pct:.4f}')}%` {fr_ico}"
    else:
        linha_funding = ""

    if oi_change is not None:
        oi_ico = ("📈" if oi_change > 3 else "📉" if oi_change < -3 else "—")
        linha_oi = f"📊 OI: {oi_ico} `{_bruto(f'{oi_change:+.1f}')}%`"
    else:
        linha_oi = ""

    if fonte == "SCOUT":
        _aviso = f"\n⚠️ _DNA SCOUT — risco reduzido \\({int(pct_risco*100)}%\\) — semi\\-agressivo_"
    elif fonte == "PREMIUM":
        _aviso = f"\n🏆 _PREMIUM — qualidade institucional máxima_"
    else:
        _aviso = ""

    linha_liq    = f"🔍 SM: {_escapar(evento_liq)}\n" if evento_liq else ""
    rvol_lbl_str = f" {_escapar(rvol_lbl)}" if rvol_lbl else ""

    texto = (
        f"🚨 *{_escapar(tag_modo)} — {direcao}*\n\n"
        f"{'🟢' if eh_long else '🔴'} *{_escapar(label)}* \\| 🕐 *{_escapar(tf_lbl)}*\n"
        f"{linha_cross}"
        f"\n"
        f"{_escapar(_grade_ico)} GRADE: *{_escapar(grade)}*\n"
        f"🏛 Score Inst: *{_escapar(str(score_inst))}/100* {_escapar('— ' + cls_inst)}\n"
        f"🎯 Confiança: *{_escapar(str(_confianca))}%*\n"
        f"{linha_liq}"
        f"\n"
        f"💰 Entrada: `${_bruto(formatar_preco(preco))}`\n"
        f"🛑 Stop \\({_escapar(label_stop)}\\): `${_bruto(_fmt(stop))}` · R\\={_escapar(f'{_risco_pct:.1f}')}%\n"
        f"🎯 TP1 \\({_escapar(str(r1))}R\\): `${_bruto(_fmt(tp1))}` → fechar 50% · stop → BE `${_bruto(formatar_preco(preco))}`\n"
        f"🎯 TP2 \\({_escapar(str(r_final))}R\\): `${_bruto(_fmt(final))}` → fechar 50%\n"
        f"\n"
        f"📊 RSI: {_escapar(f'{rsi:.0f}')}\n"
        f"📈 RVOL: `{_bruto(f'{rvol_val:.2f}')}x`{rvol_lbl_str}\n"
        f"📉 ADX: {_escapar(f'{adx:.0f}')}\n"
        f"📦 Fluxo: {_escapar(_fluxo_ico)} {_escapar(_fluxo_str)} \\| Kalman: {_escapar(k_str)}\n"
        f"📍 Tendência: {_escapar(tendencia)}"
        + _aviso
        + f"\n\n"
        f"📐 *Gestão \\({_escapar(str(int(pct_risco*100)))}% de ${_bruto(f'{CAPITAL:.0f}')}\\)*\n"
        f"  Risco: `${_bruto(f'{valor_risco:.2f}')}` \\| Pos: `${_bruto(f'{valor_pos:.2f}')}` \\| {_escapar(str(alavancagem))}x\n"
        f"💸 TP1 \\+`${_bruto(f'{ganho_tp1:.2f}')}` \\| TP2 \\+`${_bruto(f'{ganho_total:.2f}')}`\n"
        + (f"{linha_funding}\n" if linha_funding else "")
        + (f"{linha_oi}\n" if linha_oi else "")
        + f"⏰ {_escapar(agora)}"
    )

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with session.post(
            url,
            json={"chat_id": TG_CHATID, "text": texto, "parse_mode": "MarkdownV2"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            data = await r.json()
            if data.get("ok"):
                log.info(f"✅ {direcao} {abrev} Grade:{grade} Score:{score} RSI:{rsi:.0f} ADX:{adx:.0f} [{fonte}]")
                registrar_trade(simbolo, tf, direcao, preco, stop, tp1, final,
                                r1, r_final, grade, score, rsi, adx, fonte)
                # WhatsApp — mensagem simplificada
                import re as _re
                wa_tipo = _re.sub(r'[^\w\s\-→/]', '', tag_modo).strip()
                wa_text = (
                    f"SINAL {direcao} — {label} [{tf_lbl}] Grade {grade}\n"
                    f"Tipo: {wa_tipo}\n\n"
                    f"Entrada: ${formatar_preco(preco)}\n"
                    f"Stop: ${_fmt(stop)} ({label_stop})\n"
                    f"TP1 ({r1}R): ${_fmt(tp1)}\n"
                    f"TP2 ({r_final}R): ${_fmt(final)}\n\n"
                    f"Risco ${valor_risco:.2f} | {alavancagem}x ${pos_alav:.2f} colateral\n"
                    f"RSI {rsi:.0f} | ADX {adx:.0f} | "
                    + (f"RVOL {rvol_val:.2f}x {rvol_lbl} | " if rvol_lbl else "")
                    + f"DNA Flow {'✅' if dna_flow_ok else '—'} | "
                    + f"Trendilo {'✅' if trendilo_ok else '—'} | "
                    + (f"SM: {evento_liq} | " if evento_liq else "")
                    + agora
                )
                await enviar_whatsapp(session, wa_text)
                return True
            else:
                log.warning(f"❌ {data.get('description')}")
                return False
    except Exception as e:
        log.error(f"Erro ao enviar sinal: {e}")
        return False


# ── Notificação simples ───────────────────────────────────────────────────────

async def notificar(session, texto):
    """Envia mensagem de texto simples (sem MarkdownV2) ao Telegram."""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with session.post(url, json={"chat_id": TG_CHATID, "text": texto},
                                timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            if not data.get("ok"):
                log.warning(f"⚠️ Notificação TG: {data.get('description')}")
    except Exception as e:
        log.warning(f"⚠️ Notificação TG falhou: {e}")
