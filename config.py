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

RISK_BY_GRADE = {"B": 0.005, "A": 0.01, "A+": 0.015, "S": 0.02, "S+": 0.03}
RISK_SCOUT    = 0.01                                     # SCOUT = 1% (sinal secundário)

MAX_CYCLE_RISK      = 0.10   # teto 10% de capital por ciclo
MAX_SCOUT_PER_CYCLE = 2      # máximo 2 SCOUTs por ciclo
MAX_LONG_PER_CYCLE  = 2      # máximo 2 LONGs por ciclo (anti-correlação)
MAX_SHORT_PER_CYCLE = 2      # máximo 2 SHORTs por ciclo

# ── Modo INSTITUCIONAL (pedido 20/06 — filtro rígido, "apenas movimentos
# institucionais de alta probabilidade") — risco/cooldown próprios, mais
# conservadores que o modo FLEX padrão acima.
RISK_INSTITUCIONAL          = 0.01   # 1% fixo por trade, independente da grade
MAX_CYCLE_RISK_INSTITUCIONAL = 0.05  # teto 5% de capital por ciclo
MAX_POSICOES_INSTITUCIONAL   = 2     # máximo 2 posições simultâneas abertas
COOLDOWN_INSTITUCIONAL_MESMA_DIR = 10800  # 3h mesma direção
COOLDOWN_INSTITUCIONAL_OPOSTA    = 7200   # 2h direção oposta

# ── Nível de filtros (1=mínimo, 2=moderado, 3=completo) ──────────────────────
# 1: vol 50%, sem adx_subindo, sem liq_topo/fundo, fluxo >=1
# 2: vol 65%, adx_subindo ativo, fluxo >=2
# 3: vol 80%, todas as defesas SMC ativas (padrão)
FILTER_LEVEL = int(os.environ.get("FILTER_LEVEL", "3"))

# ── AJUSTE PROFISSIONAL (21/06) — qualidade acima de quantidade ──────────────
# RVOL mínimo por timeframe (30M tende a ter RVOL mais baixo que H1 com o
# mesmo grau de convicção real — piso diferenciado evita bloqueio excessivo).
RVOL_MIN_BY_TF = {"30m": 0.70, "1h": 0.80}

# Piso universal de força de tendência — aplicado a TODOS os tipos de sinal,
# além do ADX próprio de cada condição em analyze.py (que pode ser mais alto).
ADX_MIN_GLOBAL = 20

# Só opera grade A e S (S+ incluso) — ignora B e C/BRONZE.
GRAUS_PERMITIDOS = {"A", "A+", "S", "S+"}

# Filtro de Regime Global — BTC H1 neutro (sem direção clara) bloqueia
# LONG e SHORT em todas as moedas até o regime mudar.
BTC_REGIME_ADX_MAX  = 20
BTC_REGIME_RSI_MIN  = 45
BTC_REGIME_RSI_MAX  = 55

# ── Arquivos de estado ────────────────────────────────────────────────────────
STATE_FILE   = Path("last_signals.json")
JOURNAL_FILE = Path(__file__).parent / "signals_log.csv"
RESULTS_FILE = Path(__file__).parent / "resultados_log.csv"   # rastreamento de TP/STOP por sinal
