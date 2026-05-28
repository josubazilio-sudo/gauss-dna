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
SCANNER_TOP  = int(os.environ.get("SCANNER_TOP", "20"))   # moedas selecionadas
SCAN_EVERY   = int(os.environ.get("SCAN_EVERY", "16"))    # rescan a cada N ciclos (~4h em 15m)
STATE_FILE   = Path("last_signals.json")

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
    # Mega caps — máxima liquidez e tendências confiáveis
    ("BTCUSDT","BTC/USDT","BTC"),("ETHUSDT","ETH/USDT","ETH"),
    ("BNBUSDT","BNB/USDT","BNB"),("XRPUSDT","XRP/USDT","XRP"),
    # L1 com boa volatilidade e volume
    ("SOLUSDT","SOL/USDT","SOL"),("AVAXUSDT","AVAX/USDT","AVAX"),
    ("SUIUSDT","SUI/USDT","SUI"),("APTUSDT","APT/USDT","APT"),
    ("NEARUSDT","NEAR/USDT","NEAR"),("TONUSDT","TON/USDT","TON"),
    # DeFi / infra — trending behavior consistente
    ("LINKUSDT","LINK/USDT","LINK"),("INJUSDT","INJ/USDT","INJ"),
    ("JUPUSDT","JUP/USDT","JUP"),("ARBUSDT","ARB/USDT","ARB"),
    ("OPUSDT","OP/USDT","OP"),("UNIUSDT","UNI/USDT","UNI"),
    # Meme coins com alta liquidez
    ("DOGEUSDT","DOGE/USDT","DOGE"),("PEPEUSDT","PEPE/USDT","PEPE"),
    ("WIFUSDT","WIF/USDT","WIF"),("SHIBUSDT","SHIB/USDT","SHIB"),
    # High beta com volume consistente
    ("ADAUSDT","ADA/USDT","ADA"),("DOTUSDT","DOT/USDT","DOT"),
    ("ATOMUSDT","ATOM/USDT","ATOM"),("LTCUSDT","LTC/USDT","LTC"),
    # IA / narrativa em alta
    ("FETUSDT","FET/USDT","FET"),
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

    not_ext_long=(price-e50)/atr<2.5
    not_ext_short=(e50-price)/atr<2.5

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
        (10 if ha_bull else -10 if ha_bear else 0)+
        (5 if kalman_accel_up else -5 if kalman_accel_down else 0)+
        (5 if trend_consistent_bull else -5 if trend_consistent_bear else 0)
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

    # Sinal de cruzamento
    long_cross=(any_cross_bull and score>10 and adx>15 and
                (macd_bull or ha_bull) and (f_bull or obv_bull) and
                v_strong and not_ext_long and price>e200*0.97 and safe_long)
    short_cross=(any_cross_bear and score<-10 and adx>15 and
                 (macd_bear or ha_bear) and (f_bear or obv_bear) and
                 v_strong and not_ext_short and price<e200*1.03 and safe_short)

    # ── SINAL PULLBACK ── entrada após recuo nas EMAs (melhor preço)
    long_pullback=(pullback_bull and trend_bull and (macd_bull or macd_recovering) and
                   adx>18 and (f_bull or obv_bull) and v_strong and
                   above_vwap and score>25 and not any_cross_bull)
    short_pullback=(pullback_bear and trend_bear and (macd_bear or macd_exhausting) and
                    adx>18 and (f_bear or obv_bear) and v_strong and
                    below_vwap and score<-25 and not any_cross_bear)

    # ── SINAIS FLEX ── (critérios essenciais; safe_long/safe_short apenas no ELITE)
    long_flex=(score>20 and (trend_bull or kalman_up) and (macd_bull or ha_bull) and
               adx>12 and (f_bull or obv_bull) and not_ext_long)
    short_flex=(score<-20 and (trend_bear or kalman_down) and (macd_bear or ha_bear) and
                adx>12 and (f_bear or obv_bear) and not_ext_short)

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

    return {"price":price,"score":score,"atr":atr,"rsi":rsi,"adx":adx,
            "kalman_up":kalman_up,"trend":"BULL" if trend_bull else "BEAR" if trend_bear else "NEUTRO",
            "sig":sig,"sig_source":sig_source,"swing_low":swing_low,"swing_high":swing_high,
            "ha_bull":ha_bull,"obv_bull":obv_bull,"above_vwap":above_vwap,
            "signal_grade":signal_grade,"quality_score":quality_score}

# ── TELEGRAM ─────────────────────────────────────────────────────────────────

async def send_telegram(session, sym, label, short, sig_type, price, atr, score,
                        rsi, adx, trend, kalman_up, swing_low, swing_high,
                        sig_source, tf, signal_grade):
    is_long=sig_type=="LONG"

    # Stop baseado em swing high/low com floor de ATR
    if is_long:
        stop=max(swing_low-atr*0.1, price-atr*1.5)
    else:
        stop=min(swing_high+atr*0.1, price+atr*1.5)
    risk=abs(price-stop)

    # TP dinâmico por grade: S-tier deixa o winner correr mais
    if signal_grade=="S":
        r1,r2,r_final=2.0,3.0,6.0   # máximo potencial
    elif signal_grade=="A":
        r1,r2,r_final=1.8,2.5,4.5
    else:
        r1,r2,r_final=1.5,2.0,3.5

    tp1  =price+risk*r1     if is_long else price-risk*r1
    tp2  =price+risk*r2     if is_long else price-risk*r2
    final=price+risk*r_final if is_long else price-risk*r_final

    # Risk sugerido por grade
    grade_info={
        "S": ("🏆 GRADE S — Setup perfeito","5\\-10% do capital"),
        "A": ("⭐ GRADE A — Setup sólido",  "3\\-5% do capital"),
        "B": ("📊 GRADE B — Setup básico",  "1\\-3% do capital"),
    }
    grade_label,risk_sug=grade_info[signal_grade]

    if sig_source=="PULLBACK":
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
        s=str(v)
        for ch in r"_*[]()~`>#+=|{}.!\-": s=s.replace(ch,f"\\{ch}")
        return s

    now=datetime.now().strftime("%H:%M — %d/%m/%Y")
    k_str="↑" if kalman_up else "↓"
    cross_line=f"📉 Cross: {esc(cross_info)}\n" if cross_info else ""

    text=(
        f"🚨 *{esc(mode_tag)} — {sig_type}*\n\n"
        f"{'🟢' if is_long else '🔴'} *{esc(label)}* \\| ⏱ {esc(tf)}\n"
        f"{cross_line}"
        f"{esc(grade_label)}\n"
        f"💵 Risco sugerido: *{risk_sug}*\n\n"
        f"💰 Entrada: `${esc(fmt_price(price))}`\n"
        f"🛑 Stop: `${esc(d(stop))}`\n"
        f"🎯 TP1 \\({esc(str(r1))}R\\): `${esc(d(tp1))}`\n"
        f"✨ TP2 \\({esc(str(r2))}R\\): `${esc(d(tp2))}`\n"
        f"🏆 Final \\({esc(str(r_final))}R\\): `${esc(d(final))}`\n\n"
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

# ── RASTREADOR DINÂMICO DE MOEDAS ─────────────────────────────────────────────

# Stablecoins e tokens alavancados para excluir
_EXCLUDE = {"USDC","BUSD","TUSD","FDUSD","DAI","USDP","PAXG","WBTC","WETH",
            "EUR","GBP","BRL","UST","USDD","FRAX"}
_EXCLUDE_SUB = ("UP","DOWN","BULL","BEAR","3L","3S","2L","2S","5L","5S")

async def fetch_top_usdt_pairs(session, min_vol_m=3.0, max_pairs=100):
    """Busca todos os pares USDT da Binance ordenados por volume 24h (USD)."""
    url="https://api.binance.com/api/v3/ticker/24hr"
    try:
        async with session.get(url,timeout=aiohttp.ClientTimeout(total=15)) as r:
            data=await r.json()
        pairs=[]
        for t in data:
            sym=t["symbol"]
            if not sym.endswith("USDT"): continue
            base=sym[:-4]
            if base in _EXCLUDE: continue
            if any(sub in base for sub in _EXCLUDE_SUB): continue
            try:
                vol=float(t["quoteVolume"])
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
    if atr_pct<0.25 or atr_pct>6.0: return 0   # muito quieto ou muito louco
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

async def run_cycle(session, last_sig, tf, coins):
    """Executa um ciclo completo de análise em todas as moedas para um timeframe."""
    now=time.time(); sent=0
    cooldown=tf_to_minutes(tf)*60  # cooldown = duração de 1 vela neste TF
    for sym,label,short in coins:
        candles=await fetch_candles(session,sym,tf)
        if not candles: await asyncio.sleep(0.4); continue
        result=analyze(sym,candles)
        if not result: await asyncio.sleep(0.4); continue
        grade=result.get("signal_grade","B")
        log.info(f"[{tf}] {short:7s} | Score {result['score']:+4d} | RSI {result['rsi']:5.1f} | ADX {result['adx']:5.1f} | K:{'UP' if result['kalman_up'] else 'DN'} | Grade:{grade} | {result['sig_source'] or result['sig'] or '—'}")
        if result["sig"]:
            key=f"{sym}_{tf}"  # chave única por moeda + timeframe
            if now-last_sig.get(key,0)>=cooldown:
                last_sig[key]=now; sent+=1
                await send_telegram(session,sym,label,short,result["sig"],result["price"],
                                    result["atr"],result["score"],result["rsi"],result["adx"],
                                    result["trend"],result["kalman_up"],
                                    result["swing_low"],result["swing_high"],result["sig_source"],tf,grade)
            else:
                mins=int((cooldown-(now-last_sig.get(key,0)))/60)
                log.info(f"  ⏳ {short} [{tf}] cooldown {mins}min")
        await asyncio.sleep(0.4)
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
    scan_tf=TIMEFRAMES[0]  # usa o menor TF para o scanner
    mode_str="LOOP CONTÍNUO" if LOOP_MODE else "EXECUÇÃO ÚNICA"
    scan_str="DINÂMICO" if DYNAMIC_SCAN else "LISTA FIXA"
    log.info(f"🚀 GAUSS+DNA v2 | {SIGNAL_MODE} | TFs: {','.join(TIMEFRAMES)} | Coins: {scan_str} | {mode_str}")

    last_sig=load_state()
    cycle=0
    active_coins=list(COINS)   # começa com lista padrão
    last_scan_cycle=0

    async with aiohttp.ClientSession() as session:
        # Scanner inicial antes do primeiro ciclo
        if DYNAMIC_SCAN:
            result=await scan_best_coins(session,scan_tf,SCANNER_TOP)
            if result: active_coins=result
            last_scan_cycle=0

        while True:
            cycle+=1

            if LOOP_MODE:
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
            try:
                total=0
                for tf in TIMEFRAMES:
                    sent=await run_cycle(session,last_sig,tf,active_coins)
                    total+=sent
                save_state(last_sig)
                log.info(f"✅ Ciclo #{cycle} concluído. Sinais: {total} | TFs: {','.join(TIMEFRAMES)}")
            except Exception as e:
                log.error(f"❌ Erro no ciclo #{cycle}: {e}")

            if not LOOP_MODE:
                break

if __name__=="__main__":
    asyncio.run(main())
