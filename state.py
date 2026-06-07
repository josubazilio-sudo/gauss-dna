"""
GAUSS+DNA — Estado e journal
Persistência do cooldown entre ciclos e registro de trades em CSV.
"""
import json
import csv
from datetime import datetime
from config import STATE_FILE, JOURNAL_FILE

_CAMPOS_JOURNAL = [
    "data_hora", "simbolo", "timeframe", "direcao", "entrada", "stop",
    "tp_parcial", "tp_total", "r1", "r_final", "grade", "score",
    "rsi", "adx", "fonte",
]


def registrar_trade(simbolo, timeframe, direcao, entrada, stop, tp_parcial, tp_total,
                    r1, r_final, grade, score, rsi, adx, fonte):
    """Adiciona uma linha ao signals_log.csv (cria com cabeçalho se necessário)."""
    try:
        escrever_cabecalho = not JOURNAL_FILE.exists() or JOURNAL_FILE.stat().st_size == 0
        with JOURNAL_FILE.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_CAMPOS_JOURNAL, delimiter=";")
            if escrever_cabecalho:
                w.writeheader()
            w.writerow({
                "data_hora":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "simbolo":    simbolo,
                "timeframe":  timeframe,
                "direcao":    direcao,
                "entrada":    f"{entrada:.6f}",
                "stop":       f"{stop:.6f}",
                "tp_parcial": f"{tp_parcial:.6f}",
                "tp_total":   f"{tp_total:.6f}",
                "r1":         f"{r1}",
                "r_final":    f"{r_final}",
                "grade":      grade,
                "score":      score,
                "rsi":        f"{rsi:.1f}",
                "adx":        f"{adx:.1f}",
                "fonte":      fonte,
            })
    except Exception as e:
        import logging
        logging.getLogger("GAUSS+DNA").warning(f"Erro ao salvar journal: {e}")


def carregar_estado():
    """Lê o arquivo de cooldown (last_signals.json). Retorna dict vazio se não existir."""
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return {}


def salvar_estado(estado):
    """Persiste o dict de cooldown em last_signals.json."""
    try:
        STATE_FILE.write_text(json.dumps(estado))
    except Exception:
        pass
