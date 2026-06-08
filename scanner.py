"""
GAUSS+DNA — Scanner dinâmico de moedas
Busca os melhores pares USDT no MEXC e ranqueia por potencial de sinal.
"""
import asyncio
import logging
import aiohttp
from coins import _EXCLUIR, _EXCLUIR_SUFIXO
from indicators import serie_ema, serie_atr, calcular_adx
from analyze import calcular_indicadores

log = logging.getLogger("GAUSS+DNA")

# MEXC usa "60m" em vez de "1h" e formatos próprios
_TF_MEXC = {"1h":"60m","2h":"120m","4h":"4h","6h":"6h","8h":"8h","12h":"12h","1d":"1d"}


# ── Busca de candles ──────────────────────────────────────────────────────────

async def buscar_candles(session, simbolo, tf, limite=250):
    """Busca candles na API MEXC com 3 tentativas e backoff."""
    intervalo = _TF_MEXC.get(tf, tf)
    url = f"https://api.mexc.com/api/v3/klines?symbol={simbolo}&interval={intervalo}&limit={limite}"
    esperas = [1, 2, 4]
    for tentativa in range(3):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                status = r.status
                if status == 404:
                    log.warning(f"buscar_candles {simbolo} [{tf}]: HTTP 404 — símbolo não encontrado, ignorando")
                    return None
                if status == 429:
                    log.warning(f"buscar_candles {simbolo} [{tf}]: HTTP 429 — limite de requisições, aguardando 5s (tentativa {tentativa+1}/3)")
                    await asyncio.sleep(5)
                    if tentativa < 2: continue
                    return None
                data = await r.json()
            if not isinstance(data, list):
                log.warning(f"buscar_candles {simbolo} [{tf}]: {str(data)[:80]}")
                return None
            if len(data) < 60:
                return None
            return [{"o": float(k[1]), "h": float(k[2]), "l": float(k[3]),
                     "c": float(k[4]), "v": float(k[5])} for k in data]
        except asyncio.TimeoutError:
            espera = esperas[tentativa] if tentativa < len(esperas) else esperas[-1]
            log.warning(f"buscar_candles {simbolo} [{tf}]: timeout (tentativa {tentativa+1}/3), aguardando {espera}s")
            if tentativa < 2: await asyncio.sleep(espera)
        except Exception as e:
            espera = esperas[tentativa] if tentativa < len(esperas) else esperas[-1]
            log.warning(f"buscar_candles {simbolo} [{tf}]: {e} (tentativa {tentativa+1}/3), aguardando {espera}s")
            if tentativa < 2: await asyncio.sleep(espera)
    log.warning(f"buscar_candles {simbolo} [{tf}]: falha após 3 tentativas — ignorando")
    return None


async def _buscar_seguro(session, simbolo, tf):
    """Versão sem exceção — retorna None em caso de falha."""
    try:
        return await buscar_candles(session, simbolo, tf)
    except Exception:
        return None


async def _prefetch_lote(session, moedas, tf, tamanho_lote=15):
    """Busca candles de todas as moedas em lotes paralelos. Retorna lista alinhada com moedas."""
    resultados = []
    for i in range(0, len(moedas), tamanho_lote):
        lote = moedas[i:i+tamanho_lote]
        buscados = await asyncio.gather(*[_buscar_seguro(session, sym, tf) for sym, _, _ in lote])
        resultados.extend(buscados)
        if i + tamanho_lote < len(moedas):
            await asyncio.sleep(0.05)
    return resultados


# ── Scanner de mercado ────────────────────────────────────────────────────────

async def buscar_top_pares_usdt(session, vol_min_m=1.0, max_pares=400):
    """Busca os melhores pares USDT do MEXC — combina volume + maiores altas do dia."""
    url = "https://api.mexc.com/api/v3/ticker/24hr"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            data = await r.json()
        if not isinstance(data, list):
            return []

        todos_pares = []
        for t in data:
            sym = t["symbol"]
            if not sym.endswith("USDT"): continue
            base = sym[:-4]
            if base in _EXCLUIR: continue
            if any(sub in base for sub in _EXCLUIR_SUFIXO): continue
            try:
                vol = float(t.get("quoteVolume", "0"))
                pct = float(t.get("priceChangePercent", "0"))
                todos_pares.append((sym, base, vol, pct))
            except Exception:
                continue

        # Top N por volume (liquidez garantida)
        por_vol = sorted(todos_pares, key=lambda x: x[2], reverse=True)
        top_vol = [(s, b, v) for s, b, v, _ in por_vol if v >= vol_min_m * 1e6][:max_pares]

        # Maiores altas do dia (≥5% e volume mínimo $500k) — captura pumps em andamento
        por_alta = sorted(todos_pares, key=lambda x: x[3], reverse=True)
        top_alta = [(s, b, v) for s, b, v, p in por_alta if p >= 5.0 and v >= 500_000][:50]

        # Combina e deduplica mantendo top_vol primeiro
        vistos = {s for s, _, _ in top_vol}
        combinados = list(top_vol)
        novos_altas = [(s, b, v) for s, b, v in top_alta if s not in vistos]
        combinados += novos_altas
        if novos_altas:
            nomes = [b for _, b, _ in novos_altas[:10]]
            log.info(f"📈 Maiores altas adicionadas ao scan: {', '.join(nomes)}")
        return combinados
    except Exception as e:
        log.warning(f"Scanner: erro ao buscar pares — {e}")
        return []


def _pontuar_rapido(candles):
    """Pontuação rápida para ranquear moedas candidatas. Retorna 0 se não serve."""
    if len(candles) < 60:
        return 0
    fechamentos = [c["c"] for c in candles]
    volumes     = [c["v"] for c in candles]
    preco       = fechamentos[-1]

    atr = serie_atr(candles, 14)[-1]
    atr_pct = (atr / preco) * 100
    if atr_pct < 0.25 or atr_pct > 4.0:
        return 0

    try:
        _, _, adx, _ = calcular_adx(candles[-60:])
    except Exception:
        return 0
    if adx < 15:
        return 0

    e200 = serie_ema(fechamentos, 200)[-1]
    dist_e200 = abs(preco - e200) / max(e200, 1e-10)
    tendencia_score = min(25, dist_e200 * 400)  # 0% → 0pts, 2.5% → 10pts, 6.25%+ → 25pts

    vol_ma = sum(volumes[-20:]) / 20
    vol_ok = volumes[-1] > vol_ma * 1.2

    atr_ideal = max(0, 25 - abs(atr_pct - 1.5) * 8)
    score = adx * 0.40 + tendencia_score + (15 if vol_ok else 0) + atr_ideal
    return score


def _bonus_institucional(candles):
    """Calcula o Score Inst real (mesmo critério usado na graduação dos sinais) e
    devolve um bônus de ranking — moedas com forte convicção institucional sobem
    na lista de monitoramento mesmo perdendo em volume bruto para outras."""
    try:
        ind = calcular_indicadores(candles)
        if ind is None:
            return 0, "FRACO"
    except Exception:
        return 0, "FRACO"
    score_inst = max(ind["score_inst_long"], ind["score_inst_short"])
    direcional  = ind["tbull_r"] or ind["tbear_r"]
    tend_forte  = ind["tendencia_bull"] or ind["tendencia_bear"]
    bonus_dir   = 8 if tend_forte else (4 if direcional else 0)
    if score_inst >= 85: return 25 + bonus_dir, "ELITE"
    if score_inst >= 70: return 15 + bonus_dir, "FORTE"
    if score_inst >= 55: return  5 + bonus_dir, "MÉDIO"
    return bonus_dir, "FRACO"


async def escanear_melhores_moedas(session, tf="15m", top_n=20):
    """Varre o mercado e retorna as top_n moedas com melhores condições agora."""
    log.info(f"🔍 Rastreador iniciado — buscando melhores moedas [{tf}]...")
    pares = await buscar_top_pares_usdt(session)
    if not pares:
        log.warning("Rastreador: sem dados, mantendo lista atual")
        return None

    async def _avaliar_par(sym, base, vol_usd):
        try:
            candles = await buscar_candles(session, sym, tf, limite=250)
            if candles:
                s = _pontuar_rapido(candles)
                if s > 0:
                    bonus, cls_inst = _bonus_institucional(candles)
                    return (sym, f"{base}/USDT", base, s + bonus, vol_usd, cls_inst)
        except Exception:
            pass
        return None

    pontuados = []
    tamanho_lote = 15
    for i in range(0, len(pares), tamanho_lote):
        lote = pares[i:i+tamanho_lote]
        resultados = await asyncio.gather(*[_avaliar_par(sym, base, vol) for sym, base, vol in lote])
        for r in resultados:
            if r:
                pontuados.append(r)
                log.info(f"  ✓ {r[2]:8s} | Score {r[3]:.0f} | Inst {r[5]:6s} | Vol ${r[4]/1e6:.0f}M")
        if i + tamanho_lote < len(pares):
            await asyncio.sleep(0.05)

    pontuados.sort(key=lambda x: x[3], reverse=True)
    top = [(s, l, b) for s, l, b, _, _, _ in pontuados[:top_n]]
    if not top:
        return None

    nomes = [b for _, _, b in top]
    log.info(f"✅ Top {len(top)} selecionadas: {', '.join(nomes)}")
    return top
