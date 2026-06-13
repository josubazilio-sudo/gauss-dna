"""
Trend Master Flow — Swing H4
Cruzamento EMA21/EMA50 + filtro RSI no H4.
Envia sinais para o mesmo canal Telegram do GAUSS+DNA.
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import aiohttp

from coins import PRIORITY_WATCHLIST, COINS
from indicators import serie_ema, calcular_rsi, serie_atr

# ── Config ────────────────────────────────────────────────────────────────────
TG_TOKEN   = os.environ.get("TG_TOKEN", "")
TG_CHATID  = os.environ.get("TG_CHATID", "")
CAPITAL    = float(os.environ.get("CAPITAL", "64"))
RISK_PCT   = 0.02        # 2% por swing trade
ATR_SL     = 1.5
ATR_TP1    = 1.5         # TP1 = 1R (mesma distância do stop)
ATR_TP2    = 3.0         # TP2 = 2R
COOLDOWN_H = 24          # horas sem re-enviar o mesmo sinal
STATE_FILE = Path("swing_h4_signals.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("TMF-H4")

# Watchlist combinada sem duplicatas
_seen = set()
ALL_COINS = []
for c in PRIORITY_WATCHLIST + COINS:
    if c[0] not in _seen:
        _seen.add(c[0])
        ALL_COINS.append(c)


# ── Candles H4 (MEXC) ────────────────────────────────────────────────────────

async def buscar_h4(session, simbolo, limite=120):
    url = (f"https://api.mexc.com/api/v3/klines"
           f"?symbol={simbolo}&interval=4h&limit={limite}")
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
            if r.status != 200:
                return None
            data = await r.json()
        if not isinstance(data, list) or len(data) < 60:
            return None
        return [{"o": float(k[1]), "h": float(k[2]), "l": float(k[3]),
                 "c": float(k[4]), "v": float(k[5])} for k in data]
    except Exception as e:
        log.debug(f"{simbolo}: erro H4 — {e}")
        return None


# ── Formatação de preço ───────────────────────────────────────────────────────

def _fmt(p):
    if p < 0.0001: return f"{p:.7f}"
    if p < 0.001:  return f"{p:.6f}"
    if p < 0.1:    return f"{p:.5f}"
    if p < 1:      return f"{p:.4f}"
    if p < 100:    return f"{p:.3f}"
    return f"{p:.2f}"

def _esc(v):
    s = str(v)
    s = s.replace('\\', '\\\\')
    for ch in r"_*[]()~`>#+=|{}.!-":
        s = s.replace(ch, f"\\{ch}")
    return s


# ── Estado (cooldown 24h por moeda/direção) ───────────────────────────────────

def carregar_estado():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}

def salvar_estado(estado):
    STATE_FILE.write_text(json.dumps(estado))

def ja_sinalizou(estado, simbolo, direcao):
    t = estado.get(f"{simbolo}_{direcao}", 0)
    return (time.time() - t) < COOLDOWN_H * 3600

def marcar(estado, simbolo, direcao):
    estado[f"{simbolo}_{direcao}"] = time.time()


# ── Telegram ──────────────────────────────────────────────────────────────────

async def enviar_tg(session, texto):
    if not TG_TOKEN or not TG_CHATID:
        log.warning("TG_TOKEN / TG_CHATID não configurado")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    for tentativa in range(3):
        try:
            async with session.post(
                url,
                json={"chat_id": TG_CHATID, "text": texto, "parse_mode": "MarkdownV2"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json()
                if data.get("ok"):
                    return
                log.warning(f"TG erro: {data.get('description')}")
                return
        except Exception as e:
            if tentativa < 2:
                await asyncio.sleep(2 ** tentativa)
            else:
                log.error(f"TG falhou: {e}")


def montar_mensagem(abrev, direcao, preco, atr, rsi, e21, e50):
    eh_long = direcao == "LONG"
    sl  = preco - atr * ATR_SL  if eh_long else preco + atr * ATR_SL
    tp1 = preco + atr * ATR_TP1 if eh_long else preco - atr * ATR_TP1
    tp2 = preco + atr * ATR_TP2 if eh_long else preco - atr * ATR_TP2

    risco_usd  = CAPITAL * RISK_PCT
    dist_sl    = abs(preco - sl)
    contratos  = risco_usd / dist_sl if dist_sl > 0 else 0
    pos_usd    = contratos * preco
    alavancagem = 3   # swing: alavancagem conservadora
    colateral  = pos_usd / alavancagem
    ganho_tp1  = risco_usd * 1.0 * 0.5   # 1R × 50%
    ganho_tp2  = risco_usd * 2.0 * 0.5   # 2R × 50%

    agora = datetime.now().strftime("%H:%M — %d/%m/%Y")
    ico   = "🟢" if eh_long else "🔴"
    cruz  = "EMA21 cruzou acima EMA50" if eh_long else "EMA21 cruzou abaixo EMA50"
    forca = "FORTE \\(RSI > 50\\)" if eh_long else "FRACA \\(RSI < 50\\)"

    return (
        f"📈 *SWING H4 \\— {direcao}*\n\n"
        f"{ico} *{_esc(abrev)}/USDT* \\| ⏱ Gráfico: *H4*\n"
        f"🔀 Trend Master Flow\n"
        f"{_esc(cruz)} \\| RSI {_esc(f'{rsi:.0f}')} {forca}\n\n"
        f"💰 Entrada: `{_esc(_fmt(preco))}`\n"
        f"🛑 Stop: `{_esc(_fmt(sl))}` \\({_esc(str(ATR_SL))}x ATR\\)\n"
        f"🎯 TP1 \\(1R\\): `{_esc(_fmt(tp1))}` → fechar 50%\n"
        f"🏆 TP2 \\(2R\\): `{_esc(_fmt(tp2))}` → fechar 50%\n\n"
        f"📐 *Gestão de risco \\(2% de \\${_esc(f'{CAPITAL:.0f}')}\\)*\n"
        f"  Risco: `\\${_esc(f'{risco_usd:.2f}')}`\n"
        f"  Posição: `\\${_esc(f'{pos_usd:.2f}')} USDT` "
        f"\\({_esc(f'{contratos:.4f}')} {_esc(abrev)}\\)\n"
        f"  {_esc(str(alavancagem))}x: `\\${_esc(f'{colateral:.2f}')}` colateral\n"
        f"💸 Ganho: TP1 \\+`\\${_esc(f'{ganho_tp1:.2f}')}` "
        f"\\| Total \\+`\\${_esc(f'{ganho_tp2:.2f}')}`\n\n"
        f"📊 ATR: `{_esc(_fmt(atr))}` \\| "
        f"EMA21: `{_esc(_fmt(e21))}` \\| EMA50: `{_esc(_fmt(e50))}`\n"
        f"⏰ {_esc(agora)}"
    )


# ── Análise ───────────────────────────────────────────────────────────────────

async def analisar(session, simbolo, abrev, estado):
    candles = await buscar_h4(session, simbolo)
    if not candles:
        return None

    closes = [c["c"] for c in candles]
    ema21  = serie_ema(closes, 21)
    ema50  = serie_ema(closes, 50)
    rsi    = calcular_rsi(closes[-50:], 14)
    atr    = serie_atr(candles, 14)[-1]
    preco  = closes[-1]

    # Cruzamento na vela que acabou de fechar (penúltima → última)
    cross_bull = ema21[-2] <= ema50[-2] and ema21[-1] > ema50[-1]
    cross_bear = ema21[-2] >= ema50[-2] and ema21[-1] < ema50[-1]

    if cross_bull and rsi > 50 and not ja_sinalizou(estado, simbolo, "LONG"):
        return ("LONG",  preco, atr, rsi, ema21[-1], ema50[-1])
    if cross_bear and rsi < 50 and not ja_sinalizou(estado, simbolo, "SHORT"):
        return ("SHORT", preco, atr, rsi, ema21[-1], ema50[-1])
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    log.info(f"🔍 TMF H4 — scan de {len(ALL_COINS)} moedas")
    estado = carregar_estado()
    sinais = 0

    async with aiohttp.ClientSession() as session:
        for simbolo, _, abrev in ALL_COINS:
            try:
                resultado = await analisar(session, simbolo, abrev, estado)
                if resultado:
                    direcao, preco, atr, rsi, e21, e50 = resultado
                    texto = montar_mensagem(abrev, direcao, preco, atr, rsi, e21, e50)
                    await enviar_tg(session, texto)
                    marcar(estado, simbolo, direcao)
                    salvar_estado(estado)
                    sinais += 1
                    log.info(f"✅ {direcao} {abrev} — RSI {rsi:.0f} | ATR {_fmt(atr)}")
                    await asyncio.sleep(1)
            except Exception as e:
                log.warning(f"{abrev}: erro — {e}")

    log.info(f"✅ Concluído — {sinais} sinal(is) enviado(s)")

    agora = datetime.now().strftime("%H:%M — %d/%m/%Y")
    if sinais == 0:
        resumo = (
            f"🔍 *Swing H4 — Scan concluído*\n"
            f"{_esc(str(len(ALL_COINS)))} moedas escaneadas \\| 0 sinais\n"
            f"⏰ {_esc(agora)}"
        )
        async with aiohttp.ClientSession() as s:
            await enviar_tg(s, resumo)

if __name__ == "__main__":
    asyncio.run(main())
