"""
GAUSS+DNA — Notificações
Envio de sinais e alertas via Telegram e WhatsApp.
"""
import logging
import aiohttp
from datetime import datetime
from config import (TG_TOKEN, TG_CHATID, WA_PHONE, WA_APIKEY,
                    CAPITAL, RISK_PCT, RISK_BY_GRADE, RISK_SCOUT, SIGNAL_MODE,
                    RISK_INSTITUCIONAL_POR_GRADE)
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


# ── Régua de stop/TP — CLASSIFICAÇÃO INSTITUCIONAL V3 (autorizado 22/06,
# substitui a Estratégia de Saída V2) ─────────────────────────────────────────
# Extraído de enviar_sinal() em 22/06 pra ser reaproveitado pelo auto_backtest.py
# sem duplicar a lógica de gestão — qualquer ajuste de stop/TP feito aqui
# vale tanto pro sinal real quanto pro backtest automático que roda em cima dele.

def calcular_stop_tp(eh_long, preco, atr, swing_low, swing_high, fonte, classificacao):
    """Stop adaptativo (ATR vs estrutural, intocado) + alvos fixos em R, V3
    (TP1=1.5R/30%, TP2=3R/40%, TP3=5R/20%, 10% final sem alvo — segue tendência).
    Os 3 múltiplos são fixos pelo documento do usuário, independente de
    tier/grade/fonte — substitui a tabela por tier (OURO/PRATA) da V2."""
    mult_atr = (2.0 if fonte == "SURGE" else 1.8 if fonte in ("FLEX", "SETUP") else 1.5)
    stop_atr = preco - mult_atr * atr if eh_long else preco + mult_atr * atr
    stop_estrutural = swing_low - atr * 0.5 if eh_long else swing_high + atr * 0.5
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
    r1, r2, r3 = 1.5, 3.0, 5.0

    tp1 = preco + risco * r1 if eh_long else preco - risco * r1
    tp2 = preco + risco * r2 if eh_long else preco - risco * r2
    tp3 = preco + risco * r3 if eh_long else preco - risco * r3
    return {"stop": stop, "tp1": tp1, "tp2": tp2, "tp3": tp3,
            "r1": r1, "r2": r2, "r3": r3,
            "risco": risco, "label_stop": label_stop}


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
    evento_liq  = extra.get("liq_event", "")
    funding_rate = extra.get("funding_rate")
    oi_change    = extra.get("oi_change")

    # ── Classificação Institucional V3 (autorizado 22/06 — substitui a V2) —
    # já decidida e usada como gate de execução em cycles.py (OURO sempre,
    # PRATA só com H1 alinhado, BRONZE só com H1 alinhado ou score_inst>=70,
    # None nunca chega aqui), só exibida aqui.
    classificacao = extra.get("classificacao") or "PRATA"
    confluencia_emoji = {"OURO": "🥇", "PRATA": "🥈", "BRONZE": "🥉"}.get(classificacao, "🥈")
    confluencia_label = classificacao

    # ── Stop/TP — CLASSIFICAÇÃO INSTITUCIONAL V3 (extraído pra
    # notify.calcular_stop_tp, reaproveitado pelo auto_backtest.py) ──────────
    _stp = calcular_stop_tp(eh_long, preco, atr, swing_low, swing_high, fonte, classificacao)
    stop, tp1, tp2, tp3 = _stp["stop"], _stp["tp1"], _stp["tp2"], _stp["tp3"]
    r1, r2, r3 = _stp["r1"], _stp["r2"], _stp["r3"]
    risco, label_stop = _stp["risco"], _stp["label_stop"]
    if risco <= 0:
        log.warning(f"⚠️ {abrev} risco=0 (stop={stop:.8f} == preco={preco:.8f}) — sinal ignorado")
        return False
    risco_pct = risco / preco * 100

    # ── Tamanho da posição ────────────────────────────────────────────────────
    pct_risco    = (RISK_INSTITUCIONAL_POR_GRADE.get(grade, 0.01) if SIGNAL_MODE == "INSTITUCIONAL" else
                     RISK_SCOUT if fonte == "SCOUT" else RISK_BY_GRADE.get(grade, RISK_PCT))
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

    # Teto conservador por padrão (autorizado 21/06 — banca real baixa, perfil mais
    # defensivo pedido pelo usuário): trava em 10x a não ser que o sinal bata TODOS
    # os critérios de alta convicção (mesmos critérios pedidos: score_inst>=85,
    # adx>=30, rvol>=2, fluxo institucional alinhado nos dois indicadores, e a favor
    # da MM200) — nesse caso a fórmula acima continua valendo sem este teto extra.
    _mm200_ok = (tendencia == "ALTA") if eh_long else (tendencia == "BAIXA")
    _alta_conviccao = (score_inst >= 85 and adx >= 30 and rvol_val >= 2 and
                       dna_flow_ok and trendilo_ok and _mm200_ok)
    if not _alta_conviccao:
        _lev = min(_lev, 10)

    alavancagem = max(3, min(50, _lev))          # clamp 3x–50x

    pos_alav     = valor_pos / alavancagem
    # Split 30% TP1 / 40% TP2 / 20% TP3 / 10% runner (CLASSIFICAÇÃO INSTITUCIONAL
    # V3) — ganho_total é uma estimativa-piso assumindo o "restante" (10%) sai no
    # mesmo nível do TP3 (o runner pode rodar mais via trailing MM10/MM21+fluxo+
    # volume, ver _checar_runners em cycles.py)
    ganho_tp1    = valor_risco * r1 * 0.3
    ganho_tp2    = valor_risco * r2 * 0.4
    ganho_tp3    = valor_risco * r3 * 0.2
    ganho_total  = ganho_tp1 + ganho_tp2 + ganho_tp3 + valor_risco * r3 * 0.1

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
        f"{emoji_grade} *GRADE: {_escapar(grade)}* \\| {confluencia_emoji} *{_escapar(confluencia_label)}*\n"
        f"{linha_inst}"
        f"🎯 Confiança: *{_escapar(str(_confianca))}%*\n"
        f"{linha_liq}"
        f"{aviso_scout}\n"
        f"💰 Entrada: `${_bruto(formatar_preco(preco))}`\n"
        f"🛑 Stop \\({_escapar(label_stop)}\\): `${_bruto(_fmt(stop))}` · R\\=`{_bruto(f'{risco_pct:.1f}')}%`\n"
        f"🎯 TP1 \\({_escapar(str(r1))}R\\): `${_bruto(_fmt(tp1))}` → fechar 30% · stop → BE `${_bruto(formatar_preco(preco))}`\n"
        f"🎯 TP2 \\({_escapar(str(r2))}R\\): `${_bruto(_fmt(tp2))}` → fechar 40%\n"
        f"🎯 TP3 \\({_escapar(str(r3))}R\\): `${_bruto(_fmt(tp3))}` → fechar 20%\n"
        f"🏁 Restante \\(10%\\): segue tendência \\(MM10/MM21 \\+ fluxo \\+ volume\\)\n\n"
        f"📊 RSI: {_escapar(f'{rsi:.0f}')}\n"
        f"{linha_rvol}"
        f"📉 ADX: {_escapar(f'{adx:.0f}')}\n"
        f"📦 Fluxo: {fluxo_emoji} {_escapar(fluxo_label)} \\| Kalman: {_escapar(k_str)}\n"
        f"📍 Tendência: {_escapar(tendencia)}\n\n"
        f"📐 *Gestão \\({_escapar(str(int(pct_risco*100)))}% de ${_bruto(f'{CAPITAL:.0f}')}\\)*\n"
        f"Risco: `${_bruto(f'{valor_risco:.2f}')}` \\| Pos: `${_bruto(f'{valor_pos:.2f}')}` \\| {_escapar(str(alavancagem))}x \\(`${_bruto(f'{pos_alav:.2f}')}` colateral\\)\n"
        f"💸 TP1 \\+`${_bruto(f'{ganho_tp1:.2f}')}` \\| TP2 \\+`${_bruto(f'{ganho_tp2:.2f}')}` \\| TP3 \\+`${_bruto(f'{ganho_tp3:.2f}')}` \\| Total\\* \\+`${_bruto(f'{ganho_total:.2f}')}`\n"
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
                registrar_trade(simbolo, tf, direcao, preco, stop, tp1, tp3,
                                r1, r3, grade, score, rsi, adx, fonte)
                # WhatsApp — mensagem simplificada
                import re as _re
                wa_tipo = _re.sub(r'[^\w\s\-→/]', '', tag_modo).strip()
                wa_text = (
                    f"SINAL {direcao} — {label} [{tf_lbl}] Grade {grade}\n"
                    f"Tipo: {wa_tipo}\n\n"
                    f"Entrada: ${formatar_preco(preco)}\n"
                    f"Stop: ${_fmt(stop)} ({label_stop})\n"
                    f"TP1 ({r1}R, 30%): ${_fmt(tp1)} -> stop BE\n"
                    f"TP2 ({r2}R, 40%): ${_fmt(tp2)}\n"
                    f"TP3 ({r3}R, 20%): ${_fmt(tp3)}\n"
                    f"Restante (10%): segue tendência (MM10/MM21 + fluxo + volume)\n\n"
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
                return {"stop": stop, "tp1": tp1, "tp2": tp2, "tp3": tp3,
                        "r1": r1, "r2": r2, "r3": r3}
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
