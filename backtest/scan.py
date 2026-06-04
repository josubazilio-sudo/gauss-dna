"""
GAUSS+DNA Multi-Symbol Scanner
Roda backtest nas top N moedas e salva um ranking em results/summary.json
Uso: python backtest/scan.py --top 20 --months 3 --interval 1h
"""
import sys, asyncio, aiohttp, json, argparse, time as _time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from backtest.engine import (
    fetch_candles, get_top_usdt_pairs,
    backtest_symbol, ema_series, ha_series
)

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

FIXED_SYMBOLS = ["SOLUSDT", "BTCUSDT", "ETHUSDT", "BNBUSDT", "AVAXUSDT",
                 "DOTUSDT", "ADAUSDT", "MATICUSDT", "LINKUSDT", "LTCUSDT"]

async def run_one(session, symbol, interval, months):
    candles = await fetch_candles(session, symbol, interval, months)
    if len(candles) < 220:
        print(f"  {symbol}: dados insuficientes ({len(candles)} velas)")
        return None

    trades = backtest_symbol(symbol, candles)
    if not trades:
        print(f"  {symbol}: nenhum trade encontrado")
        return None

    total   = len(trades)
    wins    = sum(1 for t in trades if t["r_result"] > 0)
    total_r = sum(t["r_result"] for t in trades)

    by_grade  = {}
    by_source = {}
    for t in trades:
        g = t["grade"]
        by_grade.setdefault(g, {"total": 0, "wins": 0, "r": 0.0})
        by_grade[g]["total"] += 1
        if t["r_result"] > 0: by_grade[g]["wins"] += 1
        by_grade[g]["r"] = round(by_grade[g]["r"] + t["r_result"], 2)

        src = t["source"].split(":")[0]
        by_source.setdefault(src, {"total": 0, "wins": 0, "r": 0.0})
        by_source[src]["total"] += 1
        if t["r_result"] > 0: by_source[src]["wins"] += 1
        by_source[src]["r"] = round(by_source[src]["r"] + t["r_result"], 2)

    best  = max(trades, key=lambda x: x["r_result"])
    worst = min(trades, key=lambda x: x["r_result"])

    return {
        "symbol":   symbol,
        "candles":  len(candles),
        "total":    total,
        "wins":     wins,
        "losses":   total - wins,
        "win_rate": round(wins / total * 100, 1),
        "avg_r":    round(total_r / total, 2),
        "total_r":  round(total_r, 1),
        "by_grade":  by_grade,
        "by_source": by_source,
        "best_trade":  {"datetime": best["datetime"],  "sig": best["sig"],  "grade": best["grade"],  "r": best["r_result"],  "source": best["source"]},
        "worst_trade": {"datetime": worst["datetime"], "sig": worst["sig"], "grade": worst["grade"], "r": worst["r_result"], "source": worst["source"]},
    }

async def scan(top_n, interval, months, symbols=None):
    t0 = _time.time()
    async with aiohttp.ClientSession() as session:
        if symbols:
            syms = [s.upper() for s in symbols]
        else:
            print(f"Buscando top {top_n} pares USDT...")
            top = await get_top_usdt_pairs(session, top_n)
            syms = list(dict.fromkeys(FIXED_SYMBOLS + top))[:top_n]

        print(f"Rodando backtest em {len(syms)} moedas ({interval}, {months} meses)...\n")
        results = []
        for i, sym in enumerate(syms, 1):
            print(f"[{i:2d}/{len(syms)}] {sym}", flush=True)
            r = await run_one(session, sym, interval, months)
            if r:
                results.append(r)
                print(f"       → {r['total']} trades | WR {r['win_rate']}% | R Total {r['total_r']:+.1f}R")

    results.sort(key=lambda x: x["total_r"], reverse=True)
    elapsed = _time.time() - t0

    summary = {
        "generated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "interval":  interval,
        "months":    months,
        "coins":     results,
    }

    out = RESULTS_DIR / "summary.json"
    with open(out, "w") as f:
        json.dump(summary, f, separators=(",", ":"))

    print(f"\n{'='*55}")
    print(f"  RANKING — Top moedas por R Total ({interval}, {months}m)")
    print(f"{'='*55}")
    print(f"  {'Símbolo':12s} {'Trades':>6} {'WR':>6} {'R Total':>8} {'Grade S R':>10}")
    print(f"  {'-'*50}")
    for r in results[:20]:
        gs = r["by_grade"].get("S", {})
        gs_r = f"{gs.get('r',0):+.1f}R" if gs else "—"
        marker = " ★" if r["total_r"] >= 10 else ""
        print(f"  {r['symbol']:12s} {r['total']:6d} {r['win_rate']:5.1f}% {r['total_r']:+7.1f}R {gs_r:>10}{marker}")

    wins_total  = sum(r["wins"]   for r in results)
    trades_total = sum(r["total"] for r in results)
    r_total_all = sum(r["total_r"] for r in results)
    print(f"  {'-'*50}")
    print(f"  TOTAL        {trades_total:6d} {wins_total/trades_total*100:5.1f}%  {r_total_all:+7.1f}R")
    print(f"\n  Tempo: {elapsed:.0f}s | Salvo: {out}")
    print(f"{'='*55}")
    return True

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--top",      type=int, default=20)
    p.add_argument("--months",   type=int, default=3)
    p.add_argument("--interval", default="1h")
    p.add_argument("--symbols",  nargs="*", help="Lista específica de símbolos")
    args = p.parse_args()
    ok = asyncio.run(scan(args.top, args.interval, args.months, args.symbols))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
