"""
GAUSS+DNA — Scanner de Backtest v3
Melhorias: confirmação HTF, ADX regime + rising, TPs adaptativos por volatilidade, cooldown dinâmico
"""
import requests, math, time, json, os
from datetime import datetime
from collections import deque

BASE        = "https://api.mexc.com/api/v3"
INTERVAL    = os.environ.get("INTERVAL", "30m")
TOP_N       = int(os.environ.get("TOP_N", "100"))
API_KEY     = os.environ.get("MEXC_API_KEY", "")
CANDLES     = int(os.environ.get("CANDLES", "8640"))
WARMUP      = 100
MIN_TRADES  = 3
ATR_PCT_MIN = 0.30

INTERVAL_MS = {
    "1m":60_000,"3m":180_000,"5m":300_000,"15m":900_000,
    "30m":1_800_000,"1h":3_600_000,"4h":14_400_000,"1d":86_400_000
}

# ── Indicadores — arrays O(n) ─────────────────────────────────────────────────

def ema_arr(src, p):
    k = 2/(p+1); v = src[0]; out = [v]
    for x in src[1:]: v = x*k + v*(1-k); out.append(v)
    return out

def rma_arr(src, p):
    k = 1/p; v = src[0]; out = [v]
    for x in src[1:]: v = x*k + v*(1-k); out.append(v)
    return out

def alma(src, length=50, offset=0.85, sigma=6):
    m = math.floor(offset*(length-1)); s = length/sigma
    w = [math.exp(-((i-m)**2)/(2*s*s)) for i in range(length)]
    ws = sum(w)
    out = [float('nan')]*(length-1)
    for i in range(length-1, len(src)):
        out.append(sum(w[j]*src[i-length+1+j] for j in range(length))/ws)
    return out

def calc_rsi_arr(closes, p=14):
    n = len(closes)
    gains  = [max(closes[i]-closes[i-1], 0) for i in range(1, n)]
    losses = [max(closes[i-1]-closes[i], 0) for i in range(1, n)]
    ag = rma_arr(gains, p); al = rma_arr(losses, p)
    res = [50.0]
    for i in range(len(ag)):
        rs = ag[i]/al[i] if al[i] else 100
        res.append(100 - 100/(1+rs))
    return res

def calc_atr_arr(candles, p=14):
    trs = [0.0]
    for i in range(1, len(candles)):
        h,l,pc = candles[i][2], candles[i][3], candles[i-1][4]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return rma_arr(trs, p)

def calc_adx_arr(candles, p=14):
    highs=[c[2] for c in candles]; lows=[c[3] for c in candles]; closes=[c[4] for c in candles]
    dmp=[0.0]; dmm=[0.0]; trl=[0.0]
    for i in range(1, len(candles)):
        h,l,ph,pl,pc = highs[i],lows[i],highs[i-1],lows[i-1],closes[i-1]
        up=h-ph; dn=pl-l
        dmp.append(up if up>dn and up>0 else 0)
        dmm.append(dn if dn>up and dn>0 else 0)
        trl.append(max(h-l, abs(h-pc), abs(l-pc)))
    tr_r=rma_arr(trl,p); dp_r=rma_arr(dmp,p); dm_r=rma_arr(dmm,p)
    n=len(tr_r)
    pdi=[100*dp_r[i]/tr_r[i] if tr_r[i] else 0 for i in range(n)]
    mdi=[100*dm_r[i]/tr_r[i] if tr_r[i] else 0 for i in range(n)]
    dx=[100*abs(pdi[i]-mdi[i])/(pdi[i]+mdi[i]) if (pdi[i]+mdi[i]) else 0 for i in range(n)]
    return pdi, mdi, rma_arr(dx, p)

def calc_bb_pos_arr(closes, p=20):
    n=len(closes); res=[0.5]*n
    for i in range(p-1, n):
        w=closes[i-p+1:i+1]; mid=sum(w)/p
        std=math.sqrt(sum((x-mid)**2 for x in w)/p)
        rng=2*std or 1
        res[i]=(closes[i]-(mid-std))/rng
    return res

def calc_obv_arr(candles):
    obv=[0.0]
    for i in range(1, len(candles)):
        d=candles[i][4]-candles[i-1][4]
        obv.append(obv[-1]+candles[i][5]*(1 if d>0 else -1 if d<0 else 0))
    return obv, ema_arr(obv, 21)

def calc_trendilo_arr(closes):
    n=len(closes)
    pch=[0.0]+[(closes[i]-closes[i-1])/closes[i]*100 if closes[i] else 0 for i in range(1,n)]
    avpch=alma(pch,50,0.85,6)
    trl_long=[False]*n; trl_short=[False]*n
    win=deque(); sq_sum=0.0
    for i in range(n):
        v=avpch[i]
        if math.isnan(v): continue
        win.append(v); sq_sum+=v*v
        if len(win)>50: old=win.popleft(); sq_sum-=old*old
        rms=math.sqrt(sq_sum/len(win))
        trl_long[i]=v>rms; trl_short[i]=v<-rms
    return trl_long, trl_short

def calc_vwap_arr(candles, p=20):
    n=len(candles); res=[candles[0][4]]*n
    for i in range(p-1, n):
        w=candles[i-p+1:i+1]
        tp_vol=sum(((c[2]+c[3]+c[4])/3)*c[5] for c in w)
        vol=sum(c[5] for c in w)
        res[i]=tp_vol/vol if vol else candles[i][4]
    return res

def calc_ha_bull_arr(candles):
    n=len(candles)
    ha_o=candles[0][1]; ha_c=(candles[0][1]+candles[0][2]+candles[0][3]+candles[0][4])/4
    ha_os=[ha_o]; ha_cs=[ha_c]
    for c in candles[1:]:
        po,pc=ha_o,ha_c
        ha_c=(c[1]+c[2]+c[3]+c[4])/4; ha_o=(po+pc)/2
        ha_os.append(ha_o); ha_cs.append(ha_c)
    res=[]
    for i in range(n):
        w=5; start=max(0,i-w+1)
        bulls=sum(1 for j in range(start,i+1) if ha_cs[j]>ha_os[j])
        res.append(bulls>(i-start+1)/2)
    return res

def calc_volma_arr(candles, p=20):
    vols=[c[5] for c in candles]; n=len(vols); res=[vols[0]]*n
    for i in range(p-1, n): res[i]=sum(vols[i-p+1:i+1])/p
    return res

def calc_avg_atr_pct_arr(atr_a, closes, win=20):
    """ATR% médio em janela deslizante — decide regime de volatilidade da moeda."""
    n=len(atr_a); res=[1.0]*n
    buf=deque(); s=0.0
    for i in range(n):
        v=atr_a[i]/closes[i]*100 if closes[i]>0 else 0
        buf.append(v); s+=v
        if len(buf)>win: s-=buf.popleft()
        res[i]=s/len(buf)
    return res

# ── Pré-filtro de volatilidade ────────────────────────────────────────────────

def is_volatile_enough(candles):
    recent = candles[-30:]
    atrs = calc_atr_arr(recent)
    valid = [(atrs[i], recent[i][4]) for i in range(len(recent)) if recent[i][4] > 0]
    if not valid: return False
    return sum(a/p*100 for a,p in valid)/len(valid) >= ATR_PCT_MIN

# ── Simulação vetorizada v3 ───────────────────────────────────────────────────

def run_backtest(candles):
    n=len(candles)
    closes=[c[4] for c in candles]; highs=[c[2] for c in candles]
    lows=[c[3] for c in candles]; opens=[c[1] for c in candles]

    e10=ema_arr(closes,10); e21=ema_arr(closes,21)
    e50=ema_arr(closes,50); e200=ema_arr(closes,200)
    atr_a=calc_atr_arr(candles)
    e12=ema_arr(closes,12); e26=ema_arr(closes,26)
    ml=[e12[i]-e26[i] for i in range(n)]; sl=ema_arr(ml,9)
    hist=[ml[i]-sl[i] for i in range(n)]
    rsi_a=calc_rsi_arr(closes)
    pdi_a,mdi_a,adx_a=calc_adx_arr(candles)
    bb_pos_a=calc_bb_pos_arr(closes)
    obv_a,obv_e_a=calc_obv_arr(candles)
    trl_long_a,trl_short_a=calc_trendilo_arr(closes)
    vwap_a=calc_vwap_arr(candles)
    ha_bull_a=calc_ha_bull_arr(candles)
    volma_a=calc_volma_arr(candles)
    avg_atr_pct_a=calc_avg_atr_pct_arr(atr_a, closes)

    trades=[]; in_trade=None; cooldown=0

    for i in range(WARMUP, n):
        price=closes[i]; atr=atr_a[i]
        if not atr: continue

        e10v=e10[i]; e21v=e21[i]; e50v=e50[i]; e200v=e200[i]
        mlv=ml[i]; slv=sl[i]; hv=hist[i]; hp=hist[i-1]
        rsi=rsi_a[i]; pdi=pdi_a[i]; mdi=mdi_a[i]; adx=adx_a[i]
        bb_pos=bb_pos_a[i]; obv_v=obv_a[i]; obv_e=obv_e_a[i]
        trl_long=trl_long_a[i]; trl_short=trl_short_a[i]
        vwap=vwap_a[i]; ha_bull=ha_bull_a[i]; ha_bear=not ha_bull
        vol_cur=candles[i][5]; vm=volma_a[i]

        tbull=e10v>e21v and e21v>e50v
        tbear=e10v<e21v and e21v<e50v
        macd_bull=mlv>slv and hv>hp
        macd_bear=mlv<slv and hv<hp
        obv_bull=obv_v>obv_e; obv_bear=obv_v<obv_e
        vol_ok=vol_cur>vm or obv_bull; vol_ok_s=vol_cur>vm or obv_bear
        above_vwap=price>vwap; below_vwap=price<vwap
        near_liq=abs(price-e21v)/atr<2.5 or abs(price-e50v)/atr<2.5
        near_bb_top=bb_pos>0.97; near_bb_bot=bb_pos<0.03
        ext_above=(price-e21v)/atr>3.0; ext_below=(e21v-price)/atr>3.0
        cr=highs[i]-lows[i] or 1
        exh_top=(highs[i]-max(opens[i],closes[i]))/cr>0.4
        exh_bot=(min(opens[i],closes[i])-lows[i])/cr>0.4

        # ADX deve estar subindo (tendência se fortalecendo)
        adx_rising = adx > adx_a[max(0,i-3)]

        # Confirmação HTF via EMA50: acima/abaixo de EMA200 E em movimento
        htf_bull = e50v > e200v and e50[i] > e50[max(0,i-5)]
        htf_bear = e50v < e200v and e50[i] < e50[max(0,i-5)]

        sc=(
            (15 if e21v>e50v>e200v else 0)+(10 if e10v>e21v else 0)+
            (10 if macd_bull else -10 if macd_bear else 0)+
            (5 if rsi>55 else -5 if rsi<45 else 0)+
            (10 if adx>22 and pdi>mdi else -10 if adx>22 and mdi>pdi else 0)+
            (10 if trl_long else -10 if trl_short else 0)+
            (5 if obv_bull else -5 if obv_bear else 0)+
            (5 if above_vwap else -5)+
            (5 if near_liq else -3)+
            (3 if vol_ok else -2)
        )
        fb=30 if (tbull and not (e21v>e50v>e200v)) else 0
        fbb=30 if (tbear and not (e21v<e50v<e200v)) else 0
        flex_sc=sc+fb-fbb

        # ADX mínimo 20 (era 15) + rising + confirmação HTF
        long_flex=(flex_sc>15 and (macd_bull or ha_bull) and trl_long and
                   tbull and htf_bull and above_vwap and
                   adx>=20 and adx_rising and
                   rsi<74 and not near_bb_top and not ext_above and not exh_top)
        short_flex=(flex_sc<-15 and (macd_bear or ha_bear) and trl_short and
                    tbear and htf_bear and below_vwap and
                    adx>=20 and adx_rising and
                    rsi>32 and not near_bb_bot and not ext_below and not exh_bot)

        if in_trade:
            t=in_trade; h=highs[i]; l=lows[i]
            is_long=t["sig"]=="LONG"; closed=False
            tp1_m=t.get("tp1_m",2.5); tp2_m=t.get("tp2_m",4.5); tp3_m=t.get("tp3_m",8.0)
            if is_long:
                if l<=t["stop"]:
                    t["pnl"]+=t.get("stop_r",-1.0)*t["rem"]; t["result"]="STOP"; closed=True
                elif not t.get("tp1_hit") and h>=t["tp1"]:
                    t["pnl"]+=tp1_m*0.40; t["rem"]-=0.40; t["tp1_hit"]=True
                    t["stop"]=t["entry"]; t["stop_r"]=0.0
                elif t.get("tp1_hit") and not t.get("tp2_hit") and h>=t["tp2"]:
                    t["pnl"]+=tp2_m*0.35; t["rem"]-=0.35; t["tp2_hit"]=True
                    t["stop"]=t["tp1"]; t["stop_r"]=tp1_m
                elif t.get("tp2_hit") and h>=t["tp3"]:
                    t["pnl"]+=tp3_m*t["rem"]; t["rem"]=0; t["result"]="FULL TP"; closed=True
            else:
                if h>=t["stop"]:
                    t["pnl"]+=t.get("stop_r",-1.0)*t["rem"]; t["result"]="STOP"; closed=True
                elif not t.get("tp1_hit") and l<=t["tp1"]:
                    t["pnl"]+=tp1_m*0.40; t["rem"]-=0.40; t["tp1_hit"]=True
                    t["stop"]=t["entry"]; t["stop_r"]=0.0
                elif t.get("tp1_hit") and not t.get("tp2_hit") and l<=t["tp2"]:
                    t["pnl"]+=tp2_m*0.35; t["rem"]-=0.35; t["tp2_hit"]=True
                    t["stop"]=t["tp1"]; t["stop_r"]=tp1_m
                elif t.get("tp2_hit") and l<=t["tp3"]:
                    t["pnl"]+=tp3_m*t["rem"]; t["rem"]=0; t["result"]="FULL TP"; closed=True
            if closed:
                if not t.get("result"):
                    q=t.get("tp2_hit",False); p2=t.get("tp1_hit",False)
                    t["result"]="TP2" if q else "TP1" if p2 else "STOP"
                t["exit_idx"]=i; trades.append(t); in_trade=None
                # Cooldown dinâmico: stop total=12, win forte=3, parcial=6
                if t["result"]=="STOP" and not t.get("tp1_hit"):
                    cooldown=12
                elif t.get("tp2_hit") or t["result"]=="FULL TP":
                    cooldown=3
                else:
                    cooldown=6
            continue

        if cooldown>0: cooldown-=1; continue

        sig=None
        if long_flex: sig="LONG"
        elif short_flex: sig="SHORT"
        if not sig: continue

        is_long=sig=="LONG"
        stop=(price - 1.5*atr if is_long else price + 1.5*atr)
        risk=abs(price-stop)
        if risk<=0 or risk/price>0.08: continue

        # TPs adaptativos: conservador para coins lentos, agressivo para voláteis
        ap=avg_atr_pct_a[i]
        if ap < 0.5:    tp1_m,tp2_m,tp3_m = 1.5, 3.0, 5.0   # baixa volatilidade
        elif ap > 1.5:  tp1_m,tp2_m,tp3_m = 2.5, 4.5, 8.0   # alta volatilidade
        else:           tp1_m,tp2_m,tp3_m = 2.0, 3.5, 6.0   # média volatilidade

        tp1=price+(risk*tp1_m if is_long else -risk*tp1_m)
        tp2=price+(risk*tp2_m if is_long else -risk*tp2_m)
        tp3=price+(risk*tp3_m if is_long else -risk*tp3_m)

        in_trade={"sig":sig,"entry":price,"stop":stop,"tp1":tp1,"tp2":tp2,"tp3":tp3,
                  "risk":risk,"pnl":0,"rem":1.0,"entry_idx":i,"result":None,
                  "tp1_m":tp1_m,"tp2_m":tp2_m,"tp3_m":tp3_m,
                  "date":datetime.utcfromtimestamp(candles[i][0]/1000).strftime("%d/%m")}

    if in_trade:
        t=in_trade; q=t.get("tp2_hit",False); p2=t.get("tp1_hit",False)
        t["result"]="TP2" if q else "TP1" if p2 else "OPEN"
        trades.append(t)

    return trades

def performance_grade(wr, pf, total_r):
    if wr>=62 and pf>=2.8 and total_r>=20: return "🏆 ELITE"
    if wr>=55 and pf>=2.0 and total_r>=12: return "⭐ ÓTIMO"
    if wr>=47 and pf>=1.5 and total_r>=6:  return "✅ BOM"
    if wr>=40 and pf>=1.2 and total_r>=2:  return "🔵 ACEITÁVEL"
    return "⚠️  FRACO"

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
    equity=0; peak=0; max_dd=0
    for t in closed:
        equity+=t["pnl"]
        if equity>peak: peak=equity
        dd=peak-equity
        if dd>max_dd: max_dd=dd
    return {"trades":len(closed),"wins":len(wins),"losses":len(losses),
            "win_rate":wr,"total_r":total_r,"avg_r":total_r/len(closed),
            "profit_factor":pf,"max_dd":max_dd,
            "grade":performance_grade(wr,pf,total_r)}

# ── Fetch com paginação startTime ─────────────────────────────────────────────

def fetch_klines(symbol, interval=INTERVAL, total=CANDLES):
    step=INTERVAL_MS.get(interval,1_800_000)
    start=int(time.time()*1000)-total*step
    all_c=[]; headers={"X-MEXC-APIKEY":API_KEY} if API_KEY else {}
    for _ in range(20):
        try:
            r=requests.get(f"{BASE}/klines",
                           params={"symbol":symbol,"interval":interval,
                                   "startTime":start,"limit":1000},
                           headers=headers,timeout=15)
            data=r.json()
            if not isinstance(data,list) or not data: break
            batch=[[int(c[0]),float(c[1]),float(c[2]),
                    float(c[3]),float(c[4]),float(c[5])] for c in data]
            all_c.extend(batch)
            if len(data)<1000: break
            start=batch[-1][0]+step
            time.sleep(0.2)
        except: break
    if len(all_c)<WARMUP+10: return None
    return all_c

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
        print(f"Erro ao buscar top symbols: {e}"); return []

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    step_ms=INTERVAL_MS.get(INTERVAL,1_800_000)
    dias_alvo=CANDLES*step_ms//86_400_000
    api_str="autenticado" if API_KEY else "público"
    print("🔍 GAUSS+DNA Backtest Scanner v3")
    print(f"   Timeframe: {INTERVAL} | Alvo: {CANDLES} candles (~{dias_alvo}d) | API: {api_str}")
    print(f"   Buscando top {TOP_N} moedas do MEXC...\n")

    symbols=fetch_top_symbols(TOP_N)
    if not symbols: print("❌ Erro ao buscar símbolos"); return
    print(f"✅ {len(symbols)} moedas encontradas. Iniciando backtest...\n")

    results=[]; no_data=0; few_trades=0; low_vol=0
    total=len(symbols)
    for idx,sym in enumerate(symbols):
        print(f"  [{idx+1:3d}/{total}] {sym:15s}",end="",flush=True)
        candles=fetch_klines(sym)
        if not candles:
            print("sem dados"); no_data+=1; time.sleep(0.3); continue
        if not is_volatile_enough(candles):
            print("baixa volatilidade"); low_vol+=1; time.sleep(0.2); continue
        dias_real=len(candles)*step_ms//86_400_000
        trades=run_backtest(candles)
        stats=calc_stats(trades)
        closed_ct=len([t for t in trades if t["result"]!="OPEN"])
        if not stats:
            print(f"poucos trades ({closed_ct})"); few_trades+=1; time.sleep(0.2); continue
        results.append({"symbol":sym,"stats":stats,"trades":trades,
                        "candles":len(candles),"dias":dias_real})
        s=stats
        print(f"{s['grade']}  WR:{s['win_rate']:.0f}% R:{s['total_r']:+.1f} "
              f"PF:{s['profit_factor']:.2f} {s['trades']}x DD:{s['max_dd']:.1f}R [{dias_real}d]")
        time.sleep(0.25)

    def rank_score(r):
        s=r["stats"]
        return s["profit_factor"]*s["win_rate"]*math.sqrt(s["trades"])/(s["max_dd"]+1)

    results.sort(key=rank_score,reverse=True)

    print(f"\n{'='*82}")
    print(f"📊 RANKING — GAUSS+DNA FLEX v3 | {INTERVAL} | top {TOP_N}")
    print(f"{'='*82}")
    print(f"{'#':4} {'Moeda':14} {'Grade':15} {'WR%':6} {'TotalR':8} {'PF':6} {'Trades':7} {'AvgR':6} {'DD':5} {'Dias':5}")
    print(f"{'-'*82}")
    for i,r in enumerate(results,1):
        s=r["stats"]
        print(f"{i:3}. {r['symbol']:14} {s['grade']:15} "
              f"{s['win_rate']:5.1f}% {s['total_r']:+7.1f}R "
              f"{s['profit_factor']:5.2f} {s['trades']:5}x "
              f"{s['avg_r']:+5.2f}R {s['max_dd']:4.1f}R {r['dias']:4}d")

    from collections import Counter
    grades=Counter(r["stats"]["grade"] for r in results)
    print(f"\n{'='*82}")
    print("📈 SUMÁRIO:")
    for g in ["🏆 ELITE","⭐ ÓTIMO","✅ BOM","🔵 ACEITÁVEL","⚠️  FRACO"]:
        cnt=grades.get(g,0)
        if cnt: print(f"   {g}: {cnt} moedas")
    print(f"   Sem dados: {no_data} | Baixa volatilidade: {low_vol} | Poucos trades: {few_trades}")

    def safe_score(r):
        try: return rank_score(r)
        except: return 0

    output={"timestamp":datetime.utcnow().isoformat(),"interval":INTERVAL,
            "candles_alvo":CANDLES,"dias_alvo":dias_alvo,"results":[
                {"symbol":r["symbol"],"stats":r["stats"],
                 "candles_fetched":r["candles"],"dias":r["dias"],
                 "rank_score":round(safe_score(r),2),
                 "last_trades":[{"date":t["date"],"sig":t["sig"],
                                 "pnl":round(t["pnl"],2),"result":t["result"]}
                                for t in r["trades"][-5:]]}
                for r in results]}
    with open("backtest_results.json","w") as f:
        json.dump(output,f,indent=2)
    print(f"\n✅ Resultados salvos em backtest_results.json")
    print(f"   Total com resultado: {len(results)} moedas\n")

if __name__=="__main__":
    main()
