"""
GAUSS+DNA Backtest Runner
Uso: python backtest/run.py [--months 6] [--top 100] [--symbol SOLUSDT]

Exemplos:
  python backtest/run.py                        # top 100 + SOL, 6 meses
  python backtest/run.py --months 3 --top 50   # top 50, 3 meses
  python backtest/run.py --symbol SOLUSDT       # só SOL
  python backtest/run.py --symbol BTCUSDT,ETHUSDT,SOLUSDT  # lista manual
"""
import asyncio, aiohttp, time, argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # acessa engine.py

from backtest.engine import (
    fetch_candles, get_top_usdt_pairs, backtest_symbol,
    print_summary, save_csv, save_json
)

# ── ARGUMENTOS ────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="GAUSS+DNA Backtest")
parser.add_argument("--months",  type=int,   default=6,    help="Meses de histórico (default 6)")
parser.add_argument("--top",     type=int,   default=100,  help="Top N pares por volume (default 100)")
parser.add_argument("--symbol",  type=str,   default="",   help="Par(es) específico(s) separados por vírgula")
parser.add_argument("--interval",type=str,   default="1h", help="Timeframe (default 1h)")
parser.add_argument("--workers", type=int,   default=8,    help="Requisições paralelas (default 8)")
parser.add_argument("--no-save", action="store_true",      help="Não salvar CSV/JSON")
args = parser.parse_args()

# ── RUNNER ────────────────────────────────────────────────────────────────────

async def run_backtest():
    t0 = time.time()

    connector = aiohttp.TCPConnector(limit=args.workers)
    async with aiohttp.ClientSession(connector=connector) as session:

        # Monta lista de símbolos
        if args.symbol:
            symbols = [s.strip().upper() for s in args.symbol.split(",")]
        else:
            print(f"⏳ Buscando top {args.top} pares USDT por volume...")
            symbols = await get_top_usdt_pairs(session, args.top)
            # Garante SOL na lista
            if "SOLUSDT" not in symbols:
                symbols.append("SOLUSDT")
            print(f"   {len(symbols)} pares encontrados")

        # Fetch de candles em paralelo (semáforo para não exceder rate limit)
        sem = asyncio.Semaphore(args.workers)
        print(f"\n⏳ Baixando {args.interval} histórico ({args.months} meses) para {len(symbols)} pares...")

        async def fetch_with_sem(sym):
            async with sem:
                candles = await fetch_candles(session, sym, args.interval, args.months)
                if candles:
                    print(f"  ✓ {sym}: {len(candles)} velas")
                else:
                    print(f"  ✗ {sym}: sem dados")
                return sym, candles

        results = await asyncio.gather(*[fetch_with_sem(s) for s in symbols])

    # Backtest de cada símbolo
    print(f"\n⏳ Rodando estratégia FLEX em {len(results)} pares...")
    all_trades = []
    for sym, candles in results:
        if len(candles) < 220:
            print(f"  ⚠ {sym}: poucos dados ({len(candles)} velas), pulando")
            continue
        trades = backtest_symbol(sym, candles)
        if trades:
            wr = sum(1 for t in trades if t["r_result"] > 0) / len(trades) * 100
            avg_r = sum(t["r_result"] for t in trades) / len(trades)
            print(f"  {sym:12s}: {len(trades):3d} trades | WR {wr:.0f}% | R médio {avg_r:+.2f}")
        all_trades.extend(trades)

    elapsed = time.time() - t0
    print_summary(all_trades, elapsed)

    if not args.no_save and all_trades:
        save_csv(all_trades)
        save_json(all_trades)

    return all_trades

if __name__ == "__main__":
    asyncio.run(run_backtest())
