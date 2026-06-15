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

    rvol_val    = extra.get("rvol", 0.0)
    score_inst  = extra.get("inst_score", 0)
    cls_inst    = extra.get("inst_cls", "")
    dna_flow_ok = extra.get("dna_flow", False)
    trendilo_ok = extra.get("trendilo_dir", False)
    funding_rate = extra.get("funding_rate")
    confianca   = extra.get("confianca", score_inst)
    scout_score = extra.get("scout_score", 0)

    # Stop: sempre 1.5 ATR
    stop  = preco - 1.5 * atr if eh_long else preco + 1.5 * atr
    risco = abs(preco - stop)
    if risco <= 0:
        log.warning(f"⚠️ {abrev} risco=0 — sinal ignorado")
        return False

    # Alvos: TP1 = 1R, TP2 = 2R
    tp1   = preco + risco      if eh_long else preco - risco
    tp2   = preco + risco * 2  if eh_long else preco - risco * 2

    # Tamanho da posição
    pct_risco   = 0.02 if fonte == "PREMIUM" else 0.01
    valor_risco = CAPITAL * pct_risco
    contratos   = valor_risco / risco if risco > 0 else 0
    valor_pos   = contratos * preco

    # Alavancagem dinâmica
    _lev = 8 if fonte == "PREMIUM" else 5
    if score_inst >= 80:  _lev = min(10, _lev + 1)
    if rvol_val >= 2.5:   _lev = min(10, _lev + 1)
    elif rvol_val < 1.2:  _lev = max(3,  _lev - 1)
    alavancagem = max(3, min(10, _lev))
    pos_alav    = valor_pos / alavancagem

    ganho_tp1   = valor_risco * 1.0
    ganho_tp2   = valor_risco * 2.0

    tf_lbl = _label_tf(tf)
    agora  = datetime.now().strftime("%H:%M — %d/%m/%Y")

    if fonte == "PREMIUM":
        tag_tipo  = "🏆 PREMIUM"
        tag_label = "🏆 GAUSS\\+DNA PREMIUM"
    else:
        tag_tipo  = "🔵 SCOUT FLEX"
        tag_label = "🔵 DNA SCOUT FLEX"

    sinal_ico = "🟢" if eh_long else "🔴"

    grades_label = {
        "S+": "💎 S\\+", "S": "🏆 S", "A+": "🔥 A\\+", "A": "⭐ A", "B": "📊 B"
    }
    grade_str = grades_label.get(grade, f"📊 {grade}")

    # Fluxo
    k_str  = "↑" if kalman_subindo else "↓"
    fluxo_str = ("✅ Ativo" if dna_flow_ok else "🟡 Parcial" if trendilo_ok else "⚠️ Fraco")

    # Funding rate
    if funding_rate is not None:
        fr_pct = funding_rate * 100
        fr_ico = ("✅" if (eh_long and funding_rate < -0.0001) or (not eh_long and funding_rate > 0.0001) else
                  "⚠️" if abs(funding_rate) > 0.0001 else "—")
        linha_funding = f"\n💹 Funding: `{_bruto(f'{fr_pct:.4f}')}%` {fr_ico}"
    else:
        linha_funding = ""

    texto = (
        f"🚨 *{_escapar(tag_label)} — {direcao}*\n\n"
        f"{sinal_ico} *{_escapar(label)}* \\| 🕐 `{_escapar(tf_lbl)}`\n\n"
        f"⭐ GRADE: {grade_str}\n"
        f"🏛 Score Inst: *{_escapar(str(score_inst))}/100* — {_escapar(cls_inst)}\n"
        f"🎯 Confiança: *{_escapar(str(confianca))}%*\n\n"
        f"💰 Entrada: `${_bruto(formatar_preco(preco))}`\n"
        f"🛑 Stop \\(1\\.5 ATR\\): `${_bruto(_fmt(stop))}`\n"
        f"🎯 TP1 \\(1R\\): `${_bruto(_fmt(tp1))}` → fechar 50% \\+ trailing\n"
        f"🎯 TP2 \\(2R\\): `${_bruto(_fmt(tp2))}` → fechar 50%\n\n"
        f"📊 RSI: `{_escapar(f'{rsi:.0f}')}`\n"
        f"📈 RVOL: `{_escapar(f'{rvol_val:.2f}')}x`\n"
        f"📉 ADX: `{_escapar(f'{adx:.0f}')}`\n"
        f"📦 Fluxo: {_escapar(fluxo_str)} \\| Kalman: {_escapar(k_str)}\n"
        f"📍 Tendência: {_escapar(tendencia)}\n"
        + (f"⚠️ SCOUT FLEX — risco reduzido \\(1%\\)\n" if fonte == "SCOUT_FLEX" else "")
        + f"\n📐 *Gestão \\({_escapar(str(int(pct_risco*100)))}% de ${_bruto(f'{CAPITAL:.0f}')}\\)*\n"
        f"  Risco: `${_bruto(f'{valor_risco:.2f}')}` \\| Pos: `${_bruto(f'{valor_pos:.2f}')}` \\| {_escapar(str(alavancagem))}x\n"
        f"💸 TP1 \\+`${_bruto(f'{ganho_tp1:.2f}')}` \\| TP2 \\+`${_bruto(f'{ganho_tp2:.2f}')}`"
        + linha_funding
        + f"\n⏰ {_escapar(agora)}"
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
                log.info(f"✅ {direcao} {abrev} [{fonte}] Grade:{grade} Conf:{confianca}% RSI:{rsi:.0f}")
                registrar_trade(simbolo, tf, direcao, preco, stop, tp1, tp2,
                                1.0, 2.0, grade, score, rsi, adx, fonte)
                # WhatsApp simplificado
                import re as _re
                wa_text = (
                    f"SINAL {direcao} — {label} [{tf_lbl}]\n"
                    f"Tipo: {tag_tipo}\n"
                    f"Grade: {grade} | Inst: {score_inst}/100 | Conf: {confianca}%\n\n"
                    f"Entrada: ${formatar_preco(preco)}\n"
                    f"Stop (1.5 ATR): ${_fmt(stop)}\n"
                    f"TP1 (1R): ${_fmt(tp1)}\n"
                    f"TP2 (2R): ${_fmt(tp2)}\n\n"
                    f"RSI {rsi:.0f} | RVOL {rvol_val:.2f}x | ADX {adx:.0f}\n"
                    f"Risco ${valor_risco:.2f} | {alavancagem}x | ${pos_alav:.2f} colateral\n"
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
