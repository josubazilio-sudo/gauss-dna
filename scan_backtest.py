"""
GAUSS+DNA — Scanner de Backtest
Varre as top 100 moedas do MEXC, simula a estratégia FLEX em dados históricos
e ranqueia por performance (Profit Factor, Win Rate, Total R).
"""
import requests, math, time, json
from datetime import datetime

import os
BASE = "https://api.mexc.com/api/v3"
INTERVAL   = os.environ.get("INTERVAL", "30m")
TOP_N      = int(os.environ.get("TOP_N", "100"))
CANDLES    = 1000   # ~20 dias em 30m
WARMUP     = 200    # candles descartados para aquecimento dos indicadores
MIN_TRADES = 3      # mínimo de trades para considerar resultado válido

# ── Indicadores ──────────────────────────────────────────────────────────────

def ema(src, p):
    k = 2/(p+1); v = src[0]
    out = [v]
    for x in src[1:]:
        v = x*k + v*(1-k); out.append(v)
    return out

def rma(src, p):
    k = 1/p; v = src[0]
    out = [v]
    for x in src[1:]:
        v = x*k + v*(1-k); out.append(v)
    return out

def alma(src, length=50, offset=0.85, sigma=6):
    m = math.floor(offset*(length-1)); s = length/sigma
    w = [math.exp(-((i-m)**2)/(2*s*s)) for i in range(length)]
    ws = sum(w)
    out = [float('nan')]*(length-1)
    for i in range(length-1, len(src)):
        val = sum(w[j]*src[i-length+1+j] for j in range(length))
        out.append(val/ws)
    return out

def calc_rsi(closes, p=14):
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i]-closes[i-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    if not gains: return 50
    ag = rma(gains, p); al = rma(losses, p)
    rs = ag[-1]/al[-1] if al[-1] else 100
    return 100-100/(1+rs)

def calc_adx(candles, p=14):
    highs=[c[2] for c in candles]; lows=[c[3] for c in candles]; closes=[c[4] for c in candles]
    dm_plus, dm_minus, tr_list = [], [], []
    for i in range(1, len(candles)):
        h,l,ph,pl,pc = highs[i],lows[i],highs[i-1],lows[i-1],closes[i-1]
        up=h-ph; dn=pl-l
        dm_plus.append(up if up>dn and up>0 else 0)
        dm_minus.append(dn if dn>up and dn>0 else 0)
        tr_list.append(max(h-l, abs(h-pc), abs(l-pc)))
    if len(tr_list)<p: return 0,0,15,15
    tr_r=rma(tr_list,p); dp=rma(dm_plus,p); dm=rma(dm_minus,p)
    pdi=[100*dp[i]/tr_r[i] if tr_r[i] else 0 for i in range(len(tr_r))]
    mdi=[100*dm[i]/tr_r[i] if tr_r[i] else 0 for i in range(len(tr_r))]
    dx=[]
    for i in range(len(pdi)):
        s=pdi[i]+mdi[i]
        dx.append(100*abs(pdi[i]-mdi[i])/s if s else 0)
    adx_arr=rma(dx,p)
    return pdi[-1],mdi[-1],adx_arr[-1],adx_arr[-2] if len(adx_arr)>1 else adx_arr[-1]

def calc_macd(closes):
    e12=ema(closes,12); e26=ema(closes,26)
    ml=[e12[i]-e26[i] for i in range(len(closes))]
    sl=ema(ml,9)
    hist=[ml[i]-sl[i] for i in range(len(ml))]
    return ml[-1],sl[-1],hist[-1],hist[-2] if len(hist)>1 else 0

def calc_bb(closes, p=20, mult=2):
    if len(closes)<p: return closes[-1],closes[-1],closes[-1],0,0.5
    window=closes[-p:]
    mid=sum(window)/p
    std=math.sqrt(sum((x-mid)**2 for x in window)/p)
    upper=mid+mult*std; lower=mid-mult*std
    rng=upper-lower or 1
    pos=(closes[-1]-lower)/rng
    squeeze=rng<(sum(closes[-p*2:-p])/p)*0.01 if len(closes)>=p*2 else False
    return upper,mid,lower,rng,pos

def calc_atr(candles, p=14):
    trs=[]
    for i in range(1,len(candles)):
        h,l,pc=candles[i][2],candles[i][3],candles[i-1][4]
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    if not trs: return 0
    return rma(trs,p)[-1]

def calc_obv(candles):
    obv=[0]
    for i in range(1,len(candles)):
        d=candles[i][4]-candles[i-1][4]
        obv.append(obv[-1]+candles[i][5]*(1 if d>0 else -1 if d<0 else 0))
    obv_e=ema(obv,21)
    return obv[-1],obv_e[-1]

def calc_trendilo(closes):
    pch=[0]+[(closes[i]-closes[i-1])/closes[i]*100 if closes[i] else 0 for i in range(1,len(closes))]
    avpch=alma(pch,50,0.85,6)
    rms_vals=[]
    for i in range(len(avpch)):
        sl=[v for v in avpch[max(0,i-49):i+1] if not math.isnan(v)]
        rms_vals.append(math.sqrt(sum(v*v for v in sl)/len(sl)) if sl else 0)
    last=avpch[-1]
    if math.isnan(last): return False,False
    return last>rms_vals[-1], last<-rms_vals[-1]

def calc_vwap(candles, p=20):
    window=candles[-p:]
    tp_vol=sum(((c[2]+c[3]+c[4])/3)*c[5] for c in window)
    vol=sum(c[5] for c in window)
    return tp_vol/vol if vol else candles[-1][4]

def calc_ha(candles):
    ha_o=candles[0][1]; ha_c=(candles[0][1]+candles[0][2]+candles[0][3]+candles[0][4])/4
    for c in candles[1:]:
        prev_o,prev_c=ha_o,ha_c
        ha_c=(c[1]+c[2]+c[3]+c[4])/4
        ha_o=(prev_o+prev_c)/2
    return ha_c>ha_o

def vol_ma(candles, p=20):
    vols=[c[5] for c in candles[-p:]]
    return sum(vols)/len(vols) if vols else 0

# ── Simulação de estratégia ───────────────────────────────────────────────────

def run_backtest(candles):
    trades=[]
    in_trade=None
    cooldown=0

    for i in range(WARMUP, len(candles)):
        c=candles[:i+1]
        closes=[x[4] for x in c]
        price=closes[-1]

        # Indicadores
        e10=ema(closes,10)[-1]; e21=ema(closes,21)[-1]
        e50=ema(closes,50)[-1]; e200=ema(closes,200)[-1] if len(closes)>=200 else ema(closes,min(len(closes),200))[-1]
        atr=calc_atr(c)
        if not atr: continue

        ml,sl_v,hist,hist_p=calc_macd(closes)
        rsi=calc_rsi(closes)
        pdi,mdi,adx,adx_p=calc_adx(c)
        _,_,_,bb_range,bb_pos=calc_bb(closes)
        obv_v,obv_e=calc_obv(c)
        trl_long,trl_short=calc_trendilo(closes)
        vwap=calc_vwap(c)
        ha_bull=calc_ha(c[-5:])
        ha_bear=not ha_bull
        vm=vol_ma(c)
        vol_cur=c[-1][5]

        # Condições
        tbull_loose=e10>e21 and e21>e50
        tbear_loose=e10<e21 and e21<e50
        macd_bull=ml>sl_v and hist>hist_p
        macd_bear=ml<sl_v and hist<hist_p
        obv_bull=obv_v>obv_e; obv_bear=obv_v<obv_e
        vol_ok=vol_cur>vm or obv_bull
        vol_ok_s=vol_cur>vm or obv_bear
        above_vwap=price>vwap; below_vwap=price<vwap
        near_liq=abs(price-e21)/atr<2.5 or abs(price-e50)/atr<2.5
        near_bb_top=bb_pos>0.97; near_bb_bot=bb_pos<0.03
        ext_above=(price-e21)/atr>3.0; ext_below=(e21-price)/atr>3.0
        highs=[x[2] for x in c]; lows=[x[3] for x in c]; opens=[x[1] for x in c]
        candle_range=highs[-1]-lows[-1] or 1
        uwick=(highs[-1]-max(opens[-1],closes[-1]))/candle_range
        lwick=(min(opens[-1],closes[-1])-lows[-1])/candle_range
        exh_top=uwick>0.4; exh_bot=lwick>0.4

        # Score simplificado
        score=(
            (15 if e21>e50>e200 else 0)+(10 if e10>e21 else 0)+
            (10 if macd_bull else -10 if macd_bear else 0)+
            (5 if rsi>55 else -5 if rsi<45 else 0)+
            (10 if adx>22 and pdi>mdi else -10 if adx>22 and mdi>pdi else 0)+
            (10 if trl_long else -10 if trl_short else 0)+
            (5 if obv_bull else -5 if obv_bear else 0)+
            (5 if above_vwap else -5)
        )
        flex_bonus=30 if (tbull_loose and not (e21>e50>e200)) else 0
        flex_bonus_b=30 if (tbear_loose and not (e21<e50<e200)) else 0
        flex_score=score+flex_bonus-flex_bonus_b

        long_flex=(flex_score>30 and (macd_bull or ha_bull) and trl_long and
                   tbull_loose and above_vwap and vol_ok and near_liq and
                   adx>=15 and rsi<74 and not near_bb_top and not ext_above and not exh_top)
        short_flex=(flex_score<-30 and (macd_bear or ha_bear) and trl_short and
                    tbear_loose and below_vwap and vol_ok_s and near_liq and
                    adx>=15 and rsi>32 and not near_bb_bot and not ext_below and not exh_bot)

        # Gestão de trade aberto
        if in_trade:
            t=in_trade; idx=i
            h=highs[-1]; l=lows[-1]
            is_long=t["sig"]=="LONG"
            closed=False

            if is_long:
                if l<=t["stop"]:
                    rem=t["rem"]; t["pnl"]+=-1.0*rem; t["result"]="STOP"; closed=True
                elif not t.get("tp1_hit") and h>=t["tp1"]:
                    t["pnl"]+=2.5*0.40; t["rem"]-=0.40; t["tp1_hit"]=True
                elif not t.get("tp2_hit") and t.get("tp1_hit") and h>=t["tp2"]:
                    t["pnl"]+=4.5*0.35; t["rem"]-=0.35; t["tp2_hit"]=True
                elif t.get("tp2_hit") and h>=t["tp3"]:
                    t["pnl"]+=8.0*t["rem"]; t["rem"]=0; t["result"]="FULL TP"; closed=True
            else:
                if h>=t["stop"]:
                    rem=t["rem"]; t["pnl"]+=-1.0*rem; t["result"]="STOP"; closed=True
                elif not t.get("tp1_hit") and l<=t["tp1"]:
                    t["pnl"]+=2.5*0.40; t["rem"]-=0.40; t["tp1_hit"]=True
                elif not t.get("tp2_hit") and t.get("tp1_hit") and l<=t["tp2"]:
                    t["pnl"]+=4.5*0.35; t["rem"]-=0.35; t["tp2_hit"]=True
                elif t.get("tp2_hit") and l<=t["tp3"]:
                    t["pnl"]+=8.0*t["rem"]; t["rem"]=0; t["result"]="FULL TP"; closed=True

            if closed:
                if not t.get("result"):
                    p=t.get("tp1_hit",False); q=t.get("tp2_hit",False)
                    t["result"]="TP2" if q else "TP1" if p else "STOP"
                t["exit_idx"]=i; trades.append(t); in_trade=None; cooldown=8
            continue

        if cooldown>0: cooldown-=1; continue
        if in_trade: continue

        sig=None
        if long_flex: sig="LONG"
        elif short_flex: sig="SHORT"
        if not sig: continue

        # Stop e alvos
        is_long=sig=="LONG"
        if is_long:
            stop=min(lows[max(0,i-16):i])-0.5*atr
        else:
            stop=max(highs[max(0,i-16):i])+0.5*atr
        risk=abs(price-stop)
        if risk<=0 or risk/price>0.06: continue  # stop muito largo (>6%)
        tp1=price+(risk*2.5 if is_long else -risk*2.5)
        tp2=price+(risk*4.5 if is_long else -risk*4.5)
        tp3=price+(risk*8.0 if is_long else -risk*8.0)

        in_trade={
            "sig":sig,"entry":price,"stop":stop,
            "tp1":tp1,"tp2":tp2,"tp3":tp3,
            "risk":risk,"pnl":0,"rem":1.0,
            "entry_idx":i,"result":None,
            "date":datetime.utcfromtimestamp(c[-1][0]/1000).strftime("%d/%m")
        }

    # Fechar trade aberto no fim dos dados
    if in_trade:
        t=in_trade; p=t.get("tp1_hit",False); q=t.get("tp2_hit",False)
        t["result"]="TP2" if q else "TP1" if p else "OPEN"
        trades.append(t)

    return trades

def calc_stats(trades):
    if not trades: return None
    closed=[t for t in trades if t["result"]!="OPEN"]
    if len(closed)<MIN_TRADES: return None
    wins=[t for t in closed if t["pnl"]>0]
    losses=[t for t in closed if t["pnl"]<=0]
    total_r=sum(t["pnl"] for t in closed)
    win_r=sum(t["pnl"] for t in wins)
    loss_r=abs(sum(t["pnl"] for t in losses))
    pf=win_r/loss_r if loss_r else 999
    wr=len(wins)/len(closed)*100 if closed else 0

    # Max drawdown em R
    equity=0; peak=0; max_dd=0
    for t in closed:
        equity+=t["pnl"]
        if equity>peak: peak=equity
        dd=peak-equity
        if dd>max_dd: max_dd=dd

    return {
        "trades":len(closed),"wins":len(wins),"losses":len(losses),
        "win_rate":wr,"total_r":total_r,"avg_r":total_r/len(closed),
        "profit_factor":pf,"max_dd":max_dd
    }

# ── Fetch de dados ─────────────────────────────────────────────────────────

def fetch_klines(symbol, interval=INTERVAL, limit=CANDLES):
    try:
        r=requests.get(f"{BASE}/klines",
                       params={"symbol":symbol,"interval":interval,"limit":limit},
                       timeout=10)
        data=r.json()
        if not isinstance(data,list) or len(data)<WARMUP+10: return None
        # [time, open, high, low, close, volume, ...]
        return [[int(c[0]),float(c[1]),float(c[2]),float(c[3]),float(c[4]),float(c[5])] for c in data]
    except: return None

def fetch_top_symbols(n=100):
    try:
        r=requests.get(f"{BASE}/ticker/24hr",timeout=15)
        data=r.json()
        pairs=[d for d in data
               if d["symbol"].endswith("USDT")
               and not any(s in d["symbol"] for s in ["USD1","USDE","USDT0","TUSD","BUSD","FDUSD","USDC"])
               and float(d.get("quoteVolume","0"))>0]
        pairs.sort(key=lambda x:float(x.get("quoteVolume","0")),reverse=True)
        return [d["symbol"] for d in pairs[:n]]
    except Exception as e:
        print(f"Erro ao buscar top symbols: {e}")
        return []

# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("🔍 GAUSS+DNA Backtest Scanner")
    print(f"   Timeframe: {INTERVAL} | Candles: {CANDLES} (~{CANDLES*30//60//24} dias)")
    print("   Buscando top 100 moedas do MEXC...\n")

    symbols=fetch_top_symbols(TOP_N)
    if not symbols:
        print("❌ Erro ao buscar símbolos"); return

    print(f"✅ {len(symbols)} moedas encontradas. Iniciando backtest...\n")

    results=[]
    total=len(symbols)
    for idx,sym in enumerate(symbols):
        print(f"  [{idx+1:3d}/{total}] {sym:15s}", end="", flush=True)
        candles=fetch_klines(sym)
        if not candles:
            print("sem dados"); time.sleep(0.3); continue

        trades=run_backtest(candles)
        stats=calc_stats(trades)
        if not stats:
            print(f"poucos trades ({len(trades)})"); time.sleep(0.2); continue

        results.append({"symbol":sym,"stats":stats,"trades":trades})
        s=stats
        print(f"WR:{s['win_rate']:.0f}% | R:{s['total_r']:+.1f} | PF:{s['profit_factor']:.2f} | "
              f"Trades:{s['trades']} | DD:{s['max_dd']:.1f}R")
        time.sleep(0.25)

    # Ranking: score = PF * WR * sqrt(trades) / (max_dd+1)
    def score(r):
        s=r["stats"]
        return s["profit_factor"]*s["win_rate"]*math.sqrt(s["trades"])/(s["max_dd"]+1)

    results.sort(key=score, reverse=True)

    print("\n" + "="*70)
    print("🏆 TOP 20 — MELHOR PERFORMANCE PARA ESTRATÉGIA GAUSS+DNA")
    print("="*70)
    print(f"{'#':3} {'Moeda':12} {'WR%':6} {'Total R':8} {'PF':6} {'Trades':7} {'Avg R':7} {'Max DD':7}")
    print("-"*70)
    for i,r in enumerate(results[:20],1):
        s=r["stats"]
        print(f"{i:3}. {r['symbol']:12} {s['win_rate']:5.1f}% {s['total_r']:+7.1f}R "
              f"{s['profit_factor']:6.2f} {s['trades']:6}x {s['avg_r']:+6.2f}R {s['max_dd']:6.1f}R")

    # Salvar JSON completo
    output={"timestamp":datetime.utcnow().isoformat(),"interval":INTERVAL,
            "candles":CANDLES,"results":[
                {"symbol":r["symbol"],"stats":r["stats"],
                 "score":score(r),
                 "last_trades":[{"date":t["date"],"sig":t["sig"],"pnl":round(t["pnl"],2),"result":t["result"]}
                                for t in r["trades"][-5:]]}
                for r in results]}
    with open("backtest_results.json","w") as f:
        json.dump(output,f,indent=2)
    print(f"\n✅ Resultados completos salvos em backtest_results.json")

if __name__=="__main__":
    main()
