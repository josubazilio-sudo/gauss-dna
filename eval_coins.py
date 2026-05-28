"""
GAUSS+DNA — Avaliador de Moedas
Busca dados reais da Binance, calcula métricas da estratégia e ranqueia as melhores moedas.

Uso: python3 eval_coins.py
"""
import asyncio, math, aiohttp, json
from datetime import datetime

TIMEFRAME = "15m"
LIMIT     = 250

# Candidatas a avaliar (pool amplo)
CANDIDATES = [
    # Mega caps
    ("BTCUSDT","BTC"),("ETHUSDT","ETH"),("BNBUSDT","BNB"),("XRPUSDT","XRP"),
    ("ADAUSDT","ADA"),("TRXUSDT","TRX"),("DOGEUSDT","DOGE"),("LTCUSDT","LTC"),
    # L1 smart contract
    ("SOLUSDT","SOL"),("AVAXUSDT","AVAX"),("DOTUSDT","DOT"),("NEARUSDT","NEAR"),
    ("ATOMUSDT","ATOM"),("APTUSDT","APT"),("SUIUSDT","SUI"),("TONUSDT","TON"),
    ("ALGOUSDT","ALGO"),("ICPUSDT","ICP"),("FILUSDT","FIL"),
    # L2 / infra
    ("ARBUSDT","ARB"),("OPUSDT","OP"),("MATICUSDT","MATIC"),("STRKUSDT","STRK"),
    # DeFi / infraestrutura
    ("LINKUSDT","LINK"),("UNIUSDT","UNI"),("AAVEUSDT","AAVE"),("INJUSDT","INJ"),
    ("JUPUSDT","JUP"),("RENDERUSDT","RENDER"),
    # High beta / meme
    ("PEPEUSDT","PEPE"),("WIFUSDT","WIF"),("SHIBUSDT","SHIB"),("BONKUSDT","BONK"),
    ("DOGSUSDT","DOGS"),
    # Outros trending
    ("SEIUSDT","SEI"),("TIAUSDT","TIA"),("FETUSDT","FET"),("WLDUSDT","WLD"),
]

# ── INDICADORES ──────────────────────────────────────────────────────────────

def ema_series(arr, p):
    k = 2.0/(p+1); out=[arr[0]]
    for v in arr[1:]: out.append(v*k+out[-1]*(1-k))
    return out

def rma_series(arr, p):
    out=[sum(arr[:p])/p]
    for v in arr[p:]: out.append((out[-1]*(p-1)+v)/p)
    return out

def atr_val(candles, p=14):
    trs=[candles[0]["h"]-candles[0]["l"]]
    for i in range(1,len(candles)):
        h,l,pc=candles[i]["h"],candles[i]["l"],candles[i-1]["c"]
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    rma=rma_series(trs,p)
    return rma[-1]

def dmi_adx_val(candles, p=14, smooth=14):
    pdm,mdm,tr=[],[],[]
    for i in range(1,len(candles)):
        h,l=candles[i]["h"],candles[i]["l"]
        ph,pl,pc=candles[i-1]["h"],candles[i-1]["l"],candles[i-1]["c"]
        up,dn=h-ph,pl-l
        pdm.append(up if up>dn and up>0 else 0)
        mdm.append(dn if dn>up and dn>0 else 0)
        tr.append(max(h-l,abs(h-pc),abs(l-pc)))
    rtr=rma_series(tr,p); rpdm=rma_series(pdm,p); rmdm=rma_series(mdm,p)
    dx=[]
    for i in range(len(rtr)):
        t=rtr[i] or 1e-10
        pdi=(rpdm[i]/t)*100; mdi=(rmdm[i]/t)*100
        dx.append(abs(pdi-mdi)/(pdi+mdi or 1)*100)
    return rma_series(dx,smooth)[-1]

def obv_slope(closes, vols, window=20):
    """Retorna consistência direcional do OBV (0-1, maior = mais consistente)."""
    obv=[0.0]
    for i in range(1,len(closes)):
        if closes[i]>closes[i-1]: obv.append(obv[-1]+vols[i])
        elif closes[i]<closes[i-1]: obv.append(obv[-1]-vols[i])
        else: obv.append(obv[-1])
    # Conta quantos dos últimos `window` movimentos OBV são na mesma direção
    moves=[obv[i]-obv[i-1] for i in range(max(1,len(obv)-window),len(obv))]
    if not moves: return 0
    pos=sum(1 for m in moves if m>0)/len(moves)
    return max(pos, 1-pos)  # 0.5 = aleatório, 1.0 = totalmente direcional

def trend_clarity(closes, p200=200):
    """Percentagem de candles onde o preço está acima OU abaixo da EMA200 (sem neutralidade)."""
    if len(closes) < p200: return 0
    e200=ema_series(closes,p200)
    above=sum(1 for i,c in enumerate(closes) if c>e200[i])
    below=len(closes)-above
    return max(above,below)/len(closes)

def macd_cross_rate(closes):
    """Taxa de cruzamentos do MACD (sinais potenciais por 100 candles)."""
    ea=ema_series(closes,12); eb=ema_series(closes,26)
    ml=[a-b for a,b in zip(ea,eb)]
    sl=ema_series(ml,9)
    crosses=sum(1 for i in range(1,len(ml))
                if (ml[i]-sl[i])*(ml[i-1]-sl[i-1])<0)
    return crosses/len(closes)*100

# ── AVALIAÇÃO ────────────────────────────────────────────────────────────────

def evaluate(sym, short, candles):
    if len(candles) < 60: return None
    closes=[c["c"] for c in candles]
    vols=[c["v"] for c in candles]
    price=closes[-1]

    atr=atr_val(candles)
    atr_pct=(atr/price)*100                  # volatilidade relativa (%)
    adx=dmi_adx_val(candles)                 # força de tendência atual
    obv_cons=obv_slope(closes,vols)          # consistência OBV (0.5-1.0)
    trend_pct=trend_clarity(closes)*100      # % candles com tendência clara
    cross_rate=macd_cross_rate(closes)       # cruzamentos MACD por 100 candles
    avg_vol=sum(vols[-20:])/20               # volume médio recente
    vol_usd=avg_vol*price                    # volume em USD

    # Pontuação composta:
    # - ADX (30%): tendência forte → mais sinais de qualidade
    # - Clareza de tendência (25%): menos neutralidade = melhor
    # - ATR% ideal 0.5-2.5% (20%): não muito quieto, não muito ruidoso
    # - OBV consistência (15%): volume confirma direção
    # - MACD cross rate ideal 3-8/100 (10%): não trava, não sobre-oscila
    atr_score = 100 - abs(atr_pct - 1.5) * 30  # ideal = 1.5%
    atr_score = max(0, min(100, atr_score))
    cross_score = 100 - abs(cross_rate - 5) * 8  # ideal = 5 cruzamentos/100
    cross_score = max(0, min(100, cross_score))

    composite = (
        adx * 0.30 +
        trend_pct * 0.25 +
        atr_score * 0.20 +
        obv_cons * 100 * 0.15 +
        cross_score * 0.10
    )

    return {
        "sym": sym, "short": short, "price": price,
        "adx": adx, "atr_pct": atr_pct, "trend_pct": trend_pct,
        "obv_cons": obv_cons, "cross_rate": cross_rate,
        "vol_usd_k": vol_usd / 1000,
        "composite": composite,
    }

# ── FETCH + MAIN ─────────────────────────────────────────────────────────────

async def fetch(session, sym):
    url=f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={TIMEFRAME}&limit={LIMIT}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            data=await r.json()
            if not isinstance(data,list) or len(data)<60: return None
            return [{"o":float(k[1]),"h":float(k[2]),"l":float(k[3]),"c":float(k[4]),"v":float(k[5])} for k in data]
    except: return None

async def main():
    print(f"\n🔍 GAUSS+DNA — Avaliador de Moedas | {TIMEFRAME} | {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
    results=[]
    async with aiohttp.ClientSession() as session:
        for sym,short in CANDIDATES:
            candles=await fetch(session,sym)
            if not candles:
                print(f"  ⚠️  {short:8s} — sem dados")
                continue
            r=evaluate(sym,short,candles)
            if r:
                results.append(r)
                print(f"  {short:8s} | ADX {r['adx']:5.1f} | ATR% {r['atr_pct']:4.2f} | "
                      f"Trend {r['trend_pct']:4.1f}% | OBV {r['obv_cons']:.2f} | "
                      f"Vol ${r['vol_usd_k']:,.0f}k | Score {r['composite']:5.1f}")
            await asyncio.sleep(0.2)

    results.sort(key=lambda x: x["composite"], reverse=True)

    print("\n" + "="*70)
    print("🏆 TOP 20 — Melhores moedas para a estratégia GAUSS+DNA")
    print("="*70)
    top20=results[:20]
    for i,r in enumerate(top20,1):
        print(f"  {i:2d}. {r['short']:8s} | Score {r['composite']:5.1f} | ADX {r['adx']:4.1f} | "
              f"ATR% {r['atr_pct']:.2f} | Trend {r['trend_pct']:.0f}%")

    print("\n📋 Código para copiar no bot_actions.py:\n")
    print("COINS = [")
    for r in top20:
        sym=r["sym"]; short=r["short"]
        label=f"{short}/USDT"
        print(f'    ("{sym}","{label}","{short}"),')
    print("]")
    print()

if __name__ == "__main__":
    asyncio.run(main())
