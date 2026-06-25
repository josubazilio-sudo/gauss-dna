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

# ── CONFIGURAÇÃO DO USUÁRIO ────────────────────────────────────────────────────

# Legado (preservado por compatibilidade com analyze.py)
HA_CONFIRM_BARS = 1
HA_REVERSAL_OK = True
ADX_NAO_SUBINDO_BLOQUEIA = False
ADX_FLEX_MARGIN = 1.5

# Filtros principais
RVOL_MIN = 0.35

ADX_MIN_SURGE = 15
ADX_MIN_PULLBACK = 15
ADX_MIN_FLEX = 15
ADX_MIN_BB = 15
ADX_MIN_SCOUT = 15

MIN_FLUXO_LONG = 1
MIN_FLUXO_SHORT = 1

LATERAL_BARS = 12

H1_OBRIGATORIO = False
HA_H1_CONFIRMAR = False
HA_H1_PESO = 10

# V4 — alinhados ao piso do usuário
ADX_MIN_GLOBAL = 15
RVOL_MIN_BY_TF = {"30m": 0.35, "1h": 0.35}
RVOL_MIN_EXEC = 0.35

# V4 — thresholds do usuário
SCORE_MIN = 72
CONFIANCA_MIN = 60
SCORE_OURO = 90
SCORE_PRATA = 80
SCORE_BRONZE = 72

# RSI por direção
RSI_LONG_MIN = 38
RSI_LONG_MAX = 70
RSI_SHORT_MIN = 30
RSI_SHORT_MAX = 62

# Segurança — BTC
BTC_BLOQUEIA_SHORT_ABAIXO = 25

# BB (Bollinger Bands)
BLOQUEAR_LONG_BB_TOPO = True
BLOQUEAR_SHORT_BB_FUNDO = True
PENALIDADE_BB_EXTREMO = 10

# ── Filtros SCOUT CONTROLADO ────────────────────────────────────────────────
FLEX_SCOUT_ADX       = 15     # ADX mínimo para FLEX/SCOUT
FLEX_SCOUT_SEM_LIQ   = True   # FLEX/SCOUT sem exigir liquidez
MACD_R_OBRIGATORIO   = False  # MACD não obrigatório para sinais

# ── Filtros V4 (AJUSTE DE FREQUENCIA CONTROLADA) ────────────────────────────
CROSS_OBRIGATORIO    = False  # CROSS não obrigatório para sinais
PONTOS_CROSS         = 10     # pontuação do CROSS no score
PULLBACK_OBRIGATORIO = False  # PULLBACK não obrigatório para sinais
PULLBACK_PONTOS      = 8      # pontuação do PULLBACK no score
MACD_REC_OBRIGATORIO = False  # MACD recuperando não obrigatório
MACD_REC_PONTOS      = 8      # pontuação do MACD recuperando no score
MACD_ESG_OBRIGATORIO = False  # MACD esgotando não obrigatório
MACD_ESG_PONTOS      = 8      # pontuação do MACD esgotando no score
SEM_LIQ_BLOQUEAR    = False   # sem liquidez não bloqueia sinal
SEM_LIQ_PONTOS      = -5      # penalidade por falta de liquidez
FLOW_CONFIRMADO     = True    # fluxo (dna_flow/trendilo) obrigatório
LIQ_SWEEP           = False   # sweep de liquidez não exigido
H1_MTF_OBRIGATORIO  = False   # H1 MTF não obrigatório
HA_H1_CONFIRMAR     = False   # HA H1 não obrigatório para confirmar
DIST_MM21_MAX       = 7       # distância máxima da MM21 em %
BTC_H4_BLOQUEIA_LONG = False  # BTC H4 não bloqueia LONG
MM200_OBRIGATORIA   = True    # MM200 obrigatória
EXAUSTAO_BLOQUEAR   = True    # exaustao bloqueia sinal
BB_TOPO_BLOQUEAR    = True    # bb_topo bloqueia LONG
BB_FUNDO_BLOQUEAR   = True    # bb_fundo bloqueia SHORT
STOCH_EXTREMO_BLOQUEAR = False
VOLUME_SECANDO_BLOQUEAR = False
MERCADO_LATERAL_BLOQUEAR = False

# ── Arquivos de estado ────────────────────────────────────────────────────────
STATE_FILE   = Path("last_signals.json")
JOURNAL_FILE = Path(__file__).parent / "signals_log.csv"
RESULTS_FILE = Path(__file__).parent / "resultados_log.csv"   # rastreamento de TP/STOP por sinal
BACKTEST_FILE = Path(__file__).parent / "backtest_log.csv"    # backtest automático por sinal (22/06)
TESTE_RESULTS_FILE = Path(__file__).parent / "teste_resultados_log.csv"  # estrategia de teste paralela (23/06)

# ── Estratégia de teste paralela (autorizado 23/06 — "criar uma estratégia
# separada teste pra ver o que dá certo", enviada ao Telegram pra acompanhar) ──
MAX_SINAIS_TESTE_POR_CICLO = 0   # desligado (pedido do usuário 23/06 — "não quero mais sinal teste, quero sinal real")
