"""
DNA PREMIUM — Swing H4
H4 = gatilho principal, H1 = confirmacao, D1 = direcao macro.
Opera apenas movimentos de alta probabilidade, evita topo/fundo.
"""
import asyncio, json, logging, os, time
from datetime import datetime
from pathlib import Path

import aiohttp
from coins import PRIORITY_WATCHLIST, COINS
from scanner import buscar_candles
from analyze import calcular_indicadores

TG_TOKEN   = os.environ.get("TG_TOKEN", "")
TG_CHATID  = os.environ.get("TG_CHATID", "")
CAPITAL    = float(os.environ.get("CAPITAL", "100"))
COOLDOWN_H = 48
STATE_FILE = Path("swing_h4_signals.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("DNA-PREMIUM")

_seen = set()
ALL_COINS = []
for c in PRIORITY_WATCHLIST + COINS:
    if c[0] not in _seen:
        _seen.add(c[0])
        ALL_COINS.append(c)

def _fmt(p):
    if p < 0.0001: return f"{p:.7f}"
    if p < 0.001:  return f"{p:.6f}"
    if p < 0.1:    return f"{p:.5f}"
    if p < 1:      return f"{p:.4f}"
    if p < 100:    return f"{p:.3f}"
    return f"{p:.2f}"

def _esc(v):
    s = str(v).replace('\\', '\\\\')
    for ch in r"_*[]()~`>#+=|{}.!-":
        s = s.replace(ch, f"\\{ch}")
    return s

def carregar_estado():
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text())
        except Exception: pass
    return {}

def salvar_estado(estado):
    STATE_FILE.write_text(json.dumps(estado))

def ja_sinalizou(estado, simbolo, direcao):
    t = estado.get(f"{simbolo}_{direcao}", 0)
    return (time.time() - t) < COOLDOWN_H * 3600

def marcar(estado, simbolo, direcao):
    estado[f"{simbolo}_{direcao}"] = time.time()

async def enviar_tg(session, texto):
    if not TG_TOKEN or not TG_CHATID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    for t in range(3):
        try:
            async with session.post(url, json={"chat_id": TG_CHATID, "text": texto, "parse_mode": "MarkdownV2"}, timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = await r.json()
                if d.get("ok"): return
                log.warning(f"TG: {d.get('description')}"); return
        except Exception as e:
            if t < 2: await asyncio.sleep(2 ** t)
            else: log.error(f"TG: {e}")

def _grade_h4(r):
    i = r["score_inst_long"] if r["score"] > 0 else r["score_inst_short"]
    if i >= 90:         return "S+"
    if i >= 85:         return "S"
    if i >= 75:         return "A"
    return None

def _anti_topo(i):
    if i["rsi"] > 80:               return "RSI>80"
    if i.get("dist_e21_pct", 0) > 12: return f"dist_EMA21>{12:.0f}%"
    if i["sombra_sup"] > 0.40 and i["perto_bb_topo"]: return "topo_rejeicao"
    if i["liq_topo"]:                return "liq_topo"
    return None

def _anti_fundo(i):
    if i["rsi"] < 20:               return "RSI<20"
    if i.get("dist_e21_pct", 0) < -12: return f"dist_EMA21<{-12:.0f}%"
    if i["sombra_inf"] > 0.40 and i["perto_bb_fund"]: return "fundo_rejeicao"
    if i["liq_fundo"]:               return "liq_fundo"
    return None

def _h4_valido(i, direcao):
    if direcao == "LONG":
        if not i["tendencia_bull"]:         return "tend_bull=F"
        if i["score_inst_long"] < 75:       return f"inst={i['score_inst_long']}<75"
        if i["adx"] < 22:                    return f"ADX={i['adx']:.0f}<22"
        if i["rvol"] < 1.20:                 return f"RVOL={i['rvol']:.2f}<1.20"
        if not (50 <= i["rsi"] <= 75):       return f"RSI={i['rsi']:.0f} fora 50-75"
        if not i["rsi_subindo"]:             return "RSI_nao_subindo"
        if not i["ha_bull_1"]:               return "HA_nao_bull"
        at = _anti_topo(i)
        if at: return f"anti_topo({at})"
        if not i["sm_bull"] and not i["liq_fundo"]: return "sem_SM"
        return None
    else:
        if not i["tendencia_bear"]:         return "tend_bear=F"
        if i["score_inst_short"] < 75:      return f"inst={i['score_inst_short']}<75"
        if i["adx"] < 22:                    return f"ADX={i['adx']:.0f}<22"
        if i["rvol"] < 1.20:                 return f"RVOL={i['rvol']:.2f}<1.20"
        if not (25 <= i["rsi"] <= 50):       return f"RSI={i['rsi']:.0f} fora 25-50"
        if not i["rsi_caindo"]:              return "RSI_nao_caindo"
        if not i["ha_bear_1"]:               return "HA_nao_bear"
        af = _anti_fundo(i)
        if af: return f"anti_fundo({af})"
        if not i["sm_bear"] and not i["liq_topo"]: return "sem_SM"
        return None

def _h1_confirma(i_h1, direcao):
    if direcao == "LONG":
        return i_h1["e10"] > i_h1["e21"] and i_h1["f_bull"] and i_h1["preco"] > i_h1["e21"]
    else:
        return i_h1["e10"] < i_h1["e21"] and i_h1["f_bear"] and i_h1["preco"] < i_h1["e21"]

def _d1_confirma(i_d1, direcao):
    if direcao == "LONG":
        return i_d1["tendencia_bull"]
    else:
        return i_d1["tendencia_bear"]

def montar_mensagem(abrev, direcao, preco, atr, score_inst, rsi, adx, rvol, grade, e21, e50, e200, sm_str):
    eh_long = direcao == "LONG"
    sl  = preco * (1 - 0.02) if eh_long else preco * (1 + 0.02)
    tp1 = preco * (1 + 0.03) if eh_long else preco * (1 - 0.03)
    tp2 = preco * (1 + 0.06) if eh_long else preco * (1 - 0.06)

    risco_usd  = CAPITAL * 0.02
    dist_sl    = abs(preco - sl)
    contratos  = risco_usd / dist_sl if dist_sl > 0 else 0
    pos_usd    = contratos * preco
    alavancagem = 5
    colateral  = pos_usd / alavancagem
    ganho_tp1  = risco_usd * 1.5 * 0.5
    ganho_tp2  = risco_usd * 3.0 * 0.5

    agora = datetime.now().strftime("%H:%M — %d/%m/%Y")
    ico = "🟢" if eh_long else "🔴"
    grade_ico = {"S+": "💎", "S": "🏆", "A": "🔥"}.get(grade, "📊")
    cls = "ELITE" if score_inst >= 85 else "FORTE" if score_inst >= 75 else "—"

    return (
        f"🏛 *DNA PREMIUM — SWING H4 {direcao}*\n\n"
        f"{ico} *{_esc(abrev)}/USDT* \\| ⏱ H4\n"
        f"{grade_ico} GRADE: *{_esc(grade)}* \\| Score Inst: *{_esc(str(score_inst))}* {_esc(cls)}\n"
        f"{_esc(sm_str)}\n\n"
        f"💰 Entrada: `${_esc(_fmt(preco))}`\n"
        f"🛑 Stop \\(2%\\): `${_esc(_fmt(sl))}`\n"
        f"🎯 TP1 \\(3%\\): `${_esc(_fmt(tp1))}` → fechar 50%\n"
        f"🏆 TP2 \\(6%\\): `${_esc(_fmt(tp2))}` → fechar 50%\n\n"
        f"📊 RSI: `{_esc(str(rsi))}` \\| ADX: `{_esc(str(adx))}` \\| RVOL: `{_esc(f'{rvol:.2f}')}x`\n"
        f"📐 EMA21: `{_esc(_fmt(e21))}` \\| EMA50: `{_esc(_fmt(e50))}` \\| EMA200: `{_esc(_fmt(e200))}`\n\n"
        f"📐 *Gestão \\(2% de \\${_esc(f'{CAPITAL:.0f}')}\\)*\n"
        f"  Risco: `\\${_esc(f'{risco_usd:.2f}')}` \\| Pos: `\\${_esc(f'{pos_usd:.2f}')}` \\| {_esc(str(alavancagem))}x\n"
        f"💸 TP1 \\+`\\${_esc(f'{ganho_tp1:.2f}')}` \\| TP2 \\+`\\${_esc(f'{ganho_tp2:.2f}')}`\n\n"
        f"⏰ {_esc(agora)}"
    )

async def main():
    log.info(f"🔍 DNA PREMIUM H4 — scan de {len(ALL_COINS)} moedas")
    estado = carregar_estado(); sinais = 0

    async with aiohttp.ClientSession() as session:
        for simbolo, label, abrev in ALL_COINS:
            try:
                if ja_sinalizou(estado, simbolo, "LONG") and ja_sinalizou(estado, simbolo, "SHORT"):
                    continue

                candles_h4 = await buscar_candles(session, simbolo, "4h", 250)
                if not candles_h4: continue
                r4 = calcular_indicadores(candles_h4)
                if not r4: continue

                direcao = None
                if r4["score"] > 0:
                    bloq = _h4_valido(r4, "LONG")
                    if not bloq:
                        candles_h1 = await buscar_candles(session, simbolo, "1h", 200)
                        if candles_h1:
                            r1 = calcular_indicadores(candles_h1)
                            if r1 and _h1_confirma(r1, "LONG"):
                                candles_d1 = await buscar_candles(session, simbolo, "1d", 200)
                                if candles_d1:
                                    rd = calcular_indicadores(candles_d1)
                                    if rd and _d1_confirma(rd, "LONG"):
                                        direcao = "LONG"
                elif r4["score"] < 0:
                    bloq = _h4_valido(r4, "SHORT")
                    if not bloq:
                        candles_h1 = await buscar_candles(session, simbolo, "1h", 200)
                        if candles_h1:
                            r1 = calcular_indicadores(candles_h1)
                            if r1 and _h1_confirma(r1, "SHORT"):
                                candles_d1 = await buscar_candles(session, simbolo, "1d", 200)
                                if candles_d1:
                                    rd = calcular_indicadores(candles_d1)
                                    if rd and _d1_confirma(rd, "SHORT"):
                                        direcao = "SHORT"

                if direcao:
                    grade = _grade_h4(r4)
                    if grade is None:
                        log.info(f"  {abrev} {direcao} | Grade baixa (inst={r4['score_inst_long' if direcao=='LONG' else 'score_inst_short']:.0f}) — ignorando")
                        continue
                    if ja_sinalizou(estado, simbolo, direcao): continue

                    score_inst = r4["score_inst_long"] if direcao == "LONG" else r4["score_inst_short"]
                    sm_ev = ("LIQ_FUNDO ↑ + BOS" if direcao == "LONG" and r4.get("liq_fundo")
                             else "LIQ_TOPO ↓ + BOS" if direcao == "SHORT" and r4.get("liq_topo")
                             else "SM_Flow ativo" if (r4.get("sm_bull") if direcao == "LONG" else r4.get("sm_bear"))
                             else "Smart Money confirmado")
                    sm_str = f"🔍 {sm_ev}"

                    texto = montar_mensagem(abrev, direcao, r4["preco"], r4["atr"],
                                            score_inst, int(r4["rsi"]), int(r4["adx"]), r4["rvol"],
                                            grade, r4["e21"], r4["e50"], r4["e200"], sm_str)
                    await enviar_tg(session, texto)
                    marcar(estado, simbolo, direcao)
                    salvar_estado(estado)
                    sinais += 1
                    log.info(f"✅ {direcao} {abrev} | Grade {grade} | Inst {score_inst} | RSI {r4['rsi']:.0f} | ADX {r4['adx']:.0f} | RVOL {r4['rvol']:.2f}")
                    await asyncio.sleep(1)
                else:
                    bloq = "?" if r4["score"] > -20 and r4["score"] < 20 else (
                        _h4_valido(r4, "LONG") or _h4_valido(r4, "SHORT") or "score_inst_baixo"
                    )
                    if abs(r4["score"]) >= 60:
                        log.info(f"  {abrev} | Score {r4['score']:+d} | RSI {r4['rsi']:.0f} | ADX {r4['adx']:.0f} | RVOL {r4['rvol']:.2f}x | bloqueado: {bloq}")

            except Exception as e:
                log.warning(f"{abrev}: {e}")

    log.info(f"✅ Concluido — {sinais} sinal(is) enviado(s)")
    agora = datetime.now().strftime("%H:%M — %d/%m/%Y")
    if sinais == 0:
        resumo = (
            f"🔍 *DNA PREMIUM — Scan concluido*\n"
            f"{_esc(str(len(ALL_COINS)))} moedas escaneadas \\| 0 sinais\n"
            f"⏰ {_esc(agora)}"
        )
        async with aiohttp.ClientSession() as s:
            await enviar_tg(s, resumo)

if __name__ == "__main__":
    asyncio.run(main())
