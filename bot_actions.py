"""
GAUSS+DNA ELITE + FLEX — Bot GitHub Actions v2
SIGNAL_MODE=ELITE: criterios completos (sinais raros, precisos)
SIGNAL_MODE=FLEX:  criterios suavizados (mais sinais, funciona em BEAR)
"""
import asyncio, os, json, time, math, logging, aiohttp
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("GAUSS+DNA")

TG_TOKEN     = os.environ.get("TG_TOKEN", "")
TG_CHATID    = os.environ.get("TG_CHATID", "")
TIMEFRAME    = os.environ.get("TIMEFRAME", "15m")
COOLDOWN     = int(os.environ.get("COOLDOWN", "900"))
SIGNAL_MODE  = os.environ.get("SIGNAL_MODE", "FLEX").upper()  # ELITE ou FLEX
STATE_FILE   = Path("last_signals.json")

COINS = [
    ("BTCUSDT","BTC/USDT","BTC"),("ETHUSDT","ETH/USDT","ETH"),
    ("SOLUSDT","SOL/USDT","SOL"),("SUIUSDT","SUI/USDT","SUI"),
    ("NEARUSDT","NEAR/USDT","NEAR"),("AVAXUSDT","AVAX/USDT","AVAX"),
    ("LINKUSDT","LINK/USDT","LINK"),("XRPUSDT","XRP/USDT","XRP"),
    ("DOGEUSDT","DOGE/USDT","DOGE"),("PEPEUSDT","PEPE/USDT","PEPE"),
    ("BONKUSDT","BONK/USDT","BONK"),("JUPUSDT","JUP/USDT","JUP"),
    ("SEIUSDT","SEI/USDT","SEI"),("WIFUSDT","WIF/USDT","WIF"),
    ("TIAUSDT","TIA/USDT","TIA"),("STRKUSDT","STRK/USDT","STRK"),
    ("ARBUSDT","ARB/USDT","ARB"),("OPUSDT","OP/USDT","OP"),
    ("INJUSDT","INJ/USDT","INJ"),("RENDERUSDT","RENDER/USDT","RENDER"),
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

def kalman_filter(src, length, R=0.01, Q=0.1):
    est=src[0]; err=1.0; out=[]
    for s in src:
        em=R*length; gain=err/(err+em)
        est=est+gain*(s-est); err=(1-gain)*err+Q/length
        out.append(est)
    return out

def atr_series(candles, p=14):
    trs=[candles[0]["h"]-candles[0]["l"]]
    for i in range(1,len(candles)):
        h,l,pc=candles[i]["h"],candles[i]["l"],candles[i-1]["c"]
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    rma=rma_series(trs,p)
    return [trs[0]]*(p)+rma[1:]

def rsi_calc(closes, p=14):
    gains=[0.0]; losses=[0.0]
    for i in range(1,len(closes)):
        d=closes[i]-closes[i-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains[1:p+1])/p; al=sum(losses[1:p+1])/p
    for i in range(p+1,len(closes)):
        ag=(ag*(p-1)+gains[i])/p; al=(al*(p-1)+losses[i])/p
    return 100.0 if al==0 else 100-(100/(1+ag/al))

def macd_calc(closes, f=12, s=26, sig=9):
    ea=ema_series(closes,f); eb=ema_series(closes,s)
    ml=[a-b for a,b in zip(ea,eb)]
    sl=ema_series(ml,sig); hist=[m-s for m,s in zip(ml,sl)]
    return ml[-1],sl[-1],hist[-1],hist[-2] if len(hist)>1 else hist[-1],hist[-3] if len(hist)>2 else hist[-1]

def dmi_adx(candles, p=14, smooth=14):
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
    adx_arr=rma_series(dx,smooth)
    idx=len(adx_arr)-1
    t=rtr[idx] or 1e-10
    pdi=(rpdm[idx]/t)*100; mdi=(rmdm[idx]/t)*100
    return pdi,mdi,adx_arr[idx],adx_arr[idx-1] if idx>0 else adx_arr[idx]

def ha_series(candles):
    """Heikin-Ashi: open é a média do HA candle anterior (não do candle real)."""
    ha=[]
    for i,c in enumerate(candles):
        hc=(c["o"]+c["h"]+c["l"]+c["c"])/4
        ho=(c["o"]+c["c"])/2 if i==0 else (ha[-1]["o"]+ha[-1]["c"])/2
        ha.append({"o":ho,"h":max(c["h"],ho,hc),"l":min(c["l"],ho,hc),"c":hc})
    return ha

def bb_calc(closes, p=20, mult=2.0):
    """Bollinger Bands: retorna upper, lower, basis, bandwidth atual e anterior."""
    def _bw(data):
        b=sum(data)/p; s=math.sqrt(sum((c-b)**2 for c in data)/p)
        return (2*mult*s)/(b or 1e-10), b+mult*s, b-mult*s, b
    bw,upper,lower,basis=_bw(closes[-p:])
    bw_prev,_,_,_=_bw(closes[-(p+1):-1]) if len(closes)>=p+1 else (bw,0,0,0)
    return upper,lower,basis,bw,bw_prev

def obv_calc(closes, vols):
    """On-Balance Volume: fluxo acumulado de volume."""
    obv=[0.0]
    for i in range(1,len(closes)):
        if closes[i]>closes[i-1]: obv.append(obv[-1]+vols[i])
        elif closes[i]<closes[i-1]: obv.append(obv[-1]-vols[i])
        else: obv.append(obv[-1])
    return obv

def vwap_calc(candles, period=20):
    """VWAP sobre as últimas N velas."""
    sl=candles[-period:]
    vp=sum((c["h"]+c["l"]+c["c"])/3*c["v"] for c in sl)
    tv=sum(c["v"] for c in sl)
    return vp/tv if tv>0 else sl[-1]["c"]

def fmt_price(price):
    if price<0.0001: return f"{price:.7f}"
    if price<0.01: return f"{price:.5f}"
    if price<1: return f"{price:.4f}"
    if price<100: return f"{price:.3f}"
    return f"{price:,.2f}"

# ── ANÁLISE ───────────────────────────────────────────────────────────────────

def analyze(sym, candles):
    n=len(candles)
    if n<60: return None
    closes=[c["c"] for c in candles]
    highs=[c["h"] for c in candles]; lows=[c["l"] for c in candles]
    opens=[c["o"] for c in candles]; vols=[c["v"] for c in candles]
    price=closes[-1]

    # EMAs
    e10=ema_series(closes,10)[-1]; e21=ema_series(closes,21)[-1]
    e50=ema_series(closes,50)[-1]
    e200a=ema_series(closes,200); e200=e200a[-1]; e200p=e200a[-4] if n>4 else e200

    # ATR
    atr_arr=atr_series(candles,14); atr=max(atr_arr[-1],1e-10)

    # Kalman
    ks=kalman_filter(closes,50); kl=kalman_filter(closes,150)
    kalman_up=ks[-1]>kl[-1]; kalman_down=ks[-1]<kl[-1]

    # MACD
    ml,sl_v,hist,hist_p,hist_pp=macd_calc(closes)
    macd_bull=ml>sl_v and hist>hist_p and hist>0
    macd_bear=ml<sl_v and hist<hist_p and hist<0

    # Heikin-Ashi (série correta — open baseado no HA anterior)
    ha=ha_series(candles)
    ha_bull=ha[-1]["c"]>ha[-1]["o"] and ha[-2]["c"]>ha[-2]["o"]
    ha_bear=ha[-1]["c"]<ha[-1]["o"] and ha[-2]["c"]<ha[-2]["o"]

    # RSI
    rsi=rsi_calc(closes[-50:])
    rsi_bull=50<rsi<70; rsi_bear=30<rsi<50

    # DMI/ADX
    pdi,mdi,adx,adx_p=dmi_adx(candles[-60:])
    adx_rising=adx>=adx_p*0.95
    adx_long_ok=adx>22 and pdi>mdi and adx_rising
    adx_short_ok=adx>22 and mdi>pdi and adx_rising

    # Volume
    vol_ma=sum(vols[-20:])/20; v_strong=vols[-1]>vol_ma*1.1

    # Flow
    flow_raw=[((c["c"]-c["o"])/max(c["h"]-c["l"],1e-10))*c["v"] for c in candles]
    flow_ema=ema_series(flow_raw,13); flow=flow_ema[-1]
    flow_sma=sum(abs(f) for f in flow_ema[-20:])/20
    f_bull=flow>0; f_bear=flow<0; f_strong=abs(flow)>flow_sma*1.2

    # Bollinger Bands
    bb_upper,bb_lower,bb_basis,bb_bw,bb_bw_prev=bb_calc(closes)
    bb_squeeze=bb_bw<bb_bw_prev*0.95   # banda contraindo
    bb_expand=bb_bw>bb_bw_prev*1.02    # banda expandindo (breakout)

    # OBV — fluxo acumulado de volume
    obv=obv_calc(closes,vols)
    obv_ema=ema_series(obv,20)
    obv_bull=obv[-1]>obv_ema[-1] and obv[-1]>obv[-6]
    obv_bear=obv[-1]<obv_ema[-1] and obv[-1]<obv[-6]

    # VWAP — suporte/resistência dinâmica por volume
    vwap=vwap_calc(candles)
    above_vwap=price>vwap; below_vwap=price<vwap

    # Tendência
    trend_bull=price>e200 and e10>e21 and e21>e50 and e50>e200
    trend_bear=price<e200 and e10<e21 and e21<e50 and e50<e200
    align_bull=price>e10 and price>e21 and price>e50
    align_bear=price<e10 and price<e21 and price<e50
    e200_rising=e200>e200p; e200_falling=e200<e200p
    strong_trend=abs(e21-e50)/atr>0.6

    not_ext_long=(price-e50)/atr<2.5
    not_ext_short=(e50-price)/atr<2.5

    bull_impulse=price>highs[-2] and price>opens[-1] and (price-opens[-1])>atr*0.2
    bear_impulse=price<lows[-2] and price<opens[-1] and (opens[-1]-price)>atr*0.2
    liq_long=lows[-1]<lows[-2] and price>lows[-2] and price>opens[-1]
    liq_short=highs[-1]>highs[-2] and price<highs[-2] and price<opens[-1]

    crange=highs[-1]-lows[-1]
    lwick=min(opens[-1],price)-lows[-1]
    uwick=highs[-1]-max(opens[-1],price)
    bull_absorb=crange>0 and lwick>crange*0.45 and price>(lows[-1]+crange*0.6) and vols[-1]>vol_ma
    bear_absorb=crange>0 and uwick>crange*0.45 and price<(highs[-1]-crange*0.6) and vols[-1]>vol_ma

    sell_exhaust=hist<hist_p and hist_p<hist_pp and price<e21 and price<e50 and price<e200
    buy_exhaust=hist>hist_p and hist_p>hist_pp and price>e21 and price>e50 and price>e200

    # Swing levels para stop baseado em estrutura de mercado
    swing_low=min(lows[-5:]); swing_high=max(highs[-5:])

    # Score (capped ±145)
    score=(
        (35 if trend_bull else -35 if trend_bear else 0)+
        (15 if f_bull else -15 if f_bear else 0)+
        (10 if f_strong else 0)+
        (20 if macd_bull else -20 if macd_bear else 0)+
        (20 if adx>30 else 10 if adx>22 else 0)+
        (10 if v_strong else -5)+
        (10 if rsi_bull else -10 if rsi_bear else 0)+
        (10 if e200_rising else -10 if e200_falling else 0)+
        (10 if kalman_up else -10 if kalman_down else 0)+
        (15 if obv_bull else -15 if obv_bear else 0)+
        (5 if above_vwap else -5)+
        (10 if ha_bull else -10 if ha_bear else 0)
    )
    score=max(-145,min(145,score))

    # ── SINAIS ELITE ──
    long_elite=(strong_trend and trend_bull and align_bull and e200_rising and
                macd_bull and ha_bull and f_bull and f_strong and adx_long_ok and rsi_bull and
                (v_strong or obv_bull) and not_ext_long and kalman_up and above_vwap and
                (bull_impulse or liq_long) and score>55)
    short_elite=(strong_trend and trend_bear and align_bear and e200_falling and
                 macd_bear and ha_bear and f_bear and f_strong and adx_short_ok and rsi_bear and
                 (v_strong or obv_bear) and not_ext_short and kalman_down and below_vwap and
                 (bear_impulse or liq_short) and score<-55)
    early_long=(adx_long_ok and (v_strong or obv_bull) and sell_exhaust and liq_long and
                bull_absorb and f_bull and trend_bull and e200_rising and kalman_up and above_vwap)
    early_short=(adx_short_ok and (v_strong or obv_bear) and buy_exhaust and liq_short and
                 bear_absorb and f_bear and trend_bear and e200_falling and kalman_down and below_vwap)

    # ── SINAIS FLEX ──
    long_flex=(score>35 and (trend_bull or kalman_up) and (macd_bull or ha_bull) and
               adx>15 and (f_bull or obv_bull) and (v_strong or bb_expand))
    short_flex=(score<-35 and (trend_bear or kalman_down) and (macd_bear or ha_bear) and
                adx>15 and (f_bear or obv_bear) and (v_strong or bb_expand))

    sig=None
    if SIGNAL_MODE=="ELITE":
        if long_elite or early_long: sig="LONG"
        elif short_elite or early_short: sig="SHORT"
    else:  # FLEX
        if long_flex: sig="LONG"
        elif short_flex: sig="SHORT"

    return {"price":price,"score":score,"atr":atr,"rsi":rsi,"adx":adx,
            "kalman_up":kalman_up,"trend":"BULL" if trend_bull else "BEAR" if trend_bear else "NEUTRO",
            "sig":sig,"swing_low":swing_low,"swing_high":swing_high,
            "ha_bull":ha_bull,"obv_bull":obv_bull,"above_vwap":above_vwap}

# ── TELEGRAM ─────────────────────────────────────────────────────────────────

async def send_telegram(session, sym, label, short, sig_type, price, atr, score,
                        rsi, adx, trend, kalman_up, swing_low, swing_high):
    is_long=sig_type=="LONG"
    # Stop baseado em swing high/low com floor de ATR
    if is_long:
        stop=max(swing_low-atr*0.1, price-atr*1.5)
    else:
        stop=min(swing_high+atr*0.1, price+atr*1.5)
    risk=abs(price-stop)
    tp1=price+risk*1.8 if is_long else price-risk*1.8
    tp2=price+risk*2.5 if is_long else price-risk*2.5
    final=price+risk*4 if is_long else price-risk*4
    mode_tag="🔬 DNA ELITE KALMAN" if SIGNAL_MODE=="ELITE" else "⚡ DNA FLEX"
    def d(v): return f"{v:.6f}" if v<0.01 else f"{v:.4f}" if v<1 else f"{v:.2f}"
    def esc(v):
        s=str(v)
        for ch in r"_*[]()~`>#+=|{}.!\-": s=s.replace(ch,f"\\{ch}")
        return s
    now=datetime.now().strftime("%H:%M — %d/%m/%Y")
    k_str="↑" if kalman_up else "↓"
    text=(
        f"🚨 *{esc(mode_tag)} — {sig_type}*\n\n"
        f"{'🟢' if is_long else '🔴'} *{esc(label)}*\n"
        f"💰 Entrada: `${esc(fmt_price(price))}`\n"
        f"🛑 Stop: `${esc(d(stop))}`\n"
        f"🎯 TP1 \\(1\\.8R\\): `${esc(d(tp1))}`\n"
        f"✨ TP2 \\(2\\.5R\\): `${esc(d(tp2))}`\n"
        f"🏆 Final \\(4R\\): `${esc(d(final))}`\n"
        f"📊 Score: *{esc(score)}/145* \\| RSI: {esc(f'{rsi:.0f}')} \\| ADX: {esc(f'{adx:.0f}')}\n"
        f"📈 Trend: {esc(trend)} \\| Kalman: {esc(k_str)}\n"
        f"⏰ {esc(now)}"
    )
    url=f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with session.post(url,json={"chat_id":TG_CHATID,"text":text,"parse_mode":"MarkdownV2"},
                                timeout=aiohttp.ClientTimeout(total=10)) as r:
            data=await r.json()
            if data.get("ok"): log.info(f"✅ {sig_type} {short} Score:{score} RSI:{rsi:.0f} ADX:{adx:.0f} [{SIGNAL_MODE}]")
            else: log.warning(f"❌ {data.get('description')}")
    except Exception as e: log.error(f"Erro: {e}")

# ── BINANCE ───────────────────────────────────────────────────────────────────

async def fetch_candles(session, sym, tf, limit=250):
    url=f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={tf}&limit={limit}"
    try:
        async with session.get(url,timeout=aiohttp.ClientTimeout(total=10)) as r:
            data=await r.json()
            if not isinstance(data,list) or len(data)<60: return None
            return [{"o":float(k[1]),"h":float(k[2]),"l":float(k[3]),"c":float(k[4]),"v":float(k[5])} for k in data]
    except: return None

def load_state():
    try:
        if STATE_FILE.exists(): return json.loads(STATE_FILE.read_text())
    except: pass
    return {}

def save_state(state):
    try: STATE_FILE.write_text(json.dumps(state))
    except: pass

# ── MAIN ──────────────────────────────────────────────────────────────────────

async def main():
    if not TG_TOKEN or not TG_CHATID:
        log.error("❌ Configure TG_TOKEN e TG_CHATID!"); return
    last_sig=load_state(); now=time.time(); sent=0
    log.info(f"🚀 GAUSS+DNA v2 | Modo: {SIGNAL_MODE} | TF: {TIMEFRAME} | {len(COINS)} moedas")
    async with aiohttp.ClientSession() as session:
        for sym,label,short in COINS:
            candles=await fetch_candles(session,sym,TIMEFRAME)
            if not candles: await asyncio.sleep(0.4); continue
            result=analyze(sym,candles)
            if not result: await asyncio.sleep(0.4); continue
            log.info(f"{short:7s} | Score {result['score']:+4d} | RSI {result['rsi']:5.1f} | ADX {result['adx']:5.1f} | K:{'UP' if result['kalman_up'] else 'DN'} | OBV:{'↑' if result['obv_bull'] else '↓'} | {result['sig'] or '—'}")
            if result["sig"]:
                if now-last_sig.get(sym,0)>=COOLDOWN:
                    last_sig[sym]=now; sent+=1
                    await send_telegram(session,sym,label,short,result["sig"],result["price"],
                                        result["atr"],result["score"],result["rsi"],result["adx"],
                                        result["trend"],result["kalman_up"],
                                        result["swing_low"],result["swing_high"])
                else:
                    mins=int((COOLDOWN-(now-last_sig.get(sym,0)))/60)
                    log.info(f"  ⏳ {short} cooldown {mins}min")
            await asyncio.sleep(0.4)
    save_state(last_sig)
    log.info(f"✅ Concluído. Sinais: {sent} [{SIGNAL_MODE}]")

if __name__=="__main__":
    asyncio.run(main())
