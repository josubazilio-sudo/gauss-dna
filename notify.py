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
    adx_subindo = extra.get("adx_subindo", False)
    evento_liq  = extra.get("liq_event", "")
    funding_rate = extra.get("funding_rate")
    oi_change    = extra.get("oi_change")

    # ── Classificação de confluência (Ouro/Prata/Bronze — pedido 20/06) ────────
    # 5 critérios de qualidade real do setup (independente do tipo de sinal):
    # fluxo duplo, volume forte, ADX forte e subindo, score inst alto, RSI saudável.
    _rsi_saudavel = (40 <= rsi <= 68) if eh_long else (32 <= rsi <= 60)
    _criterios = [
        dna_flow_ok and trendilo_ok,
        rvol_val >= 1.5,
        adx > 20 and adx_subindo,
        score_inst >= 65,
        _rsi_saudavel,
    ]
    _n_conf = sum(1 for c in _criterios if c)
    if _n_conf >= 4:
        confluencia_emoji, confluencia_label = "🥇", "OURO"
    elif _n_conf == 3:
        confluencia_emoji, confluencia_label = "🥈", "PRATA"
    else:
        confluencia_emoji, confluencia_label = "🥉", "BRONZE"

    # ── Stop adaptativo ───────────────────────────────────────────────────────
    mult_atr = (2.0 if fonte == "SURGE"    else
                1.2 if fonte == "SM_SWEEP" else
                1.8 if fonte in ("FLEX", "SETUP") else 1.5)

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
    if risco <= 0:
        log.warning(f"⚠️ {abrev} risco=0 (stop={stop:.8f} == preco={preco:.8f}) — sinal ignorado")
        return False
    risco_pct = risco / preco * 100

    # ── Alvos por grade e tipo de sinal ──────────────────────────────────────
    if fonte == "SCOUT":
        r1, r_final = 1.2, 2.0
    elif grade in ("S+", "S"):
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

    # ── Calibração por fase de mercado (ADX) ─────────────────────────────────
    # ADX < 20: mercado lateral/oscilando — saída rápida antes da reversão
    # ADX 20-24: tendência moderada — alvos ligeiramente comprimidos
    # ADX >= 25: tendência forte — manter alvos originais
    if adx < 20:
        r1      = max(0.8, round(r1 * 0.65, 1))
        r_final = max(1.5, round(r_final * 0.75, 1))
    elif adx < 25:
        r1      = max(1.0, round(r1 * 0.85, 1))
        r_final = max(2.0, round(r_final * 0.90, 1))

    # ── Teto estrutural: TP1 não ultrapassa próximo swing high/low ────────────
    if risco > 0:
        if eh_long and swing_high > preco:
            dist_r = (swing_high - preco) / risco
            if dist_r < r1:
                r1 = max(0.8, round(dist_r * 0.92, 1))
        elif not eh_long and swing_low < preco:
            dist_r = (preco - swing_low) / risco
            if dist_r < r1:
                r1 = max(0.8, round(dist_r * 0.92, 1))

    tp1   = preco + risco * r1      if eh_long else preco - risco * r1
    final = preco + risco * r_final if eh_long else preco - risco * r_final

    # ── Tamanho da posição ────────────────────────────────────────────────────
    pct_risco    = RISK_SCOUT if fonte == "SCOUT" else RISK_BY_GRADE.get(grade, RISK_PCT)
    valor_risco  = CAPITAL * pct_risco
    contratos    = valor_risco / risco if risco > 0 else 0
    valor_pos    = contratos * preco

    # Alavancagem dinâmica 3x–50x por qualidade do sinal (banca $100, plano dobrar banca 20/06)
    _lev = {"S+": 45, "S": 32, "A+": 22, "A": 14, "B": 8}.get(grade, 8)
    if score_inst >= 80:   _lev += 4   # confirmação institucional forte
    elif score_inst >= 70: _lev += 2   # institucional bom
    elif score_inst < 55:  _lev -= 3   # institucional fraco
    if rvol_val >= 1.5:    _lev += 2   # volume muito acima da média
    elif rvol_val < 0.80:  _lev -= 1   # volume fraco
    if fonte == "SCOUT":                 _lev = min(_lev, 6)   # sinal secundário: teto 6x
    elif fonte == "MOMENTUM":            _lev = min(_lev, 28)  # momentum rápido/stop apertado: teto 28x
    elif fonte == "SURGE":                _lev = min(_lev, 30)  # breakout explosivo: teto 30x
    elif fonte in ("BREAKOUT", "PUMP"):    _lev = min(_lev, 22)  # breakout nascente: teto 22x
    elif fonte == "DUMP":                 _lev = min(_lev, 16)  # pós-pump: alta volatilidade, conservador
    elif fonte == "BB_BREAK":             _lev = min(_lev, 18)  # rompimento BB: risco de falso break, cap 18x
    # Cap por confiança (prevalece sobre grade)
    _confianca = max(40, min(95, score_inst - 10))
    if   _confianca < 60: _lev = min(_lev, 6)
    elif _confianca < 70: _lev = min(_lev, 14)
    elif _confianca < 80: _lev = min(_lev, 22)
    elif _confianca < 90: _lev = min(_lev, 35)
    # conf>=90: sem cap extra aqui — decide o teto de liquidação/clamp final

    # Teto de segurança por liquidação (CLAUDE.md REGRA #4): a liquidação precisa
    # ficar >=1.3x a distância do stop, senão a corretora liquida a posição ANTES
    # do stop disparar — troca uma perda planejada de poucos % da banca por 100%
    # da margem do trade. liq_dist% ≈ 100/alavancagem (aprox. margem isolada/cross).
    if risco_pct > 0:
        _liq_cap = int(100 / (1.3 * risco_pct))
        _lev = min(_lev, max(3, _liq_cap))
    alavancagem = max(3, min(50, _lev))          # clamp 3x–50x

    pos_alav     = valor_pos / alavancagem
    ganho_tp1    = valor_risco * r1 * 0.5
    ganho_total  = valor_risco * (r1 + r_final) * 0.5

    # ── Labels de modo ────────────────────────────────────────────────────────
    tf_lbl = _label_tf(tf)
    modos = {
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
        "INSTITUCIONAL": "🏛 DNA INSTITUCIONAL",
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

    emoji_grade = {"S+": "💎", "S": "🏆", "A+": "🔥", "A": "⭐", "B": "📊"}.get(grade, "📊")

    # ── Montagem da mensagem ──────────────────────────────────────────────────
    agora    = datetime.now().strftime("%H:%M — %d/%m/%Y")
    k_str    = "↑" if kalman_subindo else "↓"
    linha_cross = f"📉 Cruzamento: {_escapar(info_cross)}\n" if info_cross else ""
    linha_rvol  = f"📈 RVOL: `{_bruto(f'{rvol_val:.2f}')}x` {_escapar(rvol_lbl)}\n" if rvol_lbl else ""
    if funding_rate is not None:
        fr_pct = funding_rate * 100
        if eh_long:
            fr_ico = "✅" if funding_rate < -0.0001 else ("⚠️" if funding_rate > 0.0001 else "—")
        else:
            fr_ico = "✅" if funding_rate > 0.0001 else ("⚠️" if funding_rate < -0.0001 else "—")
        linha_funding = f"💹 Funding: `{_bruto(f'{fr_pct:.4f}')}%` {fr_ico}\n"
    else:
        linha_funding = ""

    if oi_change is not None:
        oi_ico = ("📈" if oi_change > 3 else "📉" if oi_change < -3 else "—")
        linha_oi = f"📊 OI: {oi_ico} `{_bruto(f'{oi_change:+.1f}')}%`\n"
    else:
        linha_oi = ""
    linha_inst  = f"🏛 Score Inst: *{_escapar(str(score_inst))}/100* — {_escapar(cls_inst)}\n" if score_inst else ""
    linha_liq   = f"🔍 SM: {_escapar(evento_liq)}\n" if evento_liq else ""
    aviso_scout = "⚠️ _Sinal secundário — risco reduzido \\(1%\\) — semi\\-agressivo_\n" if fonte == "SCOUT" else ""

    # Fluxo combinado (DNA Flow + Trendilo) num único selo bom/médio/ruim
    if dna_flow_ok and trendilo_ok:
        fluxo_emoji, fluxo_label = "🟢", "Confirmado"
    elif dna_flow_ok or trendilo_ok:
        fluxo_emoji, fluxo_label = "🟡", "Parcial"
    else:
        fluxo_emoji, fluxo_label = "🔴", "Fraco"

    texto = (
        f"🚨 *{_escapar(tag_modo)} — {direcao}*\n\n"
        f"{'🟢' if eh_long else '🔴'} *{_escapar(label)}* \\| 🕐 *{_escapar(tf_lbl)}*\n"
        f"{linha_cross}\n"
        f"{emoji_grade} *GRADE: {_escapar(grade)}* \\| {confluencia_emoji} *{_escapar(confluencia_label)}* \\({_escapar(str(_n_conf))}/5\\)\n"
        f"{linha_inst}"
        f"🎯 Confiança: *{_escapar(str(_confianca))}%*\n"
        f"{linha_liq}"
        f"{aviso_scout}\n"
        f"💰 Entrada: `${_bruto(formatar_preco(preco))}`\n"
        f"🛑 Stop \\({_escapar(label_stop)}\\): `${_bruto(_fmt(stop))}` · R\\=`{_bruto(f'{risco_pct:.1f}')}%`\n"
        f"🎯 TP1 \\({_escapar(str(r1))}R\\): `${_bruto(_fmt(tp1))}` → fechar 50% · stop → BE `${_bruto(formatar_preco(preco))}`\n"
        f"🎯 TP2 \\({_escapar(str(r_final))}R\\): `${_bruto(_fmt(final))}` → fechar 50%\n\n"
        f"📊 RSI: {_escapar(f'{rsi:.0f}')}\n"
        f"{linha_rvol}"
        f"📉 ADX: {_escapar(f'{adx:.0f}')}\n"
        f"📦 Fluxo: {fluxo_emoji} {_escapar(fluxo_label)} \\| Kalman: {_escapar(k_str)}\n"
        f"📍 Tendência: {_escapar(tendencia)}\n\n"
        f"📐 *Gestão \\({_escapar(str(int(pct_risco*100)))}% de ${_bruto(f'{CAPITAL:.0f}')}\\)*\n"
        f"Risco: `${_bruto(f'{valor_risco:.2f}')}` \\| Pos: `${_bruto(f'{valor_pos:.2f}')}` \\| {_escapar(str(alavancagem))}x \\(`${_bruto(f'{pos_alav:.2f}')}` colateral\\)\n"
        f"💸 TP1 \\+`${_bruto(f'{ganho_tp1:.2f}')}` \\| TP2 \\+`${_bruto(f'{ganho_total:.2f}')}`\n"
        f"{linha_funding}"
        f"{linha_oi}"
        f"⏰ {_escapar(agora)}"
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
                    f"TP Final ({r_final}R): ${_fmt(final)}\n\n"
                    f"Risco ${valor_risco:.2f} | {alavancagem}x ${pos_alav:.2f} colateral\n"
                    f"RSI {rsi:.0f} | ADX {adx:.0f} | "
                    + (f"RVOL {rvol_val:.2f}x {rvol_lbl} | " if rvol_lbl else "")
                    + f"DNA Flow {'✅' if dna_flow_ok else '—'} | "
                    + f"Trendilo {'✅' if trendilo_ok else '—'} | "
                    + (f"SM: {evento_liq} | " if evento_liq else "")
                    + agora
                )
                await enviar_whatsapp(session, wa_text)
                # Dict (truthy) em vez de True puro — permite ao chamador registrar
                # a posição pro rastreamento de resultado (TP/STOP), pedido 20/06.
                return {"stop": stop, "tp1": tp1, "tp2": final, "r1": r1, "r_final": r_final}
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
