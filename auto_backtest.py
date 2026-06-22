"""
GAUSS+DNA — Backtest automático por sinal (autorizado 22/06)

Toda vez que um sinal real é enviado (cycles.py, após enviar_sinal() retornar OK),
este módulo varre o histórico recente do mesmo símbolo/timeframe procurando outras
ocorrências do mesmo tipo de sinal (mesma fonte) e simula pra frente usando a MESMA
régua de stop/TP do sinal real (notify.calcular_stop_tp) e a MESMA cascata de detecção
(analyze.analisar) — sem duplicar lógica, qualquer ajuste de filtro/gestão futuro vale
automaticamente pros dois. Objetivo: dado de calibração em minutos, não em dias (não
precisa esperar o resultado real fechar via state.py/resultados_log.csv).

Limitação conhecida: a saída do bot real tem 3 estágios (TP1=50%→BE, TP2=30%, 20%
"runner" via MM10/MM21+estrutura). Aqui o runner é aproximado como TP2 fechando os
50% finais de uma vez (sem tracking candle-a-candle do trailing) — suficiente pra
medir STOP-rate e winrate de entrada, não é réplica exata do resultados_log.csv.
"""
import csv
import logging
from datetime import datetime, timezone

from analyze import analisar, calcular_indicadores
from notify import calcular_stop_tp
from scanner import buscar_candles
from config import BACKTEST_FILE

log = logging.getLogger("auto_backtest")

_LOOKBACK = 500   # candles buscados pra varrer ocorrências passadas
_JANELA_MIN = 100  # mínimo de candles antes de uma ocorrência pra calcular_indicadores() funcionar
_PASSO = 2         # passo do sliding window (2 = avalia a cada 2 candles, mais rápido)
_COOLDOWN_BARRAS = 6  # ocorrências da mesma fonte/direção a menos de N candles uma da outra contam só 1x

_CAMPOS = ["data_hora", "simbolo", "timeframe", "fonte", "direcao",
           "n_ocorrencias", "n_stop", "n_tp1_be", "n_tp2", "winrate", "r_medio"]


def _simular_forward(candles, i, eh_long, r, fonte):
    """A partir do candle i (sinal detectado em i), resolve STOP/TP1_BE/TP2 olhando candles[i+1:]."""
    ind = calcular_indicadores(candles[: i + 1])
    if not ind:
        return None
    preco_entrada = ind["preco"]
    stp = calcular_stop_tp(eh_long, preco_entrada, ind["atr"], ind["swing_low"],
                            ind["swing_high"], fonte, r.get("classificacao"))
    stop, tp1, tp2 = stp["stop"], stp["tp1"], stp["tp2"]
    if stp["risco"] <= 0:
        return None

    tp1_atingido = False
    for j in range(i + 1, len(candles)):
        hi, lo = candles[j]["high"], candles[j]["low"]
        if eh_long:
            if not tp1_atingido and hi >= tp1:
                tp1_atingido = True
            if tp1_atingido and lo <= preco_entrada:
                return ("TP1_BE", stp["r1"] * 0.5)
            if hi >= tp2:
                return ("TP2", stp["r1"] * 0.5 + stp["r_final"] * 0.5)
            if lo <= stop:
                return ("STOP", -1.0) if not tp1_atingido else ("TP1_BE", stp["r1"] * 0.5)
        else:
            if not tp1_atingido and lo <= tp1:
                tp1_atingido = True
            if tp1_atingido and hi >= preco_entrada:
                return ("TP1_BE", stp["r1"] * 0.5)
            if lo <= tp2:
                return ("TP2", stp["r1"] * 0.5 + stp["r_final"] * 0.5)
            if hi >= stop:
                return ("STOP", -1.0) if not tp1_atingido else ("TP1_BE", stp["r1"] * 0.5)
    return None  # não resolveu dentro da janela disponível


def _registrar_backtest(simbolo, tf, fonte, direcao, n_oco, n_stop, n_be, n_tp2, r_medio):
    BACKTEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    novo = not BACKTEST_FILE.exists()
    n_resolvidos = n_stop + n_be + n_tp2
    winrate = (n_be + n_tp2) / n_resolvidos * 100 if n_resolvidos else 0.0
    with open(BACKTEST_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CAMPOS, delimiter=";")
        if novo:
            w.writeheader()
        w.writerow({
            "data_hora": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "simbolo": simbolo, "timeframe": tf, "fonte": fonte, "direcao": direcao,
            "n_ocorrencias": n_resolvidos, "n_stop": n_stop, "n_tp1_be": n_be,
            "n_tp2": n_tp2, "winrate": round(winrate, 1), "r_medio": round(r_medio, 3),
        })


async def backtest_sinal(session, simbolo, tf, fonte, direcao):
    """Chamado por cycles.py logo após um sinal real ser enviado com sucesso."""
    try:
        candles = await buscar_candles(session, simbolo, tf, limite=_LOOKBACK)
        if not candles or len(candles) < _JANELA_MIN + 10:
            return
        eh_long = direcao == "LONG"

        n_stop = n_be = n_tp2 = 0
        soma_r = 0.0
        ultimo_match = -999

        for i in range(_JANELA_MIN, len(candles) - 1, _PASSO):
            if i - ultimo_match < _COOLDOWN_BARRAS:
                continue
            r = analisar(simbolo, candles[: i + 1])
            if not r or r.get("fonte_sinal") != fonte or r.get("sinal") != direcao:
                continue

            resultado = _simular_forward(candles, i, eh_long, r, fonte)
            if not resultado:
                continue
            ultimo_match = i
            tag, r_val = resultado
            soma_r += r_val
            if tag == "STOP":
                n_stop += 1
            elif tag == "TP1_BE":
                n_be += 1
            elif tag == "TP2":
                n_tp2 += 1

        n_resolvidos = n_stop + n_be + n_tp2
        if n_resolvidos == 0:
            return
        r_medio = soma_r / n_resolvidos
        _registrar_backtest(simbolo, tf, fonte, direcao, n_resolvidos, n_stop, n_be, n_tp2, r_medio)
        log.info(f"📊 Backtest {simbolo} {tf} {fonte}/{direcao}: "
                 f"{n_resolvidos} ocorrências — {n_stop} STOP, {n_be} TP1_BE, {n_tp2} TP2, R médio {r_medio:.2f}")
    except Exception as e:
        log.warning(f"⚠️ Backtest automático falhou pra {simbolo} {tf}: {e}")


def resumo_backtest(horas=24):
    """Agrega backtest_log.csv por fonte nas últimas N horas — mesmo padrão de state.resumo_resultados()."""
    if not BACKTEST_FILE.exists():
        return {}
    agora = datetime.now(timezone.utc)
    por_fonte = {}
    with open(BACKTEST_FILE, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            try:
                dt = datetime.strptime(row["data_hora"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if (agora - dt).total_seconds() > horas * 3600:
                continue
            fonte = row["fonte"]
            g = por_fonte.setdefault(fonte, {"n": 0, "stop": 0, "winrate_soma": 0.0, "r_soma": 0.0})
            g["n"] += 1
            g["stop"] += int(row["n_stop"])
            g["winrate_soma"] += float(row["winrate"])
            g["r_soma"] += float(row["r_medio"])
    return {f: {"amostras": g["n"], "winrate_medio": round(g["winrate_soma"] / g["n"], 1),
                "r_medio": round(g["r_soma"] / g["n"], 3)}
            for f, g in por_fonte.items()}
