"""
GAUSS+DNA — Teste local de sinais
Analisa BTC, ETH e SOL sem enviar para o Telegram.
Uso: python testar.py
"""
import asyncio
import aiohttp
import sys
import os

# Garante que os módulos do bot sejam encontrados
sys.path.insert(0, os.path.dirname(__file__))

from scanner import buscar_candles
from analyze import analisar


MOEDAS_TESTE = [
    ("BTCUSDT",  "BTC/USDT",  "BTC"),
    ("ETHUSDT",  "ETH/USDT",  "ETH"),
    ("SOLUSDT",  "SOL/USDT",  "SOL"),
    ("BNBUSDT",  "BNB/USDT",  "BNB"),
    ("XRPUSDT",  "XRP/USDT",  "XRP"),
]

TIMEFRAMES = ["15m", "1h"]


def _fmt_sinal(result, tf):
    sinal  = result.get("sinal") or "—"
    fonte  = result.get("fonte_sinal") or ""
    grade  = result.get("grade", "?")
    score  = result.get("score", 0)
    rsi    = result.get("rsi", 0)
    adx    = result.get("adx", 0)
    preco  = result.get("preco", 0)
    tend   = result.get("tendencia", "?")
    kal    = "↑" if result.get("kalman_subindo") else "↓"
    dna    = "✅" if result.get("dna_flow_bull" if sinal=="LONG" else "dna_flow_bear") else "—"
    trl    = "✅" if result.get("trendilo_long" if sinal=="LONG" else "trendilo_short") else "—"

    cor = ""
    if   sinal == "LONG":  cor = "\033[92m"   # verde
    elif sinal == "SHORT": cor = "\033[91m"    # vermelho
    reset = "\033[0m"

    linha_sinal = f"{cor}  ➜ {sinal} [{fonte}] Grade {grade}{reset}" if sinal != "—" else f"  ➜ Sem sinal"
    return (
        f"\n  [{tf}] Preço ${preco:.4g} | Score {score:+d} | RSI {rsi:.1f} | ADX {adx:.1f}"
        f" | Tendência: {tend} | Kalman: {kal}"
        f"\n  DNA Flow: {dna} | Trendilo: {trl}"
        f"\n{linha_sinal}"
    )


async def testar():
    print("=" * 60)
    print("  GAUSS+DNA — Teste de Sinais (sem Telegram)")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        for sym, label, abrev in MOEDAS_TESTE:
            print(f"\n{'─'*50}")
            print(f"  {label}")
            print(f"{'─'*50}")

            for tf in TIMEFRAMES:
                candles = await buscar_candles(session, sym, tf, limite=250)
                if not candles:
                    print(f"  [{tf}] ❌ Sem dados")
                    continue

                result = analisar(sym, candles)
                if not result:
                    print(f"  [{tf}] ❌ Análise falhou")
                    continue

                print(_fmt_sinal(result, tf))

    print(f"\n{'='*60}")
    print("  Teste concluído!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(testar())
