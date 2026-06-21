"""
GAUSS+DNA — Estado e journal
Persistência do cooldown entre ciclos e registro de trades em CSV.
"""
import json
import csv
import time
from datetime import datetime
from config import STATE_FILE, JOURNAL_FILE, RESULTS_FILE

_CAMPOS_JOURNAL = [
    "data_hora", "simbolo", "timeframe", "direcao", "entrada", "stop",
    "tp_parcial", "tp_total", "r1", "r_final", "grade", "score",
    "rsi", "adx", "fonte",
]

_CAMPOS_RESULTADOS = [
    "data_abertura", "data_fechamento", "simbolo", "timeframe", "fonte", "grade",
    "direcao", "entrada", "stop", "tp1", "tp2", "preco_saida", "resultado", "r_realizado",
]

_PRAZO_MAX_HORAS = 72   # acompanha um sinal aberto por até 72h antes de marcar EXPIRADO


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


# ── Rastreamento de resultado (TP/STOP) por sinal — pedido 20/06 ──────────────
# Guarda posições "abertas" dentro do próprio dict de estado (já cacheado entre
# runs via last_signals.json) e confere o preço atual a cada ciclo pra saber se
# bateu TP1 (parcial), TP2 (fechamento), voltou ao BE pós-TP1, ou bateu o stop.
# Sem isso não dá pra saber objetivamente se o problema é stop apertado, entrada
# tardia etc. — só impressão. Resultado fechado vai pro resultados_log.csv.

def registrar_posicao_aberta(estado, simbolo, tf, direcao, entrada, stop, tp1, tp2,
                              r1, r_final, grade, fonte):
    posicoes = estado.setdefault("_posicoes_abertas", [])
    posicoes.append({
        "simbolo": simbolo, "tf": tf, "direcao": direcao,
        "entrada": entrada, "stop": stop, "tp1": tp1, "tp2": tp2,
        "r1": r1, "r_final": r_final, "grade": grade, "fonte": fonte,
        "tp1_atingido": False,
        "aberta_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ts_abertura": time.time(),
    })


def verificar_posicoes_abertas(estado, precos):
    """precos: dict {simbolo: preco_atual}. Retorna lista de posições recém-fechadas
    (com resultado e preco_saida preenchidos) e atualiza estado["_posicoes_abertas"]."""
    posicoes = estado.get("_posicoes_abertas", [])
    restantes, fechados = [], []
    agora = time.time()

    for p in posicoes:
        preco = precos.get(p["simbolo"])
        expirou = agora - p["ts_abertura"] > _PRAZO_MAX_HORAS * 3600
        if preco is None:
            if expirou:
                fechados.append({**p, "resultado": "EXPIRADO_SEM_DADO", "preco_saida": None})
            else:
                restantes.append(p)
            continue

        eh_long  = p["direcao"] == "LONG"
        stop_hit = preco <= p["stop"] if eh_long else preco >= p["stop"]
        tp1_hit  = preco >= p["tp1"]  if eh_long else preco <= p["tp1"]
        tp2_hit  = preco >= p["tp2"]  if eh_long else preco <= p["tp2"]

        if not p["tp1_atingido"]:
            if stop_hit:
                fechados.append({**p, "resultado": "STOP", "preco_saida": preco})
                continue
            if tp2_hit:   # gap raro: pulou TP1 direto pro TP2
                fechados.append({**p, "resultado": "TP2", "preco_saida": preco})
                continue
            if tp1_hit:
                p["tp1_atingido"] = True
        else:
            if tp2_hit:
                fechados.append({**p, "resultado": "TP2", "preco_saida": preco})
                continue
            be_hit = preco <= p["entrada"] if eh_long else preco >= p["entrada"]
            if be_hit:   # stop já foi pro BE após TP1 — fecha com lucro parcial garantido
                fechados.append({**p, "resultado": "TP1_BE", "preco_saida": p["entrada"]})
                continue

        if expirou:
            fechados.append({**p, "resultado": "EXPIRADO", "preco_saida": preco})
            continue
        restantes.append(p)

    estado["_posicoes_abertas"] = restantes
    return fechados


def registrar_resultado(p):
    """Grava uma posição fechada (dict vindo de verificar_posicoes_abertas) no
    resultados_log.csv, já com o R realizado calculado."""
    resultado = p["resultado"]
    r1, r_final = p["r1"], p["r_final"]
    if resultado == "STOP":
        r_realizado = -1.0
    elif resultado == "TP1_BE":
        r_realizado = r1 * 0.5
    elif resultado == "TP2":
        r_realizado = r1 * 0.5 + r_final * 0.5
    else:   # EXPIRADO / EXPIRADO_SEM_DADO — sem resolução clara, fica de fora do winrate
        r_realizado = None

    try:
        escrever_cabecalho = not RESULTS_FILE.exists() or RESULTS_FILE.stat().st_size == 0
        with RESULTS_FILE.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_CAMPOS_RESULTADOS, delimiter=";")
            if escrever_cabecalho:
                w.writeheader()
            w.writerow({
                "data_abertura":   p["aberta_em"],
                "data_fechamento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "simbolo":         p["simbolo"],
                "timeframe":       p["tf"],
                "fonte":           p["fonte"],
                "grade":           p["grade"],
                "direcao":         p["direcao"],
                "entrada":         f"{p['entrada']:.6f}",
                "stop":            f"{p['stop']:.6f}",
                "tp1":             f"{p['tp1']:.6f}",
                "tp2":             f"{p['tp2']:.6f}",
                "preco_saida":     f"{p['preco_saida']:.6f}" if p.get("preco_saida") is not None else "",
                "resultado":       resultado,
                "r_realizado":     f"{r_realizado:.2f}" if r_realizado is not None else "",
            })
    except Exception as e:
        import logging
        logging.getLogger("GAUSS+DNA").warning(f"Erro ao salvar resultado: {e}")


def resumo_resultados(horas=24):
    """Lê resultados_log.csv e devolve um resumo agregado das últimas N horas
    (contagem por resultado e winrate), pra enriquecer o diagnóstico horário.
    Inclui também detalhamento por fonte (tipo de sinal) e grade — observabilidade
    pura (não altera stop/TP/entrada), pra já ter o dado pronto pra quando a
    amostra chegar nos 30-50 trades necessários pra revisar gestão (ver CLAUDE.md)."""
    if not RESULTS_FILE.exists():
        return None
    limite = datetime.now().timestamp() - horas * 3600
    contagem = {}
    soma_r = 0.0
    n_com_r = 0
    por_fonte = {}   # fonte -> {"total": n, "stop": n, "r_soma": x, "r_n": n}
    por_grade = {}   # grade -> {"total": n, "stop": n, "r_soma": x, "r_n": n}
    try:
        with RESULTS_FILE.open(encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter=";"):
                try:
                    ts = datetime.strptime(row["data_fechamento"], "%Y-%m-%d %H:%M:%S").timestamp()
                except Exception:
                    continue
                if ts < limite:
                    continue
                res = row["resultado"]
                contagem[res] = contagem.get(res, 0) + 1
                r_val = float(row["r_realizado"]) if row.get("r_realizado") else None
                if r_val is not None:
                    soma_r += r_val; n_com_r += 1
                for chave, agrupador in (("fonte", por_fonte), ("grade", por_grade)):
                    k = row.get(chave) or "?"
                    d = agrupador.setdefault(k, {"total": 0, "stop": 0, "r_soma": 0.0, "r_n": 0})
                    d["total"] += 1
                    if res == "STOP":
                        d["stop"] += 1
                    if r_val is not None:
                        d["r_soma"] += r_val; d["r_n"] += 1
    except Exception:
        return None
    if not contagem:
        return None
    total   = sum(contagem.values())
    vitorias = contagem.get("TP1_BE", 0) + contagem.get("TP2", 0)
    winrate = vitorias / total * 100 if total else 0
    return {"contagem": contagem, "total": total, "winrate": winrate,
            "r_medio": soma_r / n_com_r if n_com_r else 0.0,
            "por_fonte": por_fonte, "por_grade": por_grade}
