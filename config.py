"""
GAUSS+DNA — Configuração central
Todas as variáveis de ambiente e constantes do bot.
"""
import os
from pathlib import Path

# ── Telegram ──────────────────────────────────────────────────────────────────
TG_TOKEN  = os.environ.get("TG_TOKEN", "")
TG_CHATID = os.environ.get("TG_CHATID", "")

# ── WhatsApp (CallMeBot) ──────────────────────────────────────────────────────
WA_PHONE  = os.environ.get("WA_PHONE", "")    # ex: 5511999999999 (sem +)
WA_APIKEY = os.environ.get("WA_APIKEY", "")

# ── Timeframes ────────────────────────────────────────────────────────────────
# AJUSTE PROFISSIONAL (21/06) — qualidade acima de quantidade: operar somente
# H1 e 30M, ignorar 5M/15M (ruído demais pro perfil de sinal institucional).
TIMEFRAME  = os.environ.get("TIMEFRAME", "1h")
_TF_PERMITIDOS = {"30m", "1h"}
TIMEFRAMES = [t.strip() for t in os.environ.get("TIMEFRAMES", TIMEFRAME).split(",") if t.strip() in _TF_PERMITIDOS]
if not TIMEFRAMES:
    TIMEFRAMES = ["30m", "1h"]

# ── Modo de operação ──────────────────────────────────────────────────────────
SIGNAL_MODE    = os.environ.get("SIGNAL_MODE", "FLEX").upper()  # FLEX | ELITE | INSTITUCIONAL
LOOP_MODE      = os.environ.get("LOOP_MODE", "false").lower() == "true"
TEST_MODE      = os.environ.get("TEST_MODE",  "false").lower() == "true"
CYCLE_INTERVAL = int(os.environ.get("CYCLE_INTERVAL", "0"))    # segundos (0 = aguarda vela)

# ── Scanner dinâmico ──────────────────────────────────────────────────────────
DYNAMIC_SCAN = os.environ.get("DYNAMIC_SCAN", "true").lower() == "true"
SCANNER_TOP  = int(os.environ.get("SCANNER_TOP", "50"))   # top N moedas por volume
SCAN_EVERY   = int(os.environ.get("SCAN_EVERY", "2"))     # rescan a cada N ciclos

# ── Gestão de risco ───────────────────────────────────────────────────────────
CAPITAL   = float(os.environ.get("CAPITAL",  "100"))    # capital total em USD
RISK_PCT  = float(os.environ.get("RISK_PCT", "0.03"))   # risco base por trade (3%)

# ── GAUSS+DNA v5.0 (23/06) — gestão de risco em dólar fixo, banca real pequena
# ($90). Substitui CAPITAL/RISK_PCT/RISK_BY_GRADE/RISK_SCOUT acima (que ficam só
# como fallback de outros scripts fora do bot principal, ex: bot_manual.py) pra
# tudo que toca tamanho de posição e circuit breakers em notify.py/cycles.py.
BANCA_V5           = 90.0    # banca real (USD)
MARGEM_POR_TIER_V5 = {"PRATA": 30.0, "BRONZE": 15.0}   # margem fixa por tier
# Alavancagem dinâmica por tier, range 5x-20x (autorizado 23/06 — pedido "alavancagem de 5 x até 20
# pode ativar sinal real"; substitui o fixo 3x anterior): tier melhor = mais alavancagem no range.
ALAVANCAGEM_POR_TIER_V5 = {"BRONZE": 5, "PRATA": 20, "OURO": 20}
RISCO_POR_TRADE_V5  = 2.70    # referência de risco por trade (~3% da banca)
PERDA_MAX_DIA_V5    = 5.40    # circuit breaker diário (~6% da banca) — bloqueia novas entradas no dia
PAUSA_2_PERDAS_V5   = 7200    # 2h de pausa após 2 perdas (STOP) consecutivas
MAX_POSICOES_V5     = 2       # máximo de posições simultâneas — a 2ª entra com lote pela metade
NO_TRADE_PRIMEIROS_MIN_V5 = 15  # não opera nos primeiros 15min de cada vela H1 (UTC)

# Risco pela metade (autorizado 21/06 — banca real em $86, winrate 26%/24h ainda sem
# dado novo suficiente pra confirmar os 2 fixes de qualidade de entrada do mesmo dia,
# Filtro de Execução V2 e defesa de RSI/StochRSI no BB_BREAK). Protege capital enquanto
# acumula trades novos — não toca em stop/TP/leverage (gestão), só no tamanho da posição.
# Reverter pra tabela original quando os trades novos confirmarem melhora no winrate.
RISK_BY_GRADE = {"B": 0.0025, "A": 0.005, "A+": 0.0075, "S": 0.01, "S+": 0.015}
RISK_SCOUT    = 0.005                                    # SCOUT = 0.5% (sinal secundário)

MAX_CYCLE_RISK      = 0.10   # teto 10% de capital por ciclo
MAX_SCOUT_PER_CYCLE = 2      # máximo 2 SCOUTs por ciclo
MAX_LONG_PER_CYCLE  = 2      # máximo 2 LONGs por ciclo (anti-correlação)
MAX_SHORT_PER_CYCLE = 2      # máximo 2 SHORTs por ciclo

# ── Modo INSTITUCIONAL (pedido 20/06 — filtro rígido, "apenas movimentos
# institucionais de alta probabilidade") — risco/cooldown próprios, mais
# conservadores que o modo FLEX padrão acima.
# AJUSTE INSTITUCIONAL ELITE (21/06): risco agora varia por grade (S opera
# mais arriscado que A+, que é o degrau mais baixo aceito neste modo desde
# que GRAUS_PERMITIDOS_INSTITUCIONAL passou a excluir grade A); máx. de
# posições simultâneas sobe de 2 pra 3 (pedido explícito do usuário).
RISK_INSTITUCIONAL_POR_GRADE = {"A+": 0.005, "S": 0.01}   # 0.5% A+ | 1% S
MAX_CYCLE_RISK_INSTITUCIONAL = 0.05  # teto 5% de capital por ciclo
MAX_POSICOES_INSTITUCIONAL   = 3     # máximo 3 posições simultâneas abertas
COOLDOWN_INSTITUCIONAL_MESMA_DIR = 10800  # 3h mesma direção
COOLDOWN_INSTITUCIONAL_OPOSTA    = 7200   # 2h direção oposta

# DNA+GAUSS INSTITUCIONAL V2 (22/06): grade A volta a ser permitida (doc do
# usuário pede "Grades permitidas: A, S, S+" — grade aqui ainda vem do Score
# Inst, S>=90/A+>=80/A>=70, "S+" do doc não tem efeito real nesse esquema)
GRAUS_PERMITIDOS_INSTITUCIONAL = {"S", "A+", "A"}

# Circuit breaker (pedido 21/06): após N stops consecutivos no modo
# institucional, pausa novas entradas até a primeira posição fechar como
# vencedora (TP1_BE ou TP2) — reage a dado real de mercado, não a tempo fixo.
STOPS_CONSECUTIVOS_PAUSA = 3

# ── Nível de filtros (1=mínimo, 2=moderado, 3=completo) ──────────────────────
# 1: vol 50%, sem adx_subindo, sem liq_topo/fundo, fluxo >=1
# 2: vol 65%, adx_subindo ativo, fluxo >=2
# 3: vol 80%, todas as defesas SMC ativas (padrão)
FILTER_LEVEL = int(os.environ.get("FILTER_LEVEL", "3"))

# ── AJUSTE PROFISSIONAL (21/06) — qualidade acima de quantidade ──────────────
# RVOL mínimo por timeframe (30M tende a ter RVOL mais baixo que H1 com o
# mesmo grau de convicção real — piso diferenciado evita bloqueio excessivo).
# 1h baixou de 0.80 pra 0.70 em 22/06 (CLASSIFICAÇÃO V4) — ver RVOL_MIN_EXEC
# abaixo: precisa bater com o piso mais baixo dos 3 degraus (BRONZE=0.7),
# senão o gate universal pré-classificação bloqueia BRONZE antes dele rodar.
RVOL_MIN_BY_TF = {"30m": 0.70, "1h": 0.70}

# Piso universal de força de tendência — aplicado a TODOS os tipos de sinal,
# além do ADX próprio de cada condição em analyze.py (que pode ser mais alto).
# GAUSS+DNA v5.0 (23/06) subiu de 15 pra 20 ("Bloquear LONG/SHORT: ADX<20" —
# substitui a CLASSIFICAÇÃO INSTITUCIONAL V3/V4) — ver CLAUDE.md.
ADX_MIN_GLOBAL = 20

# GRAUS_PERMITIDOS (gate por grade letra S+/S/A/B no modo padrão FLEX/ELITE)
# foi REMOVIDO na V3 — auditoria de 3 runs reais seguidos mostrou zero sinais
# enviados com o funil empilhado (grade + ADX_MIN_GLOBAL + RVOL_MIN_EXEC +
# score_inst>=75 fixo), bloqueando até movimentos reais fortes (ALLO/GWEI/HUS).
# A qualidade de entrada agora é gate da classificação OURO/PRATA/BRONZE (ver
# CLASSIFICAÇÃO INSTITUCIONAL V3 em CLAUDE.md) — grade letra continua existindo
# só para dimensionar risco (RISK_BY_GRADE), não bloqueia mais entrada.

# Filtro de Execução V2 (autorizado 21/06 — caso real de 78% STOP em 24h, padrão
# binário STOP-ou-TP2 sem nenhum TP1_BE, indicando problema de qualidade de
# entrada). Camada final acima dos pisos por tipo de sinal já existentes (que
# variam 35-60 — ver _inst_min em cycles.py) — "confiança" exibida no Telegram
# é score_inst-10 (notify.py), então confiança>=65% equivale a score_inst>=75.
# Reduz frequência (não é o "aumentar frequência" do V2 original do usuário —
# essa parte foi descartada por contradizer este filtro, ver CLAUDE.md), mas
# ataca diretamente a taxa de STOP ao exigir confluência institucional bem mais
# alta pra qualquer sinal ser executado, independente do tipo.
# ⚠️ SUPERSEDED 22/06 (V3) — INST_MIN_EXEC=75 forçava score_inst>=75 pra TODO
# sinal, contradizendo a própria classificação V3 (BRONZE>=60, PRATA>=70), que
# agora é o gate real de qualidade (ver classificar_v2() em analyze.py e as
# REGRAS DE EXECUÇÃO em cycles.py). Constante mantida só por compatibilidade
# de import (não é mais lida como piso bloqueante em cycles.py).
INST_MIN_EXEC = 75
# RVOL_MIN_EXEC: piso universal de RVOL — caiu de 1.2 pra 1.0 ("Bloquear LONG/
# SHORT: RVOL<1.0" da CLASSIFICAÇÃO INSTITUCIONAL V3, autorizado 22/06).
# Caiu de novo, 1.0→0.7, em 22/06 (CLASSIFICAÇÃO V4, tabela própria do usuário):
# a V4 introduziu RVOL>=0.7 como piso explícito de BRONZE, mais baixo que o
# piso universal antigo (1.0) — sem este ajuste, BRONZE nunca veria candidatos
# com RVOL 0.7-1.0 (bloqueados aqui antes de chegar em classificar_v2()), o que
# tornaria o afrouxamento de BRONZE pedido pelo usuário código morto na prática.
RVOL_MIN_EXEC = 0.7

# Filtro de Regime Global — BTC H1 neutro (sem direção clara) bloqueia
# LONG e SHORT em todas as moedas até o regime mudar.
# AJUSTE 22/06 (auditoria de dia inteiro sem sinal — ver CLAUDE.md "AUDITORIA
# DE OPORTUNIDADES PERDIDAS"): ADX_MAX 20→15, alinhado ao piso global
# ADX_MIN_GLOBAL já usado no resto do sistema — exige BTC genuinamente mais
# flat antes de zerar o ciclo inteiro (esse filtro sozinho zerou ciclos por
# horas seguidas hoje: 00:27-08:48 e 20:18-21:52 UTC, sem nenhum sinal em
# nenhuma moeda nesses horários). RSI 45-55 intocado — mudança isolada.
BTC_REGIME_ADX_MAX  = 15
BTC_REGIME_RSI_MIN  = 45
BTC_REGIME_RSI_MAX  = 55

# ── Arquivos de estado ────────────────────────────────────────────────────────
STATE_FILE   = Path("last_signals.json")
JOURNAL_FILE = Path(__file__).parent / "signals_log.csv"
RESULTS_FILE = Path(__file__).parent / "resultados_log.csv"   # rastreamento de TP/STOP por sinal
BACKTEST_FILE = Path(__file__).parent / "backtest_log.csv"    # backtest automático por sinal (22/06)
