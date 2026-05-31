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
TIMEFRAMES   = [t.strip() for t in os.environ.get("TIMEFRAMES", TIMEFRAME).split(",")]
SIGNAL_MODE  = os.environ.get("SIGNAL_MODE", "FLEX").upper()
LOOP_MODE    = os.environ.get("LOOP_MODE", "false").lower() == "true"
TEST_MODE    = os.environ.get("TEST_MODE", "false").lower() == "true"
DYNAMIC_SCAN = os.environ.get("DYNAMIC_SCAN", "true").lower() == "true"
SCANNER_TOP  = int(os.environ.get("SCANNER_TOP", "50"))   # top 50 por volume
SCAN_EVERY   = int(os.environ.get("SCAN_EVERY", "16"))    # rescan a cada N ciclos (~4h em 15m)
STATE_FILE   = Path("last_signals.json")
CAPITAL      = float(os.environ.get("CAPITAL", "180"))   # capital total em USD
RISK_PCT     = float(os.environ.get("RISK_PCT", "0.03")) # risco por trade (3%)

def tf_to_minutes(tf):
    """Converte '15m', '1h', '4h' em minutos."""
    tf = tf.lower()
    if tf.endswith('m'): return int(tf[:-1])
    if tf.endswith('h'): return int(tf[:-1]) * 60
    if tf.endswith('d'): return int(tf[:-1]) * 1440
    return 15

def seconds_to_candle_close(tf_min):
    """Segundos até o fechamento da próxima vela (alinhado ao horário UTC)."""
    interval = tf_min * 60
    elapsed = time.time() % interval
    return interval - elapsed

COINS = [
    # ── Mega caps ────────────────────────────────────────────────────────────
    ("BTCUSDT","BTC/USDT","BTC"),("ETHUSDT","ETH/USDT","ETH"),
    ("BNBUSDT","BNB/USDT","BNB"),("XRPUSDT","XRP/USDT","XRP"),
    ("TRXUSDT","TRX/USDT","TRX"),("ADAUSDT","ADA/USDT","ADA"),
    # ── L1 — alta volatilidade e tendências limpas ────────────────────────
    ("SOLUSDT","SOL/USDT","SOL"),("AVAXUSDT","AVAX/USDT","AVAX"),
    ("SUIUSDT","SUI/USDT","SUI"),("APTUSDT","APT/USDT","APT"),
    ("NEARUSDT","NEAR/USDT","NEAR"),("TONUSDT","TON/USDT","TON"),
    ("SEIUSDT","SEI/USDT","SEI"),("TIAUSDT","TIA/USDT","TIA"),
    ("ALGOUSDT","ALGO/USDT","ALGO"),("VETUSDT","VET/USDT","VET"),
    ("HBARUSDT","HBAR/USDT","HBAR"),("STXUSDT","STX/USDT","STX"),
    # ── DeFi / infra ─────────────────────────────────────────────────────
    ("LINKUSDT","LINK/USDT","LINK"),("INJUSDT","INJ/USDT","INJ"),
    ("JUPUSDT","JUP/USDT","JUP"),("ARBUSDT","ARB/USDT","ARB"),
    ("OPUSDT","OP/USDT","OP"),("UNIUSDT","UNI/USDT","UNI"),
    ("AAVEUSDT","AAVE/USDT","AAVE"),("ENAUSDT","ENA/USDT","ENA"),
    ("ONDOUSDT","ONDO/USDT","ONDO"),("GRTUSDT","GRT/USDT","GRT"),
    # ── IA / narrativa ───────────────────────────────────────────────────
    ("FETUSDT","FET/USDT","FET"),("TAOUSDT","TAO/USDT","TAO"),
    ("RENDERUSDT","RENDER/USDT","RENDER"),("WLDUSDT","WLD/USDT","WLD"),
    ("IMXUSDT","IMX/USDT","IMX"),
    # ── Meme coins com alta liquidez ─────────────────────────────────────
    ("DOGEUSDT","DOGE/USDT","DOGE"),("PEPEUSDT","PEPE/USDT","PEPE"),
    ("WIFUSDT","WIF/USDT","WIF"),("SHIBUSDT","SHIB/USDT","SHIB"),
    ("FLOKIUSDT","FLOKI/USDT","FLOKI"),("BONKUSDT","BONK/USDT","BONK"),
    # ── High beta estabelecidos ───────────────────────────────────────────
    ("DOTUSDT","DOT/USDT","DOT"),("ATOMUSDT","ATOM/USDT","ATOM"),
    ("LTCUSDT","LTC/USDT","LTC"),("FILUSDT","FIL/USDT","FIL"),
    ("ARUSDT","AR/USDT","AR"),
    # ── L2 / interop ─────────────────────────────────────────────────────
    ("STRKUSDT","STRK/USDT","STRK"),("ZETAUSDT","ZETA/USDT","ZETA"),
    ("PYTHUSDT","PYTH/USDT","PYTH"),
    # ── Gaming / metaverso ───────────────────────────────────────────────
    ("AXSUSDT","AXS/USDT","AXS"),("SANDUSDT","SAND/USDT","SAND"),
    ("MANAUSDT","MANA/USDT","MANA"),
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

def alma_series(src, length=50, offset=0.85, sigma=6):
    """Arnaud Legoux Moving Average — idêntico ao ta.alma() do Pine Script."""
    import math
    n = len(src)
    m = math.floor(offset * (length - 1))
    s = length / sigma
    w = [math.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(length)]
    w_sum = sum(w)
    out = [float('nan')] * (length - 1)
    for i in range(length - 1, n):
        val = sum(w[j] * src[i - length + 1 + j] for j in range(length)) / w_sum
        out.append(val)
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

    # EMAs (com valores anteriores para detecção de cruzamento)
    e10_arr=ema_series(closes,10); e10=e10_arr[-1]; e10_p=e10_arr[-2]
    e21_arr=ema_series(closes,21); e21=e21_arr[-1]; e21_p=e21_arr[-2]
    e50_arr=ema_series(closes,50); e50=e50_arr[-1]; e50_p=e50_arr[-2]
    e200a=ema_series(closes,200); e200=e200a[-1]; e200p=e200a[-4] if n>4 else e200
    price_p=closes[-2]

    # ATR
    atr_arr=atr_series(candles,14); atr=max(atr_arr[-1],1e-10)

    # Kalman (com aceleração: spread crescendo = momentum se fortalecendo)
    ks=kalman_filter(closes,50); kl=kalman_filter(closes,150)
    kalman_up=ks[-1]>kl[-1]; kalman_down=ks[-1]<kl[-1]
    kalman_spread=ks[-1]-kl[-1]; kalman_spread_p=ks[-2]-kl[-2]
    kalman_accel_up=kalman_spread>kalman_spread_p>0
    kalman_accel_down=kalman_spread<kalman_spread_p<0

    # MACD (bull3/bear3 = 3 barras consecutivas para ELITE; recovering para early)
    ml,sl_v,hist,hist_p,hist_pp=macd_calc(closes)
    macd_bull=ml>sl_v and hist>hist_p and hist>0
    macd_bear=ml<sl_v and hist<hist_p and hist<0
    macd_bull3=macd_bull and hist_p>hist_pp        # 3 barras crescentes (sinal mais limpo)
    macd_bear3=macd_bear and hist_p<hist_pp        # 3 barras decrescentes
    macd_recovering=hist>hist_p                    # histograma subindo (para early long)
    macd_exhausting=hist<hist_p                    # histograma caindo (para early short)

    # Heikin-Ashi (série correta — open baseado no HA anterior)
    ha=ha_series(candles)
    ha_bull=ha[-1]["c"]>ha[-1]["o"] and ha[-2]["c"]>ha[-2]["o"]
    ha_bear=ha[-1]["c"]<ha[-1]["o"] and ha[-2]["c"]<ha[-2]["o"]

    # RSI (elite usa zona mais estreita + momentum direcional)
    rsi=rsi_calc(closes[-50:])
    rsi_prev=rsi_calc(closes[-53:-3]) if n>=53 else rsi
    rsi_rising=rsi>rsi_prev; rsi_falling=rsi<rsi_prev
    rsi_bull=50<rsi<70; rsi_bear=30<rsi<50              # score + FLEX (zona ampla)
    rsi_bull_elite=48<rsi<65 and rsi_rising              # ELITE: evita sobrecompra + momentum
    rsi_bear_elite=35<rsi<52 and rsi_falling             # ELITE: evita sobrevenda + momentum

    # DMI/ADX (strictly rising: ADX deve estar subindo, não apenas estável)
    pdi,mdi,adx,adx_p=dmi_adx(candles[-60:])
    adx_long_ok=adx>22 and pdi>mdi and adx>adx_p
    adx_short_ok=adx>22 and mdi>pdi and adx>adx_p

    # Volume (v_strong2: 2 velas consecutivas com bom volume = confirmação mais sólida)
    vol_ma=sum(vols[-20:])/20
    v_strong=vols[-1]>vol_ma*1.1
    v_strong2=v_strong and vols[-2]>vol_ma*0.9

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

    not_ext_long=(price-e50)/atr<4.0
    not_ext_short=(e50-price)/atr<4.0

    # ── ANTI-TOPO / ANTI-FUNDO ───────────────────────────────────────────────
    bb_range=max(bb_upper-bb_lower,1e-10)
    price_bb_pos=(price-bb_lower)/bb_range

    # Só bloqueia se literalmente no topo/fundo da banda (>97% ou <3%)
    near_bb_top=price_bb_pos>0.97   # acima da banda superior — sobrecomprado na BB
    near_bb_bot=price_bb_pos<0.03   # abaixo da banda inferior — sobrevendido na BB

    # Preço muito esticado (>3 ATR da EMA21) — movimento já foi feito
    ext_above_ema21=(price-e21)/atr>3.0
    ext_below_ema21=(e21-price)/atr>3.0

    # Volume secando: volume atual < 60% da média E < 70% das últimas 3 velas
    vol3=[vols[-4],vols[-3],vols[-2]]
    vol_drying=vols[-1]<vol_ma*0.6 and vols[-1]<min(vol3)*0.7

    rsi_not_overbought=rsi<75
    rsi_not_oversold=rsi>25

    # Pullback: preço tocou EMA10 ou EMA21 nas últimas 5 velas e já voltou acima
    def _low_touched_ema(ema_arr, n=5):
        return any(lows[i]<=ema_arr[i]*1.008 for i in range(-n,-1))
    def _high_touched_ema(ema_arr, n=5):
        return any(highs[i]>=ema_arr[i]*0.992 for i in range(-n,-1))

    pullback_bull=(_low_touched_ema(e10_arr) or _low_touched_ema(e21_arr)) and price>e10 and price>opens[-1] and ha_bull
    pullback_bear=(_high_touched_ema(e10_arr) or _high_touched_ema(e21_arr)) and price<e10 and price<opens[-1] and ha_bear

    # Candle de exaustão: sombra superior > 40% do range → possível reversão no topo
    uwick_ratio=(highs[-1]-max(opens[-1],price))/max(highs[-1]-lows[-1],1e-10)
    lwick_ratio=(min(opens[-1],price)-lows[-1])/max(highs[-1]-lows[-1],1e-10)
    exhaustion_top=uwick_ratio>0.40 and price<(highs[-1]-bb_range*0.02)  # rejeição no topo
    exhaustion_bot=lwick_ratio>0.40 and price>(lows[-1]+bb_range*0.02)    # rejeição no fundo

    # Filtro combinado: evita entrar no topo ou no fundo de uma move
    safe_long=not near_bb_top and not ext_above_ema21 and not vol_drying and not exhaustion_top and rsi_not_overbought
    safe_short=not near_bb_bot and not ext_below_ema21 and not vol_drying and not exhaustion_bot and rsi_not_oversold

    # Consistência de tendência: 4 das últimas 5 velas acima/abaixo da EMA21
    bulls_5=sum(1 for i in range(-5,0) if closes[i]>e21_arr[i])
    trend_consistent_bull=bulls_5>=4
    trend_consistent_bear=bulls_5<=1

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

    # Cruzamentos de médias móveis
    cross_10_21_bull=e10_p<=e21_p and e10>e21   # EMA10 cruzou acima da EMA21
    cross_10_21_bear=e10_p>=e21_p and e10<e21   # EMA10 cruzou abaixo da EMA21
    cross_21_50_bull=e21_p<=e50_p and e21>e50   # EMA21 cruzou acima da EMA50
    cross_21_50_bear=e21_p>=e50_p and e21<e50   # EMA21 cruzou abaixo da EMA50
    px_e50_bull=price_p<=e50_p and price>e50     # Preço cruzou acima da EMA50
    px_e50_bear=price_p>=e50_p and price<e50     # Preço cruzou abaixo da EMA50

    any_cross_bull=cross_10_21_bull or cross_21_50_bull or px_e50_bull
    any_cross_bear=cross_10_21_bear or cross_21_50_bear or px_e50_bear

    # Label do cruzamento (mais significativo tem prioridade)
    if cross_21_50_bull: cross_label="EMA21 > EMA50"
    elif px_e50_bull: cross_label="Preco > EMA50"
    elif cross_10_21_bull: cross_label="EMA10 > EMA21"
    elif cross_21_50_bear: cross_label="EMA21 < EMA50"
    elif px_e50_bear: cross_label="Preco < EMA50"
    elif cross_10_21_bear: cross_label="EMA10 < EMA21"
    else: cross_label=""

    # Swing levels para stop baseado em estrutura de mercado (8 velas = mais representativo)
    swing_low=min(lows[-9:-1]); swing_high=max(highs[-9:-1])

    # ── TRENDILO (ALMA do % de variação + bandas RMS) ─────────────────────────
    pch = [0.0] + [(closes[i]-closes[i-1])/closes[i]*100 for i in range(1,n)]
    avpch = alma_series(pch, 50, 0.85, 6)
    # RMS rolling dos últimos 50 valores de avpch
    import math as _math
    rms_vals = [_math.sqrt(sum(v*v for v in avpch[max(0,i-49):i+1])/min(i+1,50))
                for i in range(len(avpch))]
    trendilo_long  = not _math.isnan(avpch[-1]) and avpch[-1] > rms_vals[-1]
    trendilo_short = not _math.isnan(avpch[-1]) and avpch[-1] < -rms_vals[-1]

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
        (10 if ha_bull else -10 if ha_bear else 0)+
        (5 if kalman_accel_up else -5 if kalman_accel_down else 0)+
        (5 if trend_consistent_bull else -5 if trend_consistent_bear else 0)+
        (10 if trendilo_long else -10 if trendilo_short else 0)
    )
    score=max(-145,min(145,score))

    # ── SINAIS ELITE ── (máxima assertividade: todos os filtros de qualidade)
    long_elite=(strong_trend and trend_bull and align_bull and e200_rising and
                macd_bull3 and ha_bull and f_bull and f_strong and adx_long_ok and
                rsi_bull_elite and (v_strong2 or obv_bull) and not_ext_long and
                kalman_accel_up and above_vwap and trend_consistent_bull and
                (bull_impulse or liq_long) and score>65 and safe_long)
    short_elite=(strong_trend and trend_bear and align_bear and e200_falling and
                 macd_bear3 and ha_bear and f_bear and f_strong and adx_short_ok and
                 rsi_bear_elite and (v_strong2 or obv_bear) and not_ext_short and
                 kalman_accel_down and below_vwap and trend_consistent_bear and
                 (bear_impulse or liq_short) and score<-65 and safe_short)
    early_long=(adx_long_ok and (v_strong or obv_bull) and sell_exhaust and liq_long and
                bull_absorb and f_bull and trend_bull and e200_rising and
                kalman_up and above_vwap and macd_recovering and safe_long)
    early_short=(adx_short_ok and (v_strong or obv_bear) and buy_exhaust and liq_short and
                 bear_absorb and f_bear and trend_bear and e200_falling and
                 kalman_down and below_vwap and macd_exhausting and safe_short)

    # Sinal de cruzamento (sem safe_long — não bloquear crossovers válidos)
    long_cross=(any_cross_bull and score>10 and adx>15 and
                (macd_bull or ha_bull) and (f_bull or obv_bull) and
                v_strong and not_ext_long and price>e200*0.97)
    short_cross=(any_cross_bear and score<-10 and adx>15 and
                 (macd_bear or ha_bear) and (f_bear or obv_bear) and
                 v_strong and not_ext_short and price<e200*1.03)

    # ── SINAL PULLBACK ── entrada após recuo nas EMAs (melhor preço)
    # trend_bull usa align relaxado (e10>e21>e50, sem exigir e50>e200)
    trend_bull_relaxed=price>e200 and e10>e21 and e21>e50
    long_pullback=(pullback_bull and trend_bull_relaxed and (macd_bull or macd_recovering) and
                   adx>18 and (f_bull or obv_bull) and v_strong and
                   above_vwap and score>15 and not any_cross_bull)
    trend_bear_relaxed=price<e200 and e10<e21 and e21<e50
    short_pullback=(pullback_bear and trend_bear_relaxed and (macd_bear or macd_exhausting) and
                    adx>18 and (f_bear or obv_bear) and v_strong and
                    below_vwap and score<-15 and not any_cross_bear)

    # ── SINAIS FLEX ── lógica idêntica à versão HTML que gera sinais ────────────
    # MACD relaxado: só direção (acima/abaixo do sinal) — sem exigir histograma
    macd_bull_r=ml>sl_v and hist>hist_p   # direção + histograma crescendo
    macd_bear_r=ml<sl_v and hist<hist_p
    # Volume: 2 velas consecutivas com bom volume (mais sólido)
    vol_avg=vols[-1]>vol_ma*1.1 and vols[-2]>vol_ma*0.9
    # Tendência relaxada: sem exigir e50>e200
    tbull_r=price>e200 and e10>e21 and e21>e50
    tbear_r=price<e200 and e10<e21 and e21<e50
    # Tendência ainda mais relaxada: só exige EMAs alinhadas (sem EMA200)
    tbull_loose=e10>e21 and e21>e50
    tbear_loose=e10<e21 and e21<e50

    # Score FLEX: credita alinhamento EMA mesmo sem EMA200
    flex_bonus_bull = 30 if (tbull_loose and not trend_bull) else 0
    flex_bonus_bear = 30 if (tbear_loose and not trend_bear) else 0
    flex_score = score + flex_bonus_bull - flex_bonus_bear

    # ── FILTROS INSTITUCIONAIS ─────────────────────────────────────────────────
    adx_rising = adx > adx_p
    sideways = bb_squeeze and adx < 25
    not_ext_long_tight  = (price - e21) / atr < 2.5 and rsi < 74
    not_ext_short_tight = (e21 - price) / atr < 2.5 and rsi > 26

    long_flex = (flex_score > 40 and macd_bull_r and adx > 20 and adx_rising and
                 not sideways and not_ext_long_tight and trendilo_long and
                 safe_long and ha_bull and v_strong and (obv_bull or f_bull) and
                 e200_rising and 38 < rsi < 68)
    short_flex = (flex_score < -40 and macd_bear_r and adx > 20 and adx_rising and
                  not sideways and not_ext_short_tight and trendilo_short and
                  safe_short and ha_bear and v_strong and (obv_bear or f_bear) and
                  e200_falling and 32 < rsi < 62)

    sig=None; sig_source=""
    if SIGNAL_MODE=="ELITE":
        if long_elite or early_long: sig="LONG"; sig_source="ELITE"
        elif short_elite or early_short: sig="SHORT"; sig_source="ELITE"
    else:  # FLEX — pullback > cross > flex (prioridade melhor preço)
        if long_pullback: sig="LONG"; sig_source="PULLBACK"
        elif short_pullback: sig="SHORT"; sig_source="PULLBACK"
        elif long_cross: sig="LONG"; sig_source=f"CROSS:{cross_label}"
        elif short_cross: sig="SHORT"; sig_source=f"CROSS:{cross_label}"
        elif long_flex: sig="LONG"; sig_source="FLEX"
        elif short_flex: sig="SHORT"; sig_source="FLEX"

    # ── QUALIDADE DO SINAL (S / A / B) ───────────────────────────────────────
    # Conta quantos dos filtros premium estão alinhados
    quality_score = 0
    if sig == "LONG":
        quality_score += 3 if trend_bull else 0
        quality_score += 2 if align_bull else 0
        quality_score += 2 if macd_bull3 else (1 if macd_bull else 0)
        quality_score += 2 if ha_bull else 0
        quality_score += 2 if adx_long_ok else (1 if adx > 15 else 0)
        quality_score += 1 if obv_bull else 0
        quality_score += 1 if above_vwap else 0
        quality_score += 1 if v_strong2 else (0 if not v_strong else 0)
        quality_score += 1 if kalman_accel_up else 0
        quality_score += 1 if e200_rising else 0
        quality_score += 1 if f_strong else 0
        quality_score += 1 if trend_consistent_bull else 0
    elif sig == "SHORT":
        quality_score += 3 if trend_bear else 0
        quality_score += 2 if align_bear else 0
        quality_score += 2 if macd_bear3 else (1 if macd_bear else 0)
        quality_score += 2 if ha_bear else 0
        quality_score += 2 if adx_short_ok else (1 if adx > 15 else 0)
        quality_score += 1 if obv_bear else 0
        quality_score += 1 if below_vwap else 0
        quality_score += 1 if v_strong2 else 0
        quality_score += 1 if kalman_accel_down else 0
        quality_score += 1 if e200_falling else 0
        quality_score += 1 if f_strong else 0
        quality_score += 1 if trend_consistent_bear else 0

    if quality_score >= 14:   signal_grade = "S"   # setup perfeito
    elif quality_score >= 10: signal_grade = "A"   # setup sólido
    elif quality_score >= 6:  signal_grade = "B"   # setup básico
    else:                     signal_grade = "B"

    # Log de diagnóstico detalhado
    if not sig:
        if score < -25:
            b=[]
            if not tbear_r: b.append(f"tbear_r=F(p{'<' if price<e200 else '>'}e200,e10{'<' if e10<e21 else '>'}e21{'<' if e21<e50 else '>'}e50)")
            if not (macd_bear_r or ha_bear): b.append(f"macd_r={macd_bear_r}/ha={ha_bear}")
            if adx<=13: b.append(f"adx={adx:.1f}<=13")
            if not (v_strong or vol_avg): b.append("vol=F")
            log.info(f"  SHORT-BLOCKED {sym}: score={score:+d} | {'; '.join(b) if b else 'ok?'}")
        elif score > 25:
            b=[]
            if not tbull_r: b.append("tbull_r=F")
            if not (macd_bull_r or ha_bull): b.append(f"macd_r={macd_bull_r}/ha={ha_bull}")
            if adx<=13: b.append(f"adx={adx:.1f}<=13")
            if not (v_strong or vol_avg): b.append("vol=F")
            log.info(f"  LONG-BLOCKED {sym}: score={score:+d} | {'; '.join(b) if b else 'ok?'}")
        else:
            log.info(f"  no-sig {sym}: score={score:+d} insuf")

    return {"price":price,"score":score,"atr":atr,"rsi":rsi,"adx":adx,
            "kalman_up":kalman_up,"trend":"BULL" if trend_bull else "BEAR" if trend_bear else "NEUTRO",
            "sig":sig,"sig_source":sig_source,"swing_low":swing_low,"swing_high":swing_high,
            "ha_bull":ha_bull,"obv_bull":obv_bull,"above_vwap":above_vwap,
            "signal_grade":signal_grade,"quality_score":quality_score,
            "tbull_r":tbull_r,"tbear_r":tbear_r}

def analyze_mtf_entry(sym, candles_15m, h1_bull, h1_bear):
    """Entrada na 15m dado setup confirmado na 1h.
    Procura pullback até EMA21/EMA50 com bounce — stop no swing da correção."""
    n = len(candles_15m)
    if n < 50: return None
    closes = [c["c"] for c in candles_15m]
    highs  = [c["h"] for c in candles_15m]
    lows   = [c["l"] for c in candles_15m]
    opens  = [c["o"] for c in candles_15m]
    vols   = [c["v"] for c in candles_15m]
    price  = closes[-1]

    e10_arr = ema_series(closes, 10); e10 = e10_arr[-1]
    e21_arr = ema_series(closes, 21); e21 = e21_arr[-1]
    e50_arr = ema_series(closes, 50); e50 = e50_arr[-1]
    e200_arr = ema_series(closes, 200); e200 = e200_arr[-1]
    atr_arr = atr_series(candles_15m, 14); atr = max(atr_arr[-1], 1e-10)

    ml, sl_v, hist, hist_p, _ = macd_calc(closes)
    macd_bull_r = ml > sl_v and hist > hist_p   # direção + histograma crescendo
    macd_bear_r = ml < sl_v and hist < hist_p

    ha = ha_series(candles_15m)
    ha_body = abs(ha[-1]["c"] - ha[-1]["o"])
    ha_body_ok = ha_body > atr * 0.2            # corpo HA mínimo = não é doji
    ha_bull = ha[-1]["c"] > ha[-1]["o"] and ha[-2]["c"] > ha[-2]["o"] and ha_body_ok
    ha_bear = ha[-1]["c"] < ha[-1]["o"] and ha[-2]["c"] < ha[-2]["o"] and ha_body_ok

    rsi = rsi_calc(closes[-50:])
    vol_ma = sum(vols[-20:]) / 20
    # Volume surge: spike claro no bounce (não só acima da média)
    vol_surge = vols[-1] > vol_ma * 1.2 and vols[-1] >= vols[-2]

    obv = obv_calc(closes, vols)
    obv_ema = ema_series(obv, 20)
    obv_bull = obv[-1] > obv_ema[-1] and obv[-1] > obv[-6]
    obv_bear = obv[-1] < obv_ema[-1] and obv[-1] < obv[-6]

    _, _, adx, adx_p_mtf = dmi_adx(candles_15m[-60:])
    adx_rising_mtf = adx > adx_p_mtf

    # EMA200 direção: confirma tendência macro no 30m
    e200_rising_mtf  = e200_arr[-1] > e200_arr[-6]
    e200_falling_mtf = e200_arr[-1] < e200_arr[-6]

    # Origem do pullback: preço veio de acima da EMA21 (pullback real, não breakdown)
    came_from_above = any(closes[i] > e21_arr[i] for i in range(-8, -2))
    came_from_below = any(closes[i] < e21_arr[i] for i in range(-8, -2))

    # Alinhamento das EMAs: tendência estrutural confirmada
    ema_aligned_long  = e10 > e21 > e50
    ema_aligned_short = e10 < e21 < e50

    # Mercado lateral: EMAs coladas + ADX fraco = sem direção
    sideways_mtf = abs(e21 - e50) / atr < 0.3 and adx < 22

    # Trendilo: ALMA do % de variação vs bandas RMS — confirma momentum direcional
    import math as _math
    pch_m = [0.0] + [(closes[i]-closes[i-1])/closes[i]*100 for i in range(1, len(closes))]
    avpch_m = alma_series(pch_m, 50, 0.85, 6)
    rms_m = [_math.sqrt(sum(v*v for v in avpch_m[max(0,i-49):i+1])/min(i+1,50))
             for i in range(len(avpch_m))]
    trendilo_long_mtf  = not _math.isnan(avpch_m[-1]) and avpch_m[-1] >  rms_m[-1]
    trendilo_short_mtf = not _math.isnan(avpch_m[-1]) and avpch_m[-1] < -rms_m[-1]

    # Kalman Filter — confirma momentum direcional no 30m
    ks_m = kalman_filter(closes, 50); kl_m = kalman_filter(closes, 150)
    kalman_up_mtf   = ks_m[-1] > kl_m[-1]
    kalman_down_mtf = ks_m[-1] < kl_m[-1]
    ks_spread = ks_m[-1] - kl_m[-1]; ks_spread_p = ks_m[-2] - kl_m[-2]
    kalman_accel_up_mtf = ks_spread > ks_spread_p > 0
    kalman_accel_dn_mtf = ks_spread < ks_spread_p < 0

    # VWAP — suporte/resistência dinâmica por volume
    vwap_mtf      = vwap_calc(candles_15m)
    above_vwap_mtf = price > vwap_mtf
    below_vwap_mtf = price < vwap_mtf

    # Flow (pressão de vela — body-weighted volume)
    flow_raw_m = [((c["c"]-c["o"])/max(c["h"]-c["l"],1e-10))*c["v"] for c in candles_15m]
    flow_ema_m = ema_series(flow_raw_m, 13)
    flow_sma_m = sum(abs(f) for f in flow_ema_m[-20:]) / 20
    f_bull_mtf = flow_ema_m[-1] > 0 and abs(flow_ema_m[-1]) > flow_sma_m * 0.8
    f_bear_mtf = flow_ema_m[-1] < 0 and abs(flow_ema_m[-1]) > flow_sma_m * 0.8

    # Bollinger Bands — não entrar em extremo da banda
    bb_u_m, bb_l_m, _, _, _ = bb_calc(closes)
    bb_pos_m = (price - bb_l_m) / max(bb_u_m - bb_l_m, 1e-10)
    not_bb_top = bb_pos_m < 0.88
    not_bb_bot = bb_pos_m > 0.12

    # Força da tendência: EMA21 suficientemente afastada da EMA50
    trend_strong_mtf = abs(e21 - e50) / atr > 0.35

    # Zona de pullback: entrada só quando preço está próximo da EMA
    near_ema21_long  = abs(price - e21) < atr * 0.9 and price > e200
    near_ema50_long  = abs(price - e50) < atr * 1.2 and price > e200
    near_ema21_short = abs(price - e21) < atr * 0.9 and price < e200
    near_ema50_short = abs(price - e50) < atr * 1.2 and price < e200

    in_pullback_long  = near_ema21_long  or near_ema50_long
    in_pullback_short = near_ema21_short or near_ema50_short

    # Bounce: HA + MACD + volume spike (todos obrigatórios)
    bounce_long  = macd_bull_r and ha_bull and price > opens[-1] and (vol_surge or obv_bull)
    bounce_short = macd_bear_r and ha_bear and price < opens[-1] and (vol_surge or obv_bear)

    # Não perseguir: entrada só perto da EMA, não esticado
    not_chasing_long  = (price - e21) / atr < 1.8
    not_chasing_short = (e21 - price) / atr < 1.8

    # Stop no swing da correção (últimas 12 velas = estrutura mais real)
    swing_low  = min(lows[-13:-1])
    swing_high = max(highs[-13:-1])
    stop_long  = swing_low  - atr * 0.5
    stop_short = swing_high + atr * 0.5

    # RSI zone: evita entrar em extremos, mantém na zona saudável de pullback
    rsi_ok_long  = 40 < rsi < 65
    rsi_ok_short = 35 < rsi < 60

    sig = None
    if (h1_bull and in_pullback_long and bounce_long and
            adx > 22 and adx_rising_mtf and not sideways_mtf and
            not_chasing_long and rsi_ok_long and trendilo_long_mtf and
            e200_rising_mtf and came_from_above and ema_aligned_long and
            kalman_up_mtf and above_vwap_mtf and f_bull_mtf and
            not_bb_top and trend_strong_mtf):
        sig = "LONG"
    elif (h1_bear and in_pullback_short and bounce_short and
              adx > 22 and adx_rising_mtf and not sideways_mtf and
              not_chasing_short and rsi_ok_short and trendilo_short_mtf and
              e200_falling_mtf and came_from_below and ema_aligned_short and
              kalman_down_mtf and below_vwap_mtf and f_bear_mtf and
              not_bb_bot and trend_strong_mtf):
        sig = "SHORT"

    if not sig:
        return None

    is_long = sig == "LONG"
    stop    = stop_long if is_long else stop_short
    near21  = near_ema21_long if is_long else near_ema21_short

    # Quality score MTF (0–10)
    quality_mtf = 0
    if is_long:
        quality_mtf += 2 if kalman_accel_up_mtf else (1 if kalman_up_mtf else 0)
        quality_mtf += 2 if vol_surge else (1 if vols[-1] > vol_ma else 0)
        quality_mtf += 1 if above_vwap_mtf else 0
        quality_mtf += 1 if f_bull_mtf else 0
        quality_mtf += 1 if obv_bull else 0
        quality_mtf += 1 if trendilo_long_mtf else 0
        quality_mtf += 1 if trend_strong_mtf else 0
        quality_mtf += 1 if kalman_accel_up_mtf else 0
    else:
        quality_mtf += 2 if kalman_accel_dn_mtf else (1 if kalman_down_mtf else 0)
        quality_mtf += 2 if vol_surge else (1 if vols[-1] > vol_ma else 0)
        quality_mtf += 1 if below_vwap_mtf else 0
        quality_mtf += 1 if f_bear_mtf else 0
        quality_mtf += 1 if obv_bear else 0
        quality_mtf += 1 if trendilo_short_mtf else 0
        quality_mtf += 1 if trend_strong_mtf else 0
        quality_mtf += 1 if kalman_accel_dn_mtf else 0
    grade_mtf = "S" if quality_mtf >= 7 else "A" if quality_mtf >= 5 else "B"

    return {
        "sig": sig, "sig_source": f"MTF_PULLBACK [1h→30m] EMA{'21' if near21 else '50'}",
        "price": price, "atr": atr,
        "swing_low": swing_low, "swing_high": swing_high,
        "rsi": rsi, "adx": adx, "score": 0,
        "kalman_up": kalman_up_mtf, "trend": "BULL" if is_long else "BEAR",
        "signal_grade": grade_mtf, "quality_score": quality_mtf,
    }

# ── TELEGRAM ─────────────────────────────────────────────────────────────────

async def send_telegram(session, sym, label, short, sig_type, price, atr, score,
                        rsi, adx, trend, kalman_up, swing_low, swing_high,
                        sig_source, tf, signal_grade):
    is_long=sig_type=="LONG"

    # Stop estrutural: abaixo do swing com buffer de 0.5 ATR
    # Se swing estiver além de 3 ATR → setup ruim, não envia
    if is_long:
        stop = swing_low - atr * 0.5
        if (price - stop) > atr * 3.0:
            return   # risco/estrutura incompatível — skip
    else:
        stop = swing_high + atr * 0.5
        if (stop - price) > atr * 3.0:
            return
    risk=abs(price-stop)
    if risk <= 0: return

    # TP dinâmico por grade — mínimo 2R no TP1 (protege capital)
    if signal_grade=="S":
        r1,r2,r_final=2.5,4.5,8.0   # setup perfeito — deixa correr
    elif signal_grade=="A":
        r1,r2,r_final=2.0,3.5,6.0   # setup sólido
    else:
        r1,r2,r_final=2.0,3.0,5.0   # grade B com R/R mínimo 2:1

    tp1  =price+risk*r1     if is_long else price-risk*r1
    tp2  =price+risk*r2     if is_long else price-risk*r2
    final=price+risk*r_final if is_long else price-risk*r_final

    # Cálculo de posição baseado em capital e risco 3%
    risk_amount = CAPITAL * RISK_PCT          # ex: $5.40
    contracts   = risk_amount / risk if risk > 0 else 0  # unidades da moeda
    pos_value   = contracts * price           # valor em USD (spot)
    pos_5x      = pos_value / 5               # collateral com 5x alavancagem

    grade_info={
        "S": ("🏆 GRADE S — Setup perfeito",),
        "A": ("⭐ GRADE A — Setup sólido",),
        "B": ("📊 GRADE B — Setup básico",),
    }
    grade_label=grade_info[signal_grade][0]

    if sig_source.startswith("MTF"):
        mode_tag=f"📡 MTF PULLBACK 1H→{tf.upper()}"; cross_info=""
    elif sig_source=="PULLBACK":
        mode_tag="🎯 DNA PULLBACK"; cross_info=""
    elif sig_source.startswith("CROSS"):
        mode_tag="🔀 DNA CROSS"
        cross_info=sig_source.split(":",1)[1]
    elif SIGNAL_MODE=="ELITE":
        mode_tag="🔬 DNA ELITE KALMAN"; cross_info=""
    else:
        mode_tag="⚡ DNA FLEX"; cross_info=""

    def d(v): return f"{v:.6f}" if v<0.01 else f"{v:.4f}" if v<1 else f"{v:.2f}"
    def esc(v):
        # Escape para texto fora de backticks (MarkdownV2)
        s=str(v)
        s=s.replace('\\','\\\\')
        for ch in r"_*[]()~`>#+=|{}.!-": s=s.replace(ch,f"\\{ch}")
        return s
    def raw(v):
        # Dentro de backticks só backslash precisa ser escapado
        return str(v).replace('\\','\\\\')

    now=datetime.now().strftime("%H:%M — %d/%m/%Y")
    k_str="↑" if kalman_up else "↓"
    cross_line=f"📉 Cross: {esc(cross_info)}\n" if cross_info else ""

    text=(
        f"🚨 *{esc(mode_tag)} — {sig_type}*\n\n"
        f"{'🟢' if is_long else '🔴'} *{esc(label)}* \\| ⏱ {esc(tf)}\n"
        f"{cross_line}"
        f"{esc(grade_label)}\n\n"
        f"💰 Entrada: `${raw(fmt_price(price))}`\n"
        f"🛑 Stop: `${raw(d(stop))}`\n"
        f"🎯 TP1 \\({esc(str(r1))}R\\): `${raw(d(tp1))}` → fechar 40%\n"
        f"✨ TP2 \\({esc(str(r2))}R\\): `${raw(d(tp2))}` → fechar 35%\n"
        f"🏆 Final \\({esc(str(r_final))}R\\): `${raw(d(final))}` → últimos 25%\n\n"
        f"📐 *Gestão de risco \\(3% de ${raw(f'{CAPITAL:.0f}')}\\)*\n"
        f"  Risco: `${raw(f'{risk_amount:.2f}')}`\n"
        f"  Spot: `{raw(f'{contracts:.4f}')} {raw(short)}` \\(aprox `${raw(f'{pos_value:.2f}')} USDT`\\)\n"
        f"  5x Lev: `${raw(f'{pos_5x:.2f}')} collateral`\n\n"
        f"📊 Score: *{esc(score)}/145* \\| RSI: {esc(f'{rsi:.0f}')} \\| ADX: {esc(f'{adx:.0f}')}\n"
        f"📈 Trend: {esc(trend)} \\| Kalman: {esc(k_str)}\n"
        f"⏰ {esc(now)}"
    )
    url=f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with session.post(url,json={"chat_id":TG_CHATID,"text":text,"parse_mode":"MarkdownV2"},
                                timeout=aiohttp.ClientTimeout(total=10)) as r:
            data=await r.json()
            if data.get("ok"): log.info(f"✅ {sig_type} {short} Grade:{signal_grade} Score:{score} RSI:{rsi:.0f} ADX:{adx:.0f} [{sig_source}]")
            else: log.warning(f"❌ {data.get('description')}")
    except Exception as e: log.error(f"Erro: {e}")

# ── MEXC (formato igual ao Binance, sem bloqueio de IPs cloud) ───────────────
# MEXC usa "60m" em vez de "1h" e "4h" em vez de "4H"
_MEXC_TF={"1h":"60m","2h":"120m","4h":"4h","6h":"6h","8h":"8h","12h":"12h","1d":"1d"}

async def fetch_candles(session, sym, tf, limit=250):
    interval=_MEXC_TF.get(tf,tf)
    url=f"https://api.mexc.com/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}"
    try:
        async with session.get(url,timeout=aiohttp.ClientTimeout(total=10)) as r:
            data=await r.json()
        if not isinstance(data,list):
            log.warning(f"fetch_candles {sym} [{tf}]: {str(data)[:80]}")
            return None
        if len(data)<60: return None
        return [{"o":float(k[1]),"h":float(k[2]),"l":float(k[3]),"c":float(k[4]),"v":float(k[5])} for k in data]
    except Exception as e:
        log.warning(f"fetch_candles {sym} [{tf}]: {e}")
        return None

def load_state():
    try:
        if STATE_FILE.exists(): return json.loads(STATE_FILE.read_text())
    except: pass
    return {}

def save_state(state):
    try: STATE_FILE.write_text(json.dumps(state))
    except: pass

# ── RASTREADOR DINÂMICO DE MOEDAS ─────────────────────────────────────────────

# Stablecoins e tokens alavancados para excluir
_EXCLUDE = {"USDC","BUSD","TUSD","FDUSD","DAI","USDP","PAXG","WBTC","WETH",
            "EUR","GBP","BRL","UST","USDD","FRAX","USD1","USDE","USDT0"}
_EXCLUDE_SUB = ("UP","DOWN","BULL","BEAR","3L","3S","2L","2S","5L","5S")

async def fetch_top_usdt_pairs(session, min_vol_m=3.0, max_pairs=100):
    """Busca top pares USDT do MEXC ordenados por volume 24h (USD)."""
    url="https://api.mexc.com/api/v3/ticker/24hr"
    try:
        async with session.get(url,timeout=aiohttp.ClientTimeout(total=15)) as r:
            data=await r.json()
        if not isinstance(data,list): return []
        pairs=[]
        for t in data:
            sym=t["symbol"]
            if not sym.endswith("USDT"): continue
            base=sym[:-4]
            if base in _EXCLUDE: continue
            if any(sub in base for sub in _EXCLUDE_SUB): continue
            try:
                vol=float(t.get("quoteVolume","0"))
                if vol < min_vol_m*1e6: continue
                pairs.append((sym,base,vol))
            except: continue
        pairs.sort(key=lambda x:x[2],reverse=True)
        return pairs[:max_pairs]
    except Exception as e:
        log.warning(f"Scanner: erro ao buscar pares — {e}"); return []

def quick_rank(candles):
    """Score rápido para ranquear moedas candidatas. Retorna 0 se não serve."""
    if len(candles)<60: return 0
    closes=[c["c"] for c in candles]
    vols=[c["v"] for c in candles]
    price=closes[-1]
    # ATR%
    atr=atr_series(candles,14)[-1]
    atr_pct=(atr/price)*100
    if atr_pct<0.25 or atr_pct>4.0: return 0   # muito quieto ou muito volátil para $180
    # ADX
    try: _,_,adx,_=dmi_adx(candles[-60:])
    except: return 0
    if adx<15: return 0   # sem tendência
    # Trend
    e200=ema_series(closes,200)[-1]
    trend_ok=abs(price-e200)/e200>0.005  # preço não colado na EMA200
    # Volume crescente
    vol_ma=sum(vols[-20:])/20
    vol_ok=vols[-1]>vol_ma*1.0
    # Score composto
    atr_ideal=max(0,25-abs(atr_pct-1.5)*8)
    score=adx*0.40 + (20 if trend_ok else 0) + (15 if vol_ok else 0) + atr_ideal
    return score

async def scan_best_coins(session, tf="15m", top_n=20):
    """Varre o mercado e retorna as top_n moedas com melhores condições agora."""
    log.info(f"🔍 Rastreador iniciado — buscando melhores moedas [{tf}]...")
    pairs=await fetch_top_usdt_pairs(session)
    if not pairs:
        log.warning("Rastreador: sem dados, mantendo lista atual"); return None

    scored=[]
    for sym,base,vol_usd in pairs:
        candles=await fetch_candles(session,sym,tf,limit=250)
        if candles:
            s=quick_rank(candles)
            if s>0:
                scored.append((sym,f"{base}/USDT",base,s,vol_usd))
                log.info(f"  ✓ {base:8s} | Score {s:.0f} | Vol ${vol_usd/1e6:.0f}M")
        await asyncio.sleep(0.25)

    scored.sort(key=lambda x:x[3],reverse=True)
    top=[(s,l,b) for s,l,b,_,_ in scored[:top_n]]
    if not top: return None

    names=[b for _,_,b in top]
    log.info(f"✅ Top {len(top)} selecionadas: {', '.join(names)}")
    return top

# ── MAIN ──────────────────────────────────────────────────────────────────────

def in_trading_hours():
    """Só opera 09h-13h e 14h-21h no horário de Brasília (BRT = UTC-3)."""
    from datetime import timezone, timedelta
    brt = timezone(timedelta(hours=-3))
    h = datetime.now(brt).hour
    return (9 <= h < 13) or (14 <= h < 21)

async def run_cycle(session, last_sig, tf, coins):
    """Executa um ciclo completo de análise em todas as moedas para um timeframe."""
    now=time.time(); sent=0
    cooldown=max(tf_to_minutes(tf)*60, 14400)  # mínimo 4h entre sinais por moeda
    candidates=[]  # (abs_score, short, score, rsi, adx, reason)
    MAX_SIGNALS_PER_CYCLE = 2  # máximo 2 sinais por ciclo — preservar capital $180

    if not in_trading_hours():
        log.info(f"[{tf}] Fora do horário de operação (09-13h e 14-21h BRT) — pulando ciclo")
        return 0


    for sym,label,short in coins:
        if sent >= MAX_SIGNALS_PER_CYCLE:
            log.info(f"[{tf}] Limite de {MAX_SIGNALS_PER_CYCLE} sinais por ciclo atingido")
            break
        candles=await fetch_candles(session,sym,tf)
        if not candles: await asyncio.sleep(0.4); continue
        result=analyze(sym,candles)
        if not result: await asyncio.sleep(0.4); continue
        grade=result.get("signal_grade","B")

        # ATR% — excluir moedas muito voláteis para $180
        atr_pct=(result["atr"]/result["price"])*100 if result["price"] else 0
        if atr_pct > 4.0:
            log.info(f"[{tf}] {short:7s} | ATR {atr_pct:.1f}% > 4% — muito volátil, ignorando")
            await asyncio.sleep(0.2); continue

        log.info(f"[{tf}] {short:7s} | Score {result['score']:+4d} | RSI {result['rsi']:5.1f} | ADX {result['adx']:5.1f} | K:{'UP' if result['kalman_up'] else 'DN'} | Grade:{grade} | {result['sig_source'] or result['sig'] or '—'}")
        if result["sig"]:
            # Só Grade A e S — Grade B não tem R:R suficiente para $180
            if grade == "B":
                log.info(f"  ⚠️ {short} Grade B ignorado — aguardando setup A/S")
                candidates.append((abs(result["score"]),short,result["score"],result["rsi"],result["adx"],"grade-B"))
                await asyncio.sleep(0.2); continue
            key=f"{sym}_{tf}"
            if now-last_sig.get(key,0)>=cooldown:
                last_sig[key]=now; sent+=1
                await send_telegram(session,sym,label,short,result["sig"],result["price"],
                                    result["atr"],result["score"],result["rsi"],result["adx"],
                                    result["trend"],result["kalman_up"],
                                    result["swing_low"],result["swing_high"],result["sig_source"],tf,grade)
            else:
                mins=int((cooldown-(now-last_sig.get(key,0)))/60)
                log.info(f"  ⏳ {short} [{tf}] cooldown {mins}min")
                candidates.append((abs(result["score"]),short,result["score"],result["rsi"],result["adx"],"cooldown"))
        else:
            candidates.append((result["score"],short,result["score"],result["rsi"],result["adx"],result.get("sig_source","no-sig")))
        await asyncio.sleep(0.4)

    if sent == 0 and candidates:
        # Ordena por score desc → mostra os mais próximos de disparar sinal LONG
        candidates.sort(key=lambda x: x[0], reverse=True)
        top3 = candidates[:3]
        best_adx = max((adx for _,_,_,_,adx,_ in top3), default=0)
        best_score = top3[0][0] if top3 else 0
        motivo = ("📉 ADX baixo — mercado lateral" if best_adx < 22
                  else "📊 Score insuficiente" if best_score < 50
                  else "⏳ Aguardando confirmação")
        lines = [f"  {sh}: score {sc:+d} | RSI {rsi:.0f} | ADX {adx:.0f}" for _,sh,sc,rsi,adx,_ in top3]
        txt = (f"🔍 [{tf}] Sem sinais no ciclo\n{motivo}\nTop candidatos:\n" + "\n".join(lines) +
               f"\n⏰ {datetime.now().strftime('%H:%M')}")
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        try:
            async with session.post(url, json={"chat_id":TG_CHATID,"text":txt},
                                    timeout=aiohttp.ClientTimeout(total=10)) as r:
                await r.json()
        except: pass
    return sent

async def run_mtf_cycle(session, last_sig, coins):
    """Ciclo MTF: 1h confirma direção → 30m encontra entrada no pullback EMA21/50."""
    if not in_trading_hours():
        log.info("[MTF] Fora do horário de operação — pulando ciclo MTF")
        return 0
    now = time.time()
    sent = 0
    cooldown_mtf = 3600  # 1h entre sinais MTF por moeda

    # BTC trend — não operar altcoins contra tendência do BTC
    btc_bull_filter = btc_bear_filter = False
    btc_candles = await fetch_candles(session, "BTCUSDT", "1h")
    if btc_candles and len(btc_candles) >= 50:
        btc_c = [c["c"] for c in btc_candles]
        btc_e21  = ema_series(btc_c, 21)[-1]
        btc_e50  = ema_series(btc_c, 50)[-1]
        btc_e200 = ema_series(btc_c, 200)[-1]
        btc_p    = btc_c[-1]
        btc_bull_filter = btc_p > btc_e21 > btc_e50 and btc_p > btc_e200 * 0.98
        btc_bear_filter = btc_p < btc_e21 < btc_e50 and btc_p < btc_e200 * 1.02
        log.info(f"[MTF] BTC: {'BULL ↑' if btc_bull_filter else 'BEAR ↓' if btc_bear_filter else 'NEUTRO'} | ${btc_p:.0f}")

    for sym, label, short in coins:
        # 1h — direção e setup
        candles_1h = await fetch_candles(session, sym, "1h")
        if not candles_1h: await asyncio.sleep(0.5); continue

        r1h = analyze(sym, candles_1h)
        if not r1h: await asyncio.sleep(0.5); continue

        h1_bull = r1h["score"] > 20 and r1h.get("tbull_r", False) and r1h["adx"] > 18
        h1_bear = r1h["score"] < -20 and r1h.get("tbear_r", False) and r1h["adx"] > 18

        if not (h1_bull or h1_bear):
            log.info(f"[MTF] {short:7s} | 1h sem setup | Score {r1h['score']:+d}")
            await asyncio.sleep(0.5)
            continue

        # Pseudo-4H: usa últimas 4 velas de 1h para confirmar tendência de 4h
        c1h_arr = [c["c"] for c in candles_1h]
        if len(c1h_arr) >= 10:
            e21_1h_v = ema_series(c1h_arr, 21)
            e50_1h_v = ema_series(c1h_arr, 50)
            h4_bull = c1h_arr[-1] > e21_1h_v[-1] > e50_1h_v[-1] and c1h_arr[-1] > c1h_arr[-5]
            h4_bear = c1h_arr[-1] < e21_1h_v[-1] < e50_1h_v[-1] and c1h_arr[-1] < c1h_arr[-5]
        else:
            h4_bull = h4_bear = True
        if h1_bull and not h4_bull:
            log.info(f"[MTF] {short:7s} | LONG bloqueado — 4H não confirma")
            await asyncio.sleep(0.3); continue
        if h1_bear and not h4_bear:
            log.info(f"[MTF] {short:7s} | SHORT bloqueado — 4H não confirma")
            await asyncio.sleep(0.3); continue

        # BTC filter: não operar altcoin contra BTC (exceto BTC e USDT pairs de stablecoins)
        if short not in ("BTC", "WBTC"):
            if h1_bull and btc_bear_filter:
                log.info(f"[MTF] {short:7s} | LONG bloqueado — BTC em queda")
                await asyncio.sleep(0.2); continue
            if h1_bear and btc_bull_filter:
                log.info(f"[MTF] {short:7s} | SHORT bloqueado — BTC em alta")
                await asyncio.sleep(0.2); continue

        direction = "BULL" if h1_bull else "BEAR"
        log.info(f"[MTF] {short:7s} | 1h {direction} ✓4H ✓BTC | Score {r1h['score']:+d} → buscando entrada 30m...")

        # 30m — entrada no pullback
        candles_15m = await fetch_candles(session, sym, "30m")
        if not candles_15m: await asyncio.sleep(0.5); continue

        result = analyze_mtf_entry(sym, candles_15m, h1_bull, h1_bear)
        if not result:
            log.info(f"[MTF] {short:7s} | 30m sem entrada (não está no pullback)")
            await asyncio.sleep(0.5)
            continue

        mtf_grade = result.get("signal_grade", "A")
        mtf_quality = result.get("quality_score", 0)
        log.info(f"[MTF] {short:7s} | ✅ 30m {result['sig']} Grade:{mtf_grade} Q:{mtf_quality}/10 | {result['sig_source']} | RSI {result['rsi']:.1f} | ADX {result['adx']:.1f}")

        if mtf_grade == "B":
            log.info(f"[MTF] {short:7s} | Grade B ignorado — setup insuficiente")
            await asyncio.sleep(0.3); continue

        key = f"{sym}_MTF"
        if now - last_sig.get(key, 0) >= cooldown_mtf:
            last_sig[key] = now
            sent += 1
            await send_telegram(session, sym, label, short, result["sig"],
                                result["price"], result["atr"], r1h["score"],
                                result["rsi"], result["adx"], result["trend"],
                                result["kalman_up"],
                                result["swing_low"], result["swing_high"],
                                result["sig_source"], "30m", mtf_grade)
        else:
            mins = int((cooldown_mtf - (now - last_sig.get(key, 0))) / 60)
            log.info(f"  ⏳ {short} [MTF] cooldown {mins}min")

        await asyncio.sleep(0.5)

    return sent

async def run_test(session):
    """Modo de teste: analisa BTC e SOL em 15m com dados reais e manda sinal forçado."""
    log.info("🧪 TEST MODE — Analisando BTC e SOL em 15m com dados reais...")
    test_coins=[("BTCUSDT","BTC/USDT","BTC"),("SOLUSDT","SOL/USDT","SOL")]
    for sym,label,short in test_coins:
        candles=await fetch_candles(session,sym,"15m")
        if not candles:
            log.warning(f"❌ Sem dados para {short}"); continue
        result=analyze(sym,candles)
        if not result:
            log.warning(f"❌ Análise falhou para {short}"); continue
        grade=result.get("signal_grade","B")
        # Em teste força envio independente de sinal real, usando direção do score
        sig_force="LONG" if result["score"]>=0 else "SHORT"
        sig_src=result["sig_source"] or f"TEST({result['score']:+d})"
        log.info(f"🧪 {short} | Score {result['score']:+d} | Grade {grade} | Enviando sinal {sig_force}...")
        await send_telegram(session,sym,label,short,sig_force,result["price"],
                            result["atr"],result["score"],result["rsi"],result["adx"],
                            result["trend"],result["kalman_up"],
                            result["swing_low"],result["swing_high"],
                            f"TESTE — {sig_src}","15m",grade)
        await asyncio.sleep(1)
    log.info("✅ Teste concluído — verifique o Telegram!")

async def main():
    if not TG_TOKEN or not TG_CHATID:
        log.error("❌ Configure TG_TOKEN e TG_CHATID!"); return

    if TEST_MODE:
        log.info("🧪 GAUSS+DNA — MODO TESTE ATIVADO")
        async with aiohttp.ClientSession() as session:
            await run_test(session)
        return


    tf_min_base=min(tf_to_minutes(tf) for tf in TIMEFRAMES)
    scan_tf=TIMEFRAMES[0]
    mode_str="LOOP CONTÍNUO" if LOOP_MODE else "EXECUÇÃO ÚNICA"
    scan_str="DINÂMICO" if DYNAMIC_SCAN else "LISTA FIXA"
    log.info(f"🚀 GAUSS+DNA v2 | {SIGNAL_MODE} | TFs: {','.join(TIMEFRAMES)} | Coins: {scan_str} | {mode_str}")

    # Ping de inicialização — confirma que Telegram está funcionando
    async with aiohttp.ClientSession() as _s:
        try:
            def _esc(v):
                s=str(v)
                for ch in r"_*[]()~`>#+=|{}.!\-": s=s.replace(ch,f"\\{ch}")
                return s
            ping_txt=(
                f"🟢 *GAUSS\\+DNA INICIADO*\n\n"
                f"🕐 Modo: {_esc(mode_str)}\n"
                f"📊 Sinais: {_esc(SIGNAL_MODE)}\n"
                f"⏱ Timeframes: {_esc(','.join(TIMEFRAMES))}\n"
                f"🪙 Moedas: {_esc(scan_str)}\n"
                f"⏰ {_esc(datetime.now().strftime('%H:%M — %d/%m/%Y'))}"
            )
            async with _s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id":TG_CHATID,"text":ping_txt,"parse_mode":"MarkdownV2"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                d=await r.json()
                if d.get("ok"): log.info("✅ Telegram ping OK — bot ativo e conectado")
                else: log.warning(f"⚠️ Telegram ping falhou: {d.get('description')} — verifique TG_TOKEN e TG_CHATID")
        except Exception as e:
            log.error(f"Erro no ping Telegram: {e}")

    last_sig=load_state()
    cycle=0
    active_coins=list(COINS)
    last_scan_cycle=0

    async with aiohttp.ClientSession() as session:
        # ── Teste de conectividade antes de tudo ──────────────────────────────
        try:
            tg_url=f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            diag_lines=[]
            for test_url,label in [
                ("https://api.mexc.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=250","MEXC 15m x250"),
                ("https://api.mexc.com/api/v3/klines?symbol=BTCUSDT&interval=60m&limit=250","MEXC 60m x250"),
            ]:
                try:
                    async with session.get(test_url,timeout=aiohttp.ClientTimeout(total=8)) as _r:
                        _status=_r.status
                        _body=await _r.json()
                        _count=len(_body) if isinstance(_body,list) else -1
                        diag_lines.append(f"{label}: HTTP {_status} | {_count} velas")
                except Exception as _e:
                    diag_lines.append(f"{label}: ERRO {str(_e)[:60]}")
            diag_txt="🔬 Diagnóstico de conectividade:\n"+"\n".join(diag_lines)
            async with session.post(tg_url,json={"chat_id":TG_CHATID,"text":diag_txt},
                                    timeout=aiohttp.ClientTimeout(total=10)) as _r: await _r.json()
        except Exception as e:
            log.error(f"Diagnóstico falhou: {e}")

        # Scanner inicial rápido (top 20) antes do primeiro ciclo
        if DYNAMIC_SCAN:
            result=await scan_best_coins(session,scan_tf,min(20,SCANNER_TOP))
            if result: active_coins=result
            last_scan_cycle=0

        while True:
            cycle+=1

            if LOOP_MODE and cycle>1:   # ciclo 1 roda imediatamente
                wait=seconds_to_candle_close(tf_min_base)
                if wait>3:
                    log.info(f"⏳ Próxima vela [{TIMEFRAMES[0]}] em {wait:.0f}s ({wait/60:.1f}min)...")
                    await asyncio.sleep(wait+2)

            # Rescan periódico (a cada SCAN_EVERY ciclos)
            if DYNAMIC_SCAN and cycle>1 and (cycle-last_scan_cycle)>=SCAN_EVERY:
                result=await scan_best_coins(session,scan_tf,SCANNER_TOP)
                if result: active_coins=result
                last_scan_cycle=cycle

            log.info(f"── Ciclo #{cycle} | {datetime.now().strftime('%H:%M:%S %d/%m')} | {len(active_coins)} moedas ──")
            # MTF (1h→15m) + FLEX 15m — o 1h standalone é redundante e causa rate limit
            total=0
            try:
                if "1h" in TIMEFRAMES and ("30m" in TIMEFRAMES or "15m" in TIMEFRAMES):
                    sent_mtf = await run_mtf_cycle(session, last_sig, active_coins)
                    total += sent_mtf
            except Exception as e:
                log.error(f"❌ MTF erro ciclo #{cycle}: {e}")
            try:
                # FLEX standalone no timeframe base (30m) — 1h coberto pelo MTF
                base_tf = next((t for t in TIMEFRAMES if t != "1h"), TIMEFRAMES[0])
                sent=await run_cycle(session, last_sig, base_tf, active_coins)
                total+=sent
                save_state(last_sig)
                log.info(f"✅ Ciclo #{cycle} concluído. Sinais: {total}")
            except Exception as e:
                log.error(f"❌ FLEX erro ciclo #{cycle}: {e}")

            if not LOOP_MODE:
                break

if __name__=="__main__":
    asyncio.run(main())
