"""
GAUSS+DNA Backtest Web App
Uso: python backtest/app.py
Abra: http://localhost:8080
"""
import sys, asyncio, aiohttp, uvicorn
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

sys.path.insert(0, str(Path(__file__).parent.parent))
from backtest.engine import (
    fetch_candles, get_top_usdt_pairs, backtest_symbol,
    ema_series, ha_series
)

app = FastAPI(title="GAUSS+DNA Backtest")

@app.get("/", response_class=HTMLResponse)
async def index():
    return (Path(__file__).parent / "static" / "index.html").read_text()

@app.get("/api/symbols")
async def symbols():
    async with aiohttp.ClientSession() as s:
        syms = await get_top_usdt_pairs(s, 100)
    if "SOLUSDT" not in syms:
        syms.insert(0, "SOLUSDT")
    return {"symbols": syms}

@app.post("/api/run")
async def run(payload: dict):
    symbol   = payload.get("symbol", "SOLUSDT").upper()
    months   = int(payload.get("months", 6))
    interval = payload.get("interval", "1h")

    async with aiohttp.ClientSession() as s:
        candles = await fetch_candles(s, symbol, interval, months)

    if len(candles) < 220:
        return JSONResponse({"error": f"Dados insuficientes para {symbol} ({len(candles)} velas)"}, 400)

    trades = backtest_symbol(symbol, candles)

    # EMAs sobre HA closes (mesmo que o bot)
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

    # Markers para o chart
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

    # Stats
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
        "total":      total,
        "wins":       wins,
        "losses":     total - wins,
        "win_rate":   round(wins / total * 100, 1) if total else 0,
        "avg_r":      round(total_r / total, 2) if total else 0,
        "total_r":    round(total_r, 1),
        "by_grade":   by_grade,
        "by_source":  by_source,
    }

    return {
        "symbol":     symbol,
        "candles":    [{"time": c["t"] // 1000, "open": c["o"], "high": c["h"],
                        "low": c["l"], "close": c["c"]} for c in candles],
        "indicators": indicators,
        "markers":    markers,
        "trades":     trades,
        "stats":      stats,
    }

if __name__ == "__main__":
    print("\n🚀 GAUSS+DNA Backtest App")
    print("   Abra: http://localhost:8080\n")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
