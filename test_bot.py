"""
GAUSS+DNA — Suite de testes automáticos
Roda antes do bot principal para detectar problemas.
Sai com código 1 se teste crítico falhar.
"""
import asyncio
import sys
import math
import random
import time

import aiohttp


# ── Resultado acumulado ───────────────────────────────────────────────────────

_passed = 0
_failed = 0
_criticos_falharam = False


def _ok(tag: str, msg: str):
    global _passed
    _passed += 1
    print(f"[{tag:<12}] ✅ {msg}")


def _fail(tag: str, msg: str, critico: bool = False):
    global _failed, _criticos_falharam
    _failed += 1
    if critico:
        _criticos_falharam = True
        print(f"[{tag:<12}] ❌ CRITICO: {msg}")
    else:
        print(f"[{tag:<12}] ⚠️  {msg}")


# ── Teste 1 — Imports ─────────────────────────────────────────────────────────

def teste_imports():
    tag = "IMPORTS"
    try:
        from indicators import calcular_rsi, serie_ema
        from analyze import calcular_indicadores, analisar
        from config import TG_TOKEN, TG_CHATID, TIMEFRAMES
        _ok(tag, "todos os modulos importados com sucesso")
    except ImportError as e:
        _fail(tag, f"falha ao importar: {e}", critico=True)


# ── Teste 2 — RSI sanidade ────────────────────────────────────────────────────

def teste_rsi():
    tag = "RSI"
    try:
        from indicators import calcular_rsi

        crescente = [100 + i * 0.5 for i in range(60)]
        rsi = calcular_rsi(crescente)
        if math.isnan(rsi):
            _fail(tag, "RSI crescente retornou NaN", critico=True)
            return
        if 60 < rsi < 100:
            _ok(tag, f"serie crescente RSI={rsi:.1f}")
        else:
            _fail(tag, f"RSI serie crescente fora do esperado: {rsi:.1f} (esperado 60-100)", critico=True)
            return

        decrescente = [200 - i * 0.5 for i in range(60)]
        rsi2 = calcular_rsi(decrescente)
        if math.isnan(rsi2):
            _fail(tag, "RSI decrescente retornou NaN", critico=True)
            return
        if 0 < rsi2 < 40:
            _ok(tag, f"serie decrescente RSI={rsi2:.1f}")
        else:
            _fail(tag, f"RSI serie decrescente fora do esperado: {rsi2:.1f} (esperado 0-40)", critico=True)

    except Exception as e:
        _fail(tag, f"excecao inesperada: {e}", critico=True)


# ── Teste 3 — EMA sanidade ────────────────────────────────────────────────────

def teste_ema():
    tag = "EMA"
    try:
        from indicators import serie_ema

        precos = [100.0] * 100 + [200.0] * 100
        ema10 = serie_ema(precos, 10)
        ema21 = serie_ema(precos, 21)

        if ema21[-1] > 150:
            _ok(tag, f"EMA21 responde a mudanca: EMA21={ema21[-1]:.1f}")
        else:
            _fail(tag, f"EMA21 nao respondeu a mudanca de preco: {ema21[-1]:.1f} (esperado >150)")

        if ema10[-1] > ema21[-1]:
            _ok(tag, f"EMA10={ema10[-1]:.1f} > EMA21={ema21[-1]:.1f} (mais rapida)")
        else:
            _fail(tag, f"EMA10={ema10[-1]:.1f} nao e maior que EMA21={ema21[-1]:.1f} apos subida")

    except Exception as e:
        _fail(tag, f"excecao inesperada: {e}")


# ── Teste 4 — calcular_indicadores com dados sintéticos ──────────────────────

_candles_sinteticos = None   # reutilizado pelo teste 5

def teste_calcular_indicadores():
    global _candles_sinteticos
    tag = "INDICADORES"
    try:
        from analyze import calcular_indicadores

        random.seed(42)
        candles = []
        preco = 100.0
        for i in range(250):
            vol = random.uniform(1000, 5000)
            change = random.gauss(0.001, 0.015)
            o = preco
            c = o * (1 + change)
            h = max(o, c) * (1 + abs(random.gauss(0, 0.005)))
            l = min(o, c) * (1 - abs(random.gauss(0, 0.005)))
            preco = c
            candles.append({
                "o": round(o, 6), "h": round(h, 6),
                "l": round(l, 6), "c": round(c, 6), "v": vol
            })
        _candles_sinteticos = candles

        result = calcular_indicadores(candles)
        if result is None:
            _fail(tag, "calcular_indicadores retornou None", critico=True)
            return

        if not isinstance(result, dict):
            _fail(tag, f"retorno nao e dict: {type(result)}", critico=True)
            return

        campos_obrigatorios = [
            "rsi", "adx", "atr", "score", "e21", "e50", "e200",
            "kalman_subindo", "trendilo_long", "trendilo_short",
            "ha_bull_1", "ha_bear_1", "dna_flow_bull", "dna_flow_bear",
        ]
        faltando = [c for c in campos_obrigatorios if c not in result]
        if faltando:
            _fail(tag, f"campos ausentes: {faltando}", critico=True)
            return

        rsi = result["rsi"]
        atr = result["atr"]

        if not (0 <= rsi <= 100):
            _fail(tag, f"RSI fora do range: {rsi}", critico=True)
            return

        if atr <= 0:
            _fail(tag, f"ATR invalido: {atr}", critico=True)
            return

        nans = [k for k, v in result.items() if isinstance(v, float) and math.isnan(v)]
        if nans:
            _fail(tag, f"campos com NaN: {nans}", critico=True)
            return

        _ok(tag, f"calcular_indicadores ok — RSI={rsi:.1f} ATR={atr:.6f} score={result['score']}")

    except Exception as e:
        _fail(tag, f"excecao inesperada: {e}", critico=True)


# ── Teste 5 — analisar() nao crasha ──────────────────────────────────────────

def teste_analisar():
    tag = "ANALISAR"
    try:
        from analyze import analisar

        candles = _candles_sinteticos
        if candles is None:
            _fail(tag, "candles sinteticos ausentes — teste 4 deve rodar antes")
            return

        result = analisar("TESTUSDT", candles)

        if result is None:
            _fail(tag, "analisar() retornou None", critico=True)
            return

        if "score" not in result or "rsi" not in result:
            _fail(tag, f"campos 'score' ou 'rsi' ausentes no resultado", critico=True)
            return

        if not isinstance(result["score"], (int, float)):
            _fail(tag, f"result['score'] nao e numerico: {type(result['score'])}", critico=True)
            return

        _ok(tag, f"analisar() ok — score={result['score']:+d} RSI={result['rsi']:.1f} sinal={result.get('sinal') or 'nenhum'}")

    except Exception as e:
        _fail(tag, f"excecao inesperada: {e}", critico=True)


# ── Teste 6 — MEXC API (async, critico) ──────────────────────────────────────

_raw_btc_candles = None   # reutilizado pelo teste 7


async def teste_mexc_api():
    global _raw_btc_candles
    tag = "MEXC"
    url = "https://api.mexc.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=10"
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    _fail(tag, f"HTTP {resp.status}", critico=True)
                    return
                data = await resp.json()

        if not isinstance(data, list) or len(data) == 0:
            _fail(tag, f"resposta vazia ou formato inesperado: {type(data)}", critico=True)
            return

        if len(data[0]) < 6:
            _fail(tag, f"candle com menos de 6 campos: {data[0]}", critico=True)
            return

        _raw_btc_candles = data
        _ok(tag, f"API ok — {len(data)} candles BTC")

    except asyncio.TimeoutError:
        _fail(tag, "timeout ao conectar com MEXC", critico=True)
    except aiohttp.ClientError as e:
        _fail(tag, f"erro de rede: {e}", critico=True)
    except Exception as e:
        _fail(tag, f"excecao inesperada: {e}", critico=True)


# ── Teste 7 — calcular_indicadores com dados reais BTC ───────────────────────

async def teste_btc_real():
    tag = "BTC_REAL"
    try:
        from analyze import calcular_indicadores

        # Busca mais candles para ter >= 60 necessarios para calcular_indicadores
        url_250 = "https://api.mexc.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=250"
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url_250) as resp:
                raw = await resp.json()

        if not isinstance(raw, list) or len(raw) < 60:
            _fail(tag, f"dados insuficientes da MEXC: {len(raw) if isinstance(raw, list) else 0} candles")
            return

        candles = [
            {
                "o": float(c[1]), "h": float(c[2]),
                "l": float(c[3]), "c": float(c[4]), "v": float(c[5])
            }
            for c in raw
        ]

        result = calcular_indicadores(candles)
        if result is None:
            _fail(tag, "calcular_indicadores retornou None com dados reais BTC", critico=True)
            return

        rsi = result["rsi"]
        if not (0 <= rsi <= 100):
            _fail(tag, f"RSI BTC real fora do range: {rsi}", critico=True)
            return

        _ok(tag, f"dados reais BTC ok — {len(candles)} candles RSI={rsi:.1f} score={result['score']:+d}")

    except Exception as e:
        _fail(tag, f"excecao inesperada: {e}", critico=True)


# ── Runner principal ──────────────────────────────────────────────────────────

async def main():
    print("=== GAUSS+DNA Auto-Review ===\n")

    # Testes síncronos
    teste_imports()
    teste_rsi()
    teste_ema()
    teste_calcular_indicadores()
    teste_analisar()

    # Testes assíncronos
    await teste_mexc_api()
    await teste_btc_real()

    # Resumo
    print()
    total = _passed + _failed
    print(f"[{'TOTAL':<12}] {_passed} passed, {_failed} failed" +
          (" (1 CRITICO)" if _criticos_falharam else ""))

    if _criticos_falharam:
        print("❌ ABORTANDO — problema critico detectado!")
        sys.exit(1)
    else:
        print("✅ Bot pronto para rodar!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
