"""
GAUSS+DNA Backtest Generator
Gera backtest/results/latest.json para uso no viewer do GitHub Pages.
Uso: python backtest/generate.py --symbol BTCUSDT --months 3 --interval 1h
"""
import sys, asyncio, aiohttp, json, argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from backtest.engine import (
    fetch_candles, backtest_symbol,
    ema_series, ha_series
)

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

async def generate(symbol, months, interval):
    print(f"Buscando {symbol} {interval} ({months} meses)...")
    async with aiohttp.ClientSession() as session:
        candles = await fetch_candles(session, symbol, interval, months)

    if len(candles) < 220:
        print(f"Dados insuficientes: {len(candles)} velas")
        return False

    print(f"Rodando backtest ({len(candles)} velas)...")
    trades = backtest_symbol(symbol, candles)

    ha  = ha_series(candles)
    cls = [c["c"] for c in ha]

    def to_line(arr):
        return [{"time": candles[i]["t"] // 1000, "value": round(arr[i], 8)}
                for i in range(len(candles))]

    indicators = {
        "ema10":  to_line(ema_series(cls, 10)),
        "ema21":  to_line(ema_series(cls, 21)),
        "ema50":  to_line(ema_series(cls, 50)),
        "ema200": to_line(ema_series(cls, 200)),
    }

    markers = []
    for t in trades:
        r = t["r_result"]
        is_long = t["sig"] == "LONG"
        if r >= 1.5:    color = "#26a69a"
        elif r >= 0:    color = "#81c784"
        elif r >= -0.5: color = "#ff9800"
        else:           color = "#ef5350"
        markers.append({
            "time":     t["ts"],
            "position": "belowBar" if is_long else "aboveBar",
            "color":    color,
            "shape":    "arrowUp" if is_long else "arrowDown",
            "text":     f"{t['grade']} {r:+.1f}R",
            "size":     2 if t["grade"] == "S" else 1,
        })
    markers.sort(key=lambda x: x["time"])

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

    stats = {
        "total":     total,
        "wins":      wins,
        "losses":    total - wins,
        "win_rate":  round(wins / total * 100, 1) if total else 0,
        "avg_r":     round(total_r / total, 2) if total else 0,
        "total_r":   round(total_r, 1),
        "by_grade":  by_grade,
        "by_source": by_source,
    }

    output = {
        "symbol":    symbol,
        "interval":  interval,
        "months":    months,
        "generated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "candles":   [{"time": c["t"] // 1000, "open": c["o"], "high": c["h"],
                       "low": c["l"], "close": c["c"]} for c in candles],
        "indicators": indicators,
        "markers":   markers,
        "trades":    trades,
        "stats":     stats,
    }

    out_file = RESULTS_DIR / "latest.json"
    with open(out_file, "w") as f:
        json.dump(output, f, separators=(",", ":"))

    size_kb = out_file.stat().st_size / 1024
    print(f"\nResultados salvos: {out_file} ({size_kb:.0f} KB)")
    print(f"Trades: {total} | Win Rate: {stats['win_rate']}% | R Total: {stats['total_r']:+.1f}R")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol",   default="BTCUSDT")
    parser.add_argument("--months",   type=int, default=3)
    parser.add_argument("--interval", default="1h")
    args = parser.parse_args()
    ok = asyncio.run(generate(args.symbol.upper(), args.months, args.interval))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
