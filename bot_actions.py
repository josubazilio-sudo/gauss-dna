"""
GAUSS+DNA ELITE + FLEX — Bot GitHub Actions v2
SIGNAL_MODE=ELITE: criterios completos (sinais raros, precisos)
SIGNAL_MODE=FLEX:  criterios suavizados (mais sinais, funciona em BEAR)
"""
import asyncio, os, json, time, math, logging, aiohttp, csv
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("GAUSS+DNA")

TG_TOKEN     = os.environ.get("TG_TOKEN", "")
TG_CHATID    = os.environ.get("TG_CHATID", "")
WA_PHONE     = os.environ.get("WA_PHONE", "")    # ex: 5511999999999 (sem +)
WA_APIKEY    = os.environ.get("WA_APIKEY", "")   # API key do CallMeBot
TIMEFRAME    = os.environ.get("TIMEFRAME", "15m")
TIMEFRAMES   = [t.strip() for t in os.environ.get("TIMEFRAMES", TIMEFRAME).split(",")]
SIGNAL_MODE  = os.environ.get("SIGNAL_MODE", "FLEX").upper()
LOOP_MODE    = os.environ.get("LOOP_MODE", "false").lower() == "true"
TEST_MODE    = os.environ.get("TEST_MODE", "false").lower() == "true"
DYNAMIC_SCAN = os.environ.get("DYNAMIC_SCAN", "true").lower() == "true"
SCANNER_TOP  = int(os.environ.get("SCANNER_TOP", "50"))   # top 50 por volume
SCAN_EVERY   = int(os.environ.get("SCAN_EVERY", "4"))     # rescan a cada N ciclos (~20min em 5min)
CYCLE_INTERVAL = int(os.environ.get("CYCLE_INTERVAL", "0"))  # intervalo máximo em segundos (0=aguarda vela)
STATE_FILE   = Path("last_signals.json")
JOURNAL_FILE = Path(__file__).parent / "signals_log.csv"
CAPITAL      = float(os.environ.get("CAPITAL", "200"))   # capital total em USD ($200 → $1000 com 5x)
RISK_PCT     = float(os.environ.get("RISK_PCT", "0.03")) # risco por trade (3%) — base para Grade A
RISK_BY_GRADE = {"B": 0.02, "A": 0.03, "S": 0.05}       # B=2%, A=3%, S=5%
RISK_SCOUT    = 0.01                                      # SCOUT=1% — sinal secundário
MAX_CYCLE_RISK      = 0.10   # teto 10% de capital por ciclo — evita overexposição
MAX_SCOUT_PER_CYCLE = 2      # máximo 2 SCOUT por ciclo
MAX_LONG_PER_CYCLE  = 2      # máximo 2 LONGs por ciclo (anti-correlação)
MAX_SHORT_PER_CYCLE = 2      # máximo 2 SHORTs por ciclo

_JOURNAL_FIELDS = ["datetime","symbol","timeframe","direction","entry","stop",
                   "tp_parcial","tp_total","r1","r_final","grade","score",
                   "rsi","adx","source"]

def append_journal(symbol, timeframe, direction, entry, stop, tp_parcial, tp_total,
                   r1, r_final, grade, score, rsi, adx, source):
    """Appends one row to signals_log.csv (creates with header if needed)."""
    try:
        write_header = not JOURNAL_FILE.exists() or JOURNAL_FILE.stat().st_size == 0
        with JOURNAL_FILE.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_JOURNAL_FIELDS, delimiter=";")
            if write_header:
                w.writeheader()
            w.writerow({
                "datetime":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol":     symbol,
                "timeframe":  timeframe,
                "direction":  direction,
                "entry":      f"{entry:.6f}",
                "stop":       f"{stop:.6f}",
                "tp_parcial": f"{tp_parcial:.6f}",
                "tp_total":   f"{tp_total:.6f}",
                "r1":         f"{r1}",
                "r_final":    f"{r_final}",
                "grade":      grade,
                "score":      score,
                "rsi":        f"{rsi:.1f}",
                "adx":        f"{adx:.1f}",
                "source":     source,
            })
    except Exception as e:
        log.warning(f"journal write error: {e}")

def tf_to_minutes(tf):
    """Converte '15m', '1h', '4h' em minutos."""
    tf = tf.lower()
    if tf.endswith('m'): return int(tf[:-1])
    if tf.endswith('h'): return int(tf[:-1]) * 60
    if tf.endswith('d'): return int(tf[:-1]) * 1440
    return 15

def seconds_to_candle_close(tf_min):
    """Segundos até o fechamento da próxima vela (alinhado ao horário UTC)."""
    interval = tf_min * 60
    elapsed = time.time() % interval
    return interval - elapsed

COINS = [
    # ── Mega caps ────────────────────────────────────────────────────────────
    ("BTCUSDT","BTC/USDT","BTC"),("ETHUSDT","ETH/USDT","ETH"),
    ("BNBUSDT","BNB/USDT","BNB"),("XRPUSDT","XRP/USDT","XRP"),
    ("TRXUSDT","TRX/USDT","TRX"),("ADAUSDT","ADA/USDT","ADA"),
    # ── L1 — alta volatilidade e tendências limpas ────────────────────────
    ("SOLUSDT","SOL/USDT","SOL"),("AVAXUSDT","AVAX/USDT","AVAX"),
    ("SUIUSDT","SUI/USDT","SUI"),("APTUSDT","APT/USDT","APT"),
    ("NEARUSDT","NEAR/USDT","NEAR"),("TONUSDT","TON/USDT","TON"),
    ("SEIUSDT","SEI/USDT","SEI"),("TIAUSDT","TIA/USDT","TIA"),
    ("ALGOUSDT","ALGO/USDT","ALGO"),("VETUSDT","VET/USDT","VET"),
    ("HBARUSDT","HBAR/USDT","HBAR"),("STXUSDT","STX/USDT","STX"),
    ("ICPUSDT","ICP/USDT","ICP"),("XLMUSDT","XLM/USDT","XLM"),
    ("KASUSDT","KAS/USDT","KAS"),("EGLDUSDT","EGLD/USDT","EGLD"),
    ("FLOWUSDT","FLOW/USDT","FLOW"),("CFXUSDT","CFX/USDT","CFX"),
    # ── DeFi / infra ─────────────────────────────────────────────────────
    ("LINKUSDT","LINK/USDT","LINK"),("INJUSDT","INJ/USDT","INJ"),
    ("JUPUSDT","JUP/USDT","JUP"),("ARBUSDT","ARB/USDT","ARB"),
    ("OPUSDT","OP/USDT","OP"),("UNIUSDT","UNI/USDT","UNI"),
    ("AAVEUSDT","AAVE/USDT","AAVE"),("ENAUSDT","ENA/USDT","ENA"),
    ("ONDOUSDT","ONDO/USDT","ONDO"),("GRTUSDT","GRT/USDT","GRT"),
    ("LDOUSDT","LDO/USDT","LDO"),("RUNEUSDT","RUNE/USDT","RUNE"),
    ("PENDLEUSDT","PENDLE/USDT","PENDLE"),("CAKEUSDT","CAKE/USDT","CAKE"),
    ("CRVUSDT","CRV/USDT","CRV"),("DYDXUSDT","DYDX/USDT","DYDX"),
    ("SNXUSDT","SNX/USDT","SNX"),("GMXUSDT","GMX/USDT","GMX"),
    ("COMPUSDT","COMP/USDT","COMP"),("STGUSDT","STG/USDT","STG"),
    # ── IA / narrativa ───────────────────────────────────────────────────
    ("FETUSDT","FET/USDT","FET"),("TAOUSDT","TAO/USDT","TAO"),
    ("RENDERUSDT","RENDER/USDT","RENDER"),("WLDUSDT","WLD/USDT","WLD"),
    ("IMXUSDT","IMX/USDT","IMX"),("EIGENUSDT","EIGEN/USDT","EIGEN"),
    # ── Meme coins com alta liquidez ─────────────────────────────────────
    ("DOGEUSDT","DOGE/USDT","DOGE"),("PEPEUSDT","PEPE/USDT","PEPE"),
    ("WIFUSDT","WIF/USDT","WIF"),("SHIBUSDT","SHIB/USDT","SHIB"),
    ("FLOKIUSDT","FLOKI/USDT","FLOKI"),("BONKUSDT","BONK/USDT","BONK"),
    ("NOTUSDT","NOT/USDT","NOT"),("POPCATUSDT","POPCAT/USDT","POPCAT"),
    ("DOGSUSDT","DOGS/USDT","DOGS"),("TURBOUSDT","TURBO/USDT","TURBO"),
    ("MEWUSDT","MEW/USDT","MEW"),("BOMEUSDT","BOME/USDT","BOME"),
    # ── High beta estabelecidos ───────────────────────────────────────────
    ("DOTUSDT","DOT/USDT","DOT"),("ATOMUSDT","ATOM/USDT","ATOM"),
    ("LTCUSDT","LTC/USDT","LTC"),("FILUSDT","FIL/USDT","FIL"),
    ("ARUSDT","AR/USDT","AR"),("BCHUSDT","BCH/USDT","BCH"),
    ("ETCUSDT","ETC/USDT","ETC"),("XTZUSDT","XTZ/USDT","XTZ"),
    ("QNTUSDT","QNT/USDT","QNT"),("BATUSDT","BAT/USDT","BAT"),
    # ── L2 / interop ─────────────────────────────────────────────────────
    ("STRKUSDT","STRK/USDT","STRK"),("ZETAUSDT","ZETA/USDT","ZETA"),
    ("PYTHUSDT","PYTH/USDT","PYTH"),("WUSDT","W/USDT","W"),
    ("ZKUSDT","ZK/USDT","ZK"),("MNTUSDT","MNT/USDT","MNT"),
    ("ZROUSDT","ZRO/USDT","ZRO"),("SAGAUSDT","SAGA/USDT","SAGA"),
    ("BLURUSDT","BLUR/USDT","BLUR"),("ORDIUSDT","ORDI/USDT","ORDI"),
    # ── Gaming / metaverso ───────────────────────────────────────────────
    ("AXSUSDT","AXS/USDT","AXS"),("SANDUSDT","SAND/USDT","SAND"),
    ("MANAUSDT","MANA/USDT","MANA"),("GALAUSDT","GALA/USDT","GALA"),
    ("CHZUSDT","CHZ/USDT","CHZ"),("APEUSDT","APE/USDT","APE"),
    ("YGGUSDT","YGG/USDT","YGG"),("MAGICUSDT","MAGIC/USDT","MAGIC"),
    # ── DePIN / outros ───────────────────────────────────────────────────
    ("IOUSDT","IO/USDT","IO"),("ROSEUSDT","ROSE/USDT","ROSE"),
    ("IOTXUSDT","IOTX/USDT","IOTX"),("CELOUSDT","CELO/USDT","CELO"),
    ("JASMYUSDT","JASMY/USDT","JASMY"),("LPTUSDT","LPT/USDT","LPT"),
    ("AEVOUSDT","AEVO/USDT","AEVO"),("BERAUSDT","BERA/USDT","BERA"),
    ("LISTAUSDT","LISTA/USDT","LISTA"),("REZUSDT","REZ/USDT","REZ"),
    # ── L1 adicionais ────────────────────────────────────────────────────────
    ("FTMUSDT","FTM/USDT","FTM"),("KAVAUSDT","KAVA/USDT","KAVA"),
    ("THETAUSDT","THETA/USDT","THETA"),("ONTUSDT","ONT/USDT","ONT"),
    ("ZILLUSDT","ZIL/USDT","ZIL"),("BANDUSDT","BAND/USDT","BAND"),
    ("IOTAUSDT","IOTA/USDT","IOTA"),("MINAUSDT","MINA/USDT","MINA"),
    ("MANTAUSDT","MANTA/USDT","MANTA"),("KSMUSDT","KSM/USDT","KSM"),
    ("QTUMUSDT","QTUM/USDT","QTUM"),("WAVESUSDT","WAVES/USDT","WAVES"),
    ("IOSTUSDT","IOST/USDT","IOST"),("NKNUSDT","NKN/USDT","NKN"),
    ("CTSIUSDT","CTSI/USDT","CTSI"),("COTIUSDT","COTI/USDT","COTI"),
    ("LSKUSDT","LSK/USDT","LSK"),("ZENUSDT","ZEN/USDT","ZEN"),
    ("POWRUSDT","POWR/USDT","POWR"),("SCRTUSDT","SCRT/USDT","SCRT"),
    ("ACAUSDT","ACA/USDT","ACA"),("POLUSDT","POL/USDT","POL"),
    ("CKBUSDT","CKB/USDT","CKB"),("KLAYUSDT","KLAY/USDT","KLAY"),
    ("XDCUSDT","XDC/USDT","XDC"),("NEOUSDT","NEO/USDT","NEO"),
    ("XEMUSDT","XEM/USDT","XEM"),("WAXPUSDT","WAXP/USDT","WAXP"),
    ("HNTUSDT","HNT/USDT","HNT"),("OSMUSDT","OSMO/USDT","OSMO"),
    # ── DeFi adicionais ──────────────────────────────────────────────────────
    ("MKRUSDT","MKR/USDT","MKR"),("SUSHIUSDT","SUSHI/USDT","SUSHI"),
    ("BALUSDT","BAL/USDT","BAL"),("LRCUSDT","LRC/USDT","LRC"),
    ("ANKRUSDT","ANKR/USDT","ANKR"),("CELRUSDT","CELR/USDT","CELR"),
    ("YFIUSDT","YFI/USDT","YFI"),("OCEANUSDT","OCEAN/USDT","OCEAN"),
    ("KNCUSDT","KNC/USDT","KNC"),("ZRXUSDT","ZRX/USDT","ZRX"),
    ("PERPUSDT","PERP/USDT","PERP"),("RSRUSDT","RSR/USDT","RSR"),
    ("FXSUSDT","FXS/USDT","FXS"),("ETHFIUSDT","ETHFI/USDT","ETHFI"),
    ("ALPACAUSDT","ALPACA/USDT","ALPACA"),("REQUSDT","REQ/USDT","REQ"),
    ("OMUSDT","OM/USDT","OM"),("ALICEUSDT","ALICE/USDT","ALICE"),
    ("SPELLUSDT","SPELL/USDT","SPELL"),("RENUSDT","REN/USDT","REN"),
    ("CVXUSDT","CVX/USDT","CVX"),("LITUSDT","LIT/USDT","LIT"),
    ("AMPUSDT","AMP/USDT","AMP"),("OXTUSDT","OXT/USDT","OXT"),
    ("FORTHUSDT","FORTH/USDT","FORTH"),("GLMUSDT","GLM/USDT","GLM"),
    ("AGLDUSDT","AGLD/USDT","AGLD"),("RAREUSDT","RARE/USDT","RARE"),
    ("BONDUSDT","BOND/USDT","BOND"),("WOOUSDT","WOO/USDT","WOO"),
    ("BNTUSDT","BNT/USDT","BNT"),("LQTYUSDT","LQTY/USDT","LQTY"),
    # ── IA / dados adicionais ─────────────────────────────────────────────
    ("AGIXUSDT","AGIX/USDT","AGIX"),("PHBUSDT","PHB/USDT","PHB"),
    ("ARKMUSDT","ARKM/USDT","ARKM"),("NMRUSDT","NMR/USDT","NMR"),
    ("AIUSDT","AI/USDT","AI"),("MOVRUSDT","MOVR/USDT","MOVR"),
    ("GLMRUSDT","GLMR/USDT","GLMR"),("TRBUSDT","TRB/USDT","TRB"),
    ("ENSUSDT","ENS/USDT","ENS"),("AUDIOUSDT","AUDIO/USDT","AUDIO"),
    ("RIFUSDT","RIF/USDT","RIF"),("CTXCUSDT","CTXC/USDT","CTXC"),
    # ── L2 / Rollup adicionais ────────────────────────────────────────────
    ("METISUSDT","METIS/USDT","METIS"),("ALTUSDT","ALT/USDT","ALT"),
    ("XAIUSDT","XAI/USDT","XAI"),("DYMAUSDT","DYMA/USDT","DYMA"),
    ("BEAMUSDT","BEAM/USDT","BEAM"),("POLYXUSDT","POLYX/USDT","POLYX"),
    ("STPTUSDT","STPT/USDT","STPT"),("PORTAUSDT","PORTAL/USDT","PORTAL"),
    ("OMNIUSDT","OMNI/USDT","OMNI"),("IDUSDT","ID/USDT","ID"),
    ("AXLUSDT","AXL/USDT","AXL"),("SYNUSDT","SYN/USDT","SYN"),
    ("ASTRUSDT","ASTR/USDT","ASTR"),("SXPUSDT","SXP/USDT","SXP"),
    # ── Gaming / NFT adicionais ───────────────────────────────────────────
    ("ILVUSDT","ILV/USDT","ILV"),("RONUSDT","RON/USDT","RON"),
    ("PIXELUSDT","PIXEL/USDT","PIXEL"),("MBOXUSDT","MBOX/USDT","MBOX"),
    ("SLPUSDT","SLP/USDT","SLP"),("DARUSDT","DAR/USDT","DAR"),
    ("VOXELUSDT","VOXEL/USDT","VOXEL"),("TLMUSDT","TLM/USDT","TLM"),
    ("NFPUSDT","NFP/USDT","NFP"),("HIGHUSDT","HIGH/USDT","HIGH"),
    ("RDNTUSDT","RDNT/USDT","RDNT"),("WINUSDT","WIN/USDT","WIN"),
    ("DEGOUSDT","DEGO/USDT","DEGO"),("LAZIOUSDT","LAZIO/USDT","LAZIO"),
    ("SANTOSUSDT","SANTOS/USDT","SANTOS"),("GMTUSDT","GMT/USDT","GMT"),
    ("ATMUSDT","ATM/USDT","ATM"),("CITYUSDT","CITY/USDT","CITY"),
    # ── Meme / trending ───────────────────────────────────────────────────
    ("TRUMPUSDT","TRUMP/USDT","TRUMP"),("MOODENGUSDT","MOODENG/USDT","MOODENG"),
    ("NEIROUSDT","NEIRO/USDT","NEIRO"),("BRETTUSDT","BRETT/USDT","BRETT"),
    ("CATIUSDT","CATI/USDT","CATI"),("HMSTRUSDT","HMSTR/USDT","HMSTR"),
    ("ACTUSDT","ACT/USDT","ACT"),("GOATUSDT","GOAT/USDT","GOAT"),
    ("PNUTUSDT","PNUT/USDT","PNUT"),("COWUSDT","COW/USDT","COW"),
    ("GALUSDT","GAL/USDT","GAL"),("OGNUSDT","OGN/USDT","OGN"),
    ("PEOPLEUSDT","PEOPLE/USDT","PEOPLE"),("LUNCUSDT","LUNC/USDT","LUNC"),
    ("USTCUSDT","USTC/USDT","USTC"),("ALPHAUSDT","ALPHA/USDT","ALPHA"),
    # ── Infra / DePIN adicionais ──────────────────────────────────────────
    ("STORJUSDT","STORJ/USDT","STORJ"),("SCUSDT","SC/USDT","SC"),
    ("RVNUSDT","RVN/USDT","RVN"),("HOTUSDT","HOT/USDT","HOT"),
    ("DUSKUSDT","DUSK/USDT","DUSK"),("ENJUSDT","ENJ/USDT","ENJ"),
    ("NEXOUSDT","NEXO/USDT","NEXO"),("TFUELUSDT","TFUEL/USDT","TFUEL"),
    ("SUNUSDT","SUN/USDT","SUN"),("NULSUSDT","NULS/USDT","NULS"),
    ("FUNUSDT","FUN/USDT","FUN"),("CVCUSDT","CVC/USDT","CVC"),
    ("TRUUSDT","TRU/USDT","TRU"),("TWTUSDT","TWT/USDT","TWT"),
    ("DEXEUSDT","DEXE/USDT","DEXE"),("HOOKUSDT","HOOK/USDT","HOOK"),
    ("MTLUSDT","MTL/USDT","MTL"),("ACHUSDT","ACH/USDT","ACH"),
    ("PONDUSDT","POND/USDT","POND"),("KEYUSDT","KEY/USDT","KEY"),
    # ── Narrativas emergentes ─────────────────────────────────────────────
    ("HYPEUSDT","HYPE/USDT","HYPE"),("VIRTUALUSDT","VIRTUAL/USDT","VIRTUAL"),
    ("MOVEUSDT","MOVE/USDT","MOVE"),("GRASSUSDT","GRASS/USDT","GRASS"),
    ("SOLVUSDT","SOLV/USDT","SOLV"),("UXLINKUSDT","UXLINK/USDT","UXLINK"),
    ("KERNELUSDT","KERNEL/USDT","KERNEL"),("MLNUSDT","MLN/USDT","MLN"),
    ("BANANAUSDT","BANANA/USDT","BANANA"),("SPECUSDT","SPEC/USDT","SPEC"),
    # ── Alts médio cap ────────────────────────────────────────────────────
    ("ARPAUSDT","ARPA/USDT","ARPA"),("STEEMUSDT","STEEM/USDT","STEEM"),
    ("SYSUSDT","SYS/USDT","SYS"),("BAKEUSDT","BAKE/USDT","BAKE"),
    ("DODOUSDT","DODO/USDT","DODO"),("WINGUSDT","WING/USDT","WING"),
    ("XVSUSDT","XVS/USDT","XVS"),("SFPUSDT","SFP/USDT","SFP"),
    ("PROSUSDT","PROS/USDT","PROS"),("HARDUSDT","HARD/USDT","HARD"),
    ("QUICKUSDT","QUICK/USDT","QUICK"),("KDAUSDT","KDA/USDT","KDA"),
    ("BICOUSDT","BICO/USDT","BICO"),("REEFUSDT","REEF/USDT","REEF"),
    ("EPXUSDT","EPX/USDT","EPX"),("MBLUSDT","MBL/USDT","MBL"),
    ("ATAUSDT","ATA/USDT","ATA"),("MULTIUSDT","MULTI/USDT","MULTI"),
    ("GTCUSDT","GTC/USDT","GTC"),("HIVEUSDT","HIVE/USDT","HIVE"),
    ("RAYUSDT","RAY/USDT","RAY"),("ORCAUSDT","ORCA/USDT","ORCA"),
    ("JITOUSDT","JITO/USDT","JITO"),("WEMIXUSDT","WEMIX/USDT","WEMIX"),
    ("FIDAUSDT","FIDA/USDT","FIDA"),("SWEATUSDT","SWEAT/USDT","SWEAT"),
    ("CLVUSDT","CLV/USDT","CLV"),("UMAUSDT","UMA/USDT","UMA"),
    ("DIAUSDT","DIA/USDT","DIA"),("LINAUSDT","LINA/USDT","LINA"),
    ("ORNUSDT","ORN/USDT","ORN"),("IDEXUSDT","IDEX/USDT","IDEX"),
    ("TVKUSDT","TVK/USDT","TVK"),("COSUSDT","COS/USDT","COS"),
    ("LTOUSDT","LTO/USDT","LTO"),("KP3RUSDT","KP3R/USDT","KP3R"),
    ("MCUSDT","MC/USDT","MC"),("ACMUSDT","ACM/USDT","ACM"),
    ("JUVUSDT","JUV/USDT","JUV"),("FLMUSDT","FLM/USDT","FLM"),
    ("APEXUSDT","APEX/USDT","APEX"),("BSVUSDT","BSV/USDT","BSV"),
    ("AMBUSDT","AMB/USDT","AMB"),("HFTUSDT","HFT/USDT","HFT"),
    ("IRISUSDT","IRIS/USDT","IRIS"),("MDXUSDT","MDX/USDT","MDX"),
    # ── Watchlist usuário ─────────────────────────────────────────────────
    ("IRYSUSDT","IRYS/USDT","IRYS"),("ASTERUSDT","ASTER/USDT","ASTER"),
    ("PENGUUSDT","PENGU/USDT","PENGU"),("EPICUSDT","EPIC/USDT","EPIC"),
    ("HOMEUSDT","HOME/USDT","HOME"),
]

# ── INDICADORES ──────────────────────────────────────────────────────────────

def ema_series(arr, p):
    k = 2.0/(p+1); out=[arr[0]]
    for v in arr[1:]: out.append(v*k+out[-1]*(1-k))
    return out

def rma_series(arr, p):
    out=[sum(arr[:p])/p]
    for v in arr[p:]: out.append((out[-1]*(p-1)+v)/p)
    return out

def alma_series(src, length=50, offset=0.85, sigma=6):
    """Arnaud Legoux Moving Average — idêntico ao ta.alma() do Pine Script."""
    import math
    n = len(src)
    m = math.floor(offset * (length - 1))
    s = length / sigma
    w = [math.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(length)]
    w_sum = sum(w)
    out = [float('nan')] * (length - 1)
    for i in range(length - 1, n):
        val = sum(w[j] * src[i - length + 1 + j] for j in range(length)) / w_sum
        out.append(val)
    return out

def kalman_filter(src, length, R=0.01, Q=0.1):
    est=src[0]; err=1.0; out=[]
    for s in src:
        em=R*length; gain=err/(err+em)
        est=est+gain*(s-est); err=(1-gain)*err+Q/length
        out.append(est)
    return out

def atr_series(candles, p=14):
    trs=[candles[0]["h"]-candles[0]["l"]]
    for i in range(1,len(candles)):
        h,l,pc=candles[i]["h"],candles[i]["l"],candles[i-1]["c"]
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    rma=rma_series(trs,p)
    return [trs[0]]*(p)+rma[1:]

def rsi_calc(closes, p=14):
    gains=[0.0]; losses=[0.0]
    for i in range(1,len(closes)):
        d=closes[i]-closes[i-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains[1:p+1])/p; al=sum(losses[1:p+1])/p
    for i in range(p+1,len(closes)):
        ag=(ag*(p-1)+gains[i])/p; al=(al*(p-1)+losses[i])/p
    return 100.0 if al==0 else 100-(100/(1+ag/al))

def macd_calc(closes, f=12, s=26, sig=9):
    ea=ema_series(closes,f); eb=ema_series(closes,s)
    ml=[a-b for a,b in zip(ea,eb)]
    sl=ema_series(ml,sig); hist=[m-s for m,s in zip(ml,sl)]
    return ml[-1],sl[-1],hist[-1],hist[-2] if len(hist)>1 else hist[-1],hist[-3] if len(hist)>2 else hist[-1]

def dmi_adx(candles, p=14, smooth=14):
    pdm,mdm,tr=[],[],[]
    for i in range(1,len(candles)):
        h,l=candles[i]["h"],candles[i]["l"]
        ph,pl,pc=candles[i-1]["h"],candles[i-1]["l"],candles[i-1]["c"]
        up,dn=h-ph,pl-l
        pdm.append(up if up>dn and up>0 else 0)
        mdm.append(dn if dn>up and dn>0 else 0)
        tr.append(max(h-l,abs(h-pc),abs(l-pc)))
    rtr=rma_series(tr,p); rpdm=rma_series(pdm,p); rmdm=rma_series(mdm,p)
    dx=[]
    for i in range(len(rtr)):
        t=rtr[i] or 1e-10
        pdi=(rpdm[i]/t)*100; mdi=(rmdm[i]/t)*100
        dx.append(abs(pdi-mdi)/(pdi+mdi or 1)*100)
    adx_arr=rma_series(dx,smooth)
    idx=len(adx_arr)-1
    t=rtr[idx] or 1e-10
    pdi=(rpdm[idx]/t)*100; mdi=(rmdm[idx]/t)*100
    return pdi,mdi,adx_arr[idx],adx_arr[idx-1] if idx>0 else adx_arr[idx]

def ha_series(candles):
    """Heikin-Ashi: open é a média do HA candle anterior (não do candle real)."""
    ha=[]
    for i,c in enumerate(candles):
        hc=(c["o"]+c["h"]+c["l"]+c["c"])/4
        ho=(c["o"]+c["c"])/2 if i==0 else (ha[-1]["o"]+ha[-1]["c"])/2
        ha.append({"o":ho,"h":max(c["h"],ho,hc),"l":min(c["l"],ho,hc),"c":hc})
    return ha

def bb_calc(closes, p=20, mult=2.0):
    """Bollinger Bands: retorna upper, lower, basis, bandwidth atual e anterior."""
    def _bw(data):
        b=sum(data)/p; s=math.sqrt(sum((c-b)**2 for c in data)/p)
        return (2*mult*s)/(b or 1e-10), b+mult*s, b-mult*s, b
    bw,upper,lower,basis=_bw(closes[-p:])
    bw_prev,_,_,_=_bw(closes[-(p+1):-1]) if len(closes)>=p+1 else (bw,0,0,0)
    return upper,lower,basis,bw,bw_prev

def obv_calc(closes, vols):
    """On-Balance Volume: fluxo acumulado de volume."""
    obv=[0.0]
    for i in range(1,len(closes)):
        if closes[i]>closes[i-1]: obv.append(obv[-1]+vols[i])
        elif closes[i]<closes[i-1]: obv.append(obv[-1]-vols[i])
        else: obv.append(obv[-1])
    return obv

def vwap_calc(candles, period=20):
    """VWAP sobre as últimas N velas."""
    sl=candles[-period:]
    vp=sum((c["h"]+c["l"]+c["c"])/3*c["v"] for c in sl)
    tv=sum(c["v"] for c in sl)
    return vp/tv if tv>0 else sl[-1]["c"]

def fmt_price(price):
    if price<0.0001: return f"{price:.7f}"
    if price<0.01: return f"{price:.5f}"
    if price<1: return f"{price:.4f}"
    if price<100: return f"{price:.3f}"
    return f"{price:,.2f}"

# ── ANÁLISE ───────────────────────────────────────────────────────────────────

def analyze(sym, candles):
    n=len(candles)
    if n<60: return None
    # Heikin Ashi como base — suaviza indicadores e reduz ruído falso
    ha_raw=ha_series(candles)
    closes=[c["c"] for c in ha_raw]   # HA close (EMAs, RSI, MACD, Kalman, BB)
    highs =[c["h"] for c in ha_raw]   # HA high
    lows  =[c["l"] for c in ha_raw]   # HA low
    opens =[c["o"] for c in ha_raw]   # HA open
    vols  =[c["v"] for c in candles]  # volume real
    price =candles[-1]["c"]           # preço real (entrada / stop / TP)

    # EMAs (com valores anteriores para detecção de cruzamento)
    e10_arr=ema_series(closes,10); e10=e10_arr[-1]; e10_p=e10_arr[-2]
    e21_arr=ema_series(closes,21); e21=e21_arr[-1]; e21_p=e21_arr[-2]
    e50_arr=ema_series(closes,50); e50=e50_arr[-1]; e50_p=e50_arr[-2]
    e200a=ema_series(closes,200); e200=e200a[-1]; e200p=e200a[-4] if n>4 else e200
    price_p=closes[-2]

    # ATR
    atr_arr=atr_series(candles,14); atr=max(atr_arr[-1],1e-10)

    # Kalman (com aceleração: spread crescendo = momentum se fortalecendo)
    ks=kalman_filter(closes,50); kl=kalman_filter(closes,150)
    kalman_up=ks[-1]>kl[-1]; kalman_down=ks[-1]<kl[-1]
    kalman_spread=ks[-1]-kl[-1]; kalman_spread_p=ks[-2]-kl[-2]
    kalman_accel_up=kalman_spread>kalman_spread_p>0
    kalman_accel_down=kalman_spread<kalman_spread_p<0
    k_short_rising  = ks[-1] > ks[-2]   # Kalman curto subindo (Pine: short_rising)
    k_short_falling = ks[-1] < ks[-2]   # Kalman curto caindo  (Pine: short_falling)

    # MACD (bull3/bear3 = 3 barras consecutivas para ELITE; recovering para early)
    ml,sl_v,hist,hist_p,hist_pp=macd_calc(closes)
    macd_bull=ml>sl_v and hist>hist_p and hist>0
    macd_bear=ml<sl_v and hist<hist_p and hist<0
    macd_bull3=macd_bull and hist_p>hist_pp        # 3 barras crescentes (sinal mais limpo)
    macd_bear3=macd_bear and hist_p<hist_pp        # 3 barras decrescentes
    macd_recovering=hist>hist_p                    # histograma subindo (para early long)
    macd_exhausting=hist<hist_p                    # histograma caindo (para early short)

    # Heikin-Ashi: corpo mínimo (0.2 ATR) filtra dojis e candles fracos
    ha_body_ok = abs(closes[-1] - opens[-1]) > atr * 0.2
    ha_bull  = closes[-1]>opens[-1] and closes[-2]>opens[-2] and ha_body_ok
    ha_bear  = closes[-1]<opens[-1] and closes[-2]<opens[-2] and ha_body_ok
    # 3 candles HA consecutivos — confirmação mais forte para ELITE
    ha_bull3 = ha_bull and closes[-3]>opens[-3]
    ha_bear3 = ha_bear and closes[-3]<opens[-3]

    # RSI (elite usa zona mais estreita + momentum direcional)
    rsi=rsi_calc(closes[-50:])
    rsi_prev=rsi_calc(closes[-53:-3]) if n>=53 else rsi
    rsi_rising=rsi>rsi_prev; rsi_falling=rsi<rsi_prev
    # RSI histórico para detecção de rebound (6 e 9 candles atrás)
    rsi_6 = rsi_calc(closes[-56:-6]) if n >= 56 else rsi
    rsi_9 = rsi_calc(closes[-59:-9]) if n >= 59 else rsi
    # REBOUND SHORT: RSI deu dip abaixo de 35 recentemente + voltou para 38-46
    rsi_dipped_short   = rsi_prev < 35 or rsi_6 < 35 or rsi_9 < 35
    rsi_rebounded_short = 38 <= rsi <= 46 and rsi > rsi_prev
    # REBOUND LONG: RSI subiu acima de 65 recentemente + recuou para 54-62
    rsi_spiked_long    = rsi_prev > 65 or rsi_6 > 65 or rsi_9 > 65
    rsi_rebounded_long  = 54 <= rsi <= 62 and rsi < rsi_prev
    # Divergências RSI
    rsi_div_bull = closes[-1]<closes[-4] and rsi>rsi_prev and rsi<45   # fundo mais baixo no preço, mais alto no RSI
    rsi_div_bear = closes[-1]>closes[-4] and rsi<rsi_prev and rsi>55   # topo mais alto no preço, mais baixo no RSI
    rsi_bull=50<rsi<65; rsi_bear=35<rsi<50              # score: zona saudável bull/bear
    rsi_bull_elite=48<rsi<65 and rsi_rising              # ELITE: abaixo de overbought + subindo
    rsi_bear_elite=35<rsi<52 and rsi_falling             # ELITE: acima de oversold + caindo

    # DMI/ADX (strictly rising: ADX deve estar subindo, não apenas estável)
    pdi,mdi,adx,adx_p=dmi_adx(candles[-60:])
    adx_long_ok=adx>22 and pdi>mdi and adx>adx_p
    adx_short_ok=adx>22 and mdi>pdi and adx>adx_p

    # Volume — RVOL 4 tiers institucionais (1.2/1.5/2.0/3.0)
    # vol_ma exclui a vela atual (pode ser parcial em 15m) — usa 20 velas completas
    vol_ma=sum(vols[-21:-1])/20 if len(vols)>=21 else sum(vols[:-1])/max(len(vols)-1,1)
    rvol       = vols[-1] / max(vol_ma, 1e-10)
    rvol_tier  = (4 if rvol >= 3.0 else 3 if rvol >= 2.0 else
                  2 if rvol >= 1.5 else 1 if rvol >= 1.2 else 0)
    rvol_label = ("INST" if rvol_tier==4 else "VSTRONG" if rvol_tier==3 else
                  "STRONG" if rvol_tier==2 else "GOOD" if rvol_tier==1 else "LOW")
    v_good   = rvol_tier >= 1   # 1.2x+
    v_strong = rvol_tier >= 2   # 1.5x+  (Strong)
    v_inst   = rvol_tier >= 4   # 3.0x+  (institucional)
    v_strong2= v_strong and vols[-2] > vol_ma * 0.9

    # Flow
    flow_raw=[((c["c"]-c["o"])/max(c["h"]-c["l"],1e-10))*c["v"] for c in candles]
    flow_ema=ema_series(flow_raw,13); flow=flow_ema[-1]
    flow_sma=sum(abs(f) for f in flow_ema[-20:])/20
    f_bull=flow>0; f_bear=flow<0; f_strong=abs(flow)>flow_sma*1.2
    # Pressão compradora/vendedora + DNA Flow Institucional (MACD + pressão + v_good)
    mid_body      = (highs[-1] + lows[-1]) / 2
    bull_press    = price > mid_body
    bear_press    = price < mid_body
    dna_flow_bull = macd_bull and bull_press and v_good
    dna_flow_bear = macd_bear and bear_press and v_good

    # Bollinger Bands
    bb_upper,bb_lower,bb_basis,bb_bw,bb_bw_prev=bb_calc(closes)
    bb_squeeze=bb_bw<bb_bw_prev*0.95   # banda contraindo
    bb_expand=bb_bw>bb_bw_prev*1.02    # banda expandindo (breakout)
    bb_break_long  = price > bb_upper  # quebra acima da banda (Pine Script)
    bb_break_short = price < bb_lower  # quebra abaixo da banda (Pine Script)

    # OBV — fluxo acumulado de volume
    obv=obv_calc(closes,vols)
    obv_ema=ema_series(obv,20)
    obv_bull=obv[-1]>obv_ema[-1] and obv[-1]>obv[-6]
    obv_bear=obv[-1]<obv_ema[-1] and obv[-1]<obv[-6]

    # VWAP — suporte/resistência dinâmica por volume
    vwap=vwap_calc(candles)
    above_vwap=price>vwap; below_vwap=price<vwap

    # Tendência
    trend_bull=price>e200 and e10>e21 and e21>e50 and e50>e200
    trend_bear=price<e200 and e10<e21 and e21<e50 and e50<e200
    align_bull=price>e10 and price>e21 and price>e50
    align_bear=price<e10 and price<e21 and price<e50
    e200_rising=e200>e200p; e200_falling=e200<e200p
    strong_trend=abs(e21-e50)/atr>0.6

    not_ext_long=(price-e50)/atr<4.0
    not_ext_short=(e50-price)/atr<4.0

    # ── ANTI-TOPO / ANTI-FUNDO ───────────────────────────────────────────────
    bb_range=max(bb_upper-bb_lower,1e-10)
    price_bb_pos=(price-bb_lower)/bb_range

    # Só bloqueia se literalmente no topo/fundo da banda (>97% ou <3%)
    near_bb_top=price_bb_pos>0.97   # acima da banda superior — sobrecomprado na BB
    near_bb_bot=price_bb_pos<0.03   # abaixo da banda inferior — sobrevendido na BB

    # Preço muito esticado (>3 ATR da EMA21) — movimento já foi feito
    ext_above_ema21=(price-e21)/atr>3.0
    ext_below_ema21=(e21-price)/atr>3.0

    # Volume secando: volume atual < 40% da média E < 50% das últimas 3 velas
    vol3=[vols[-4],vols[-3],vols[-2]]
    vol_drying=vols[-1]<vol_ma*0.4 and vols[-1]<min(vol3)*0.5

    # Pullback: preço tocou EMA10 ou EMA21 nas últimas 5 velas e já voltou acima
    def _low_touched_ema(ema_arr, n=5):
        return any(lows[i]<=ema_arr[i]*1.015 for i in range(-n,-1))
    def _high_touched_ema(ema_arr, n=5):
        return any(highs[i]>=ema_arr[i]*0.985 for i in range(-n,-1))

    pullback_bull=(_low_touched_ema(e10_arr) or _low_touched_ema(e21_arr)) and price>e10 and price>opens[-1] and ha_bull
    pullback_bear=(_high_touched_ema(e10_arr) or _high_touched_ema(e21_arr)) and price<e10 and price<opens[-1] and ha_bear

    # Candle de exaustão: sombra superior > 40% do range → possível reversão no topo
    uwick_ratio=(highs[-1]-max(opens[-1],price))/max(highs[-1]-lows[-1],1e-10)
    lwick_ratio=(min(opens[-1],price)-lows[-1])/max(highs[-1]-lows[-1],1e-10)
    exhaustion_top=uwick_ratio>0.40 and price<(highs[-1]-bb_range*0.02)  # rejeição no topo
    exhaustion_bot=lwick_ratio>0.40 and price>(lows[-1]+bb_range*0.02)    # rejeição no fundo

    # Consistência de tendência: 4 das últimas 5 velas acima/abaixo da EMA21
    bulls_5=sum(1 for i in range(-5,0) if closes[i]>e21_arr[i])
    trend_consistent_bull=bulls_5>=4
    trend_consistent_bear=bulls_5<=1

    bull_impulse=price>highs[-2] and price>opens[-1] and (price-opens[-1])>atr*0.2
    bear_impulse=price<lows[-2] and price<opens[-1] and (opens[-1]-price)>atr*0.2
    liq_long=lows[-1]<lows[-2] and price>lows[-2] and price>opens[-1]
    liq_short=highs[-1]>highs[-2] and price<highs[-2] and price<opens[-1]
    # Smart Money — varredura de liquidez institucional (Pine Script: sweep de 20 velas)
    sm_swing_h = max(highs[-21:-1])
    sm_swing_l = min(lows[-21:-1])
    liq_top    = ((highs[-2] >= sm_swing_h or highs[-1] >= sm_swing_h) and
                  closes[-1] < sm_swing_h and
                  (highs[-1] - closes[-1]) > atr * 0.2)
    liq_bot    = ((lows[-2] <= sm_swing_l or lows[-1] <= sm_swing_l) and
                  closes[-1] > sm_swing_l and
                  (closes[-1] - lows[-1]) > atr * 0.2)
    sm_bull    = liq_bot and ha_bull and (dna_flow_bull or f_bull)
    sm_bear    = liq_top and ha_bear and (dna_flow_bear or f_bear)

    crange=highs[-1]-lows[-1]
    lwick=min(opens[-1],price)-lows[-1]
    uwick=highs[-1]-max(opens[-1],price)
    bull_absorb=crange>0 and lwick>crange*0.45 and price>(lows[-1]+crange*0.6) and vols[-1]>vol_ma
    bear_absorb=crange>0 and uwick>crange*0.45 and price<(highs[-1]-crange*0.6) and vols[-1]>vol_ma

    sell_exhaust=hist<hist_p and hist_p<hist_pp and price<e21 and price<e50 and price<e200
    buy_exhaust=hist>hist_p and hist_p>hist_pp and price>e21 and price>e50 and price>e200

    # Cruzamentos de médias móveis
    cross_10_21_bull=e10_p<=e21_p and e10>e21   # EMA10 cruzou acima da EMA21
    cross_10_21_bear=e10_p>=e21_p and e10<e21   # EMA10 cruzou abaixo da EMA21
    cross_21_50_bull=e21_p<=e50_p and e21>e50   # EMA21 cruzou acima da EMA50
    cross_21_50_bear=e21_p>=e50_p and e21<e50   # EMA21 cruzou abaixo da EMA50
    px_e50_bull=price_p<=e50_p and price>e50     # Preço cruzou acima da EMA50
    px_e50_bear=price_p>=e50_p and price<e50     # Preço cruzou abaixo da EMA50

    any_cross_bull=cross_10_21_bull or cross_21_50_bull or px_e50_bull
    any_cross_bear=cross_10_21_bear or cross_21_50_bear or px_e50_bear

    # Label do cruzamento (mais significativo tem prioridade)
    if cross_21_50_bull: cross_label="EMA21 > EMA50"
    elif px_e50_bull: cross_label="Preco > EMA50"
    elif cross_10_21_bull: cross_label="EMA10 > EMA21"
    elif cross_21_50_bear: cross_label="EMA21 < EMA50"
    elif px_e50_bear: cross_label="Preco < EMA50"
    elif cross_10_21_bear: cross_label="EMA10 < EMA21"
    else: cross_label=""

    # Swing levels — 12 velas = estrutura mais sólida, stop abaixo de wicks reais
    swing_low=min(lows[-13:-1]); swing_high=max(highs[-13:-1])

    # ── TRENDILO (ALMA do % de variação + bandas RMS) ─────────────────────────
    pch = [0.0] + [(closes[i]-closes[i-1])/closes[i]*100 for i in range(1,n)]
    avpch = alma_series(pch, 50, 0.85, 6)
    # RMS rolling dos últimos 50 valores de avpch
    import math as _math
    rms_vals = [_math.sqrt(sum(v*v for v in avpch[max(0,i-49):i+1])/min(i+1,50))
                for i in range(len(avpch))]
    trendilo_long  = not _math.isnan(avpch[-1]) and avpch[-1] > rms_vals[-1]
    trendilo_short = not _math.isnan(avpch[-1]) and avpch[-1] < -rms_vals[-1]

    # Score (capped ±145)
    score=(
        (35 if trend_bull else -35 if trend_bear else 0)+
        (15 if f_bull else -15 if f_bear else 0)+
        (10 if f_strong else 0)+
        (20 if macd_bull else -20 if macd_bear else 0)+
        (20 if adx>30 else 10 if adx>22 else 0)+
        (10 if v_strong else -5)+
        (10 if rsi_bull else -10 if rsi_bear else 0)+
        (10 if e200_rising else -10 if e200_falling else 0)+
        (10 if kalman_up else -10 if kalman_down else 0)+
        (15 if obv_bull else -15 if obv_bear else 0)+
        (5 if above_vwap else -5)+
        (10 if ha_bull else -10 if ha_bear else 0)+
        (5 if kalman_accel_up else -5 if kalman_accel_down else 0)+
        (5 if trend_consistent_bull else -5 if trend_consistent_bear else 0)+
        (10 if trendilo_long else -10 if trendilo_short else 0)
    )
    score=max(-145,min(145,score))
    # Score institucional 0–100 por direção (espelha Pine Script DNA FLOW ELITE)
    def _isc(htf_ok, adx_ok_d, flow_d, ha_d, trl_d, rsi_d, v_s, div_d, sm_d):
        return max(0, min(100,
            (20 if htf_ok else 0) + (15 if adx_ok_d else 0) + (15 if flow_d else 0) +
            (10 if ha_d else 0) + (10 if trl_d else 0) + (10 if rsi_d else 0) +
            (10 if v_s else 0) + (5 if div_d else 0) + (5 if sm_d else 0)
        ))
    inst_score_long  = _isc(trend_bull, adx_long_ok,
                            dna_flow_bull or (f_bull and bull_press),
                            ha_bull, trendilo_long, rsi_rising,
                            v_strong, rsi_div_bull, sm_bull)
    inst_score_short = _isc(trend_bear, adx_short_ok,
                            dna_flow_bear or (f_bear and bear_press),
                            ha_bear, trendilo_short, rsi_falling,
                            v_strong, rsi_div_bear, sm_bear)
    def inst_class(s): return "ELITE" if s>=85 else "FORTE" if s>=70 else "MÉDIO" if s>=55 else "FRACO"
    inst_cls_long  = inst_class(inst_score_long)
    inst_cls_short = inst_class(inst_score_short)
    # Evitar compra no topo (RSI≥65) e venda no fundo extremo (RSI≤25)
    rsi_not_top    = rsi < 65   # LONG: não entrar sobrecomprado (65 = início de breakout)
    rsi_not_bottom = rsi > 30   # SHORT: bloquear fundo extremo (sobrevendido clássico)
    safe_long  = not near_bb_top and not ext_above_ema21 and not vol_drying and not exhaustion_top and rsi_not_top
    safe_short = not near_bb_bot and not ext_below_ema21 and not vol_drying and not exhaustion_bot and rsi_not_bottom

    # ── SINAIS ELITE ── (máxima assertividade: todos os filtros de qualidade)
    long_elite=(strong_trend and trend_bull and align_bull and e200_rising and
                macd_bull3 and ha_bull3 and f_bull and f_strong and adx_long_ok and
                rsi_bull_elite and (v_strong2 or obv_bull) and not_ext_long and
                kalman_accel_up and above_vwap and trend_consistent_bull and
                (bull_impulse or liq_long) and score>65 and safe_long)
    short_elite=(strong_trend and trend_bear and align_bear and e200_falling and
                 macd_bear3 and ha_bear3 and f_bear and f_strong and adx_short_ok and
                 rsi_bear_elite and (v_strong2 or obv_bear) and not_ext_short and
                 kalman_accel_down and below_vwap and trend_consistent_bear and
                 (bear_impulse or liq_short) and score<-65 and safe_short)
    early_long=(adx_long_ok and (v_strong or obv_bull) and sell_exhaust and liq_long and
                bull_absorb and f_bull and trend_bull and e200_rising and
                kalman_up and above_vwap and macd_recovering and safe_long)
    early_short=(adx_short_ok and (v_strong or obv_bear) and buy_exhaust and liq_short and
                 bear_absorb and f_bear and trend_bear and e200_falling and
                 kalman_down and below_vwap and macd_exhausting and safe_short)

    # Sinal de cruzamento (não está no Pine — mantém trendilo + safe como guards)
    long_cross=(any_cross_bull and dna_flow_bull and adx_long_ok and
                price>e200 and inst_score_long>=50 and
                safe_long and (trendilo_long or kalman_up))
    short_cross=(any_cross_bear and dna_flow_bear and adx_short_ok and
                 price<e200 and inst_score_short>=50 and
                 safe_short and (trendilo_short or not kalman_up))

    # ── SINAL PULLBACK (Pine: close<e21*1.02 + flow_bull + adx_long_ok + trl_bull + score>=55)
    trend_bull_relaxed=price>e200 and e10>e21 and e21>e50
    long_pullback=(pullback_bull and trend_bull_relaxed and price<e21*1.03 and
                   dna_flow_bull and adx>18 and pdi>mdi and rsi<65 and
                   inst_score_long>=50 and safe_long and trendilo_long)
    trend_bear_relaxed=price<e200 and e10<e21 and e21<e50
    short_pullback=(pullback_bear and trend_bear_relaxed and price>e21*0.97 and
                    dna_flow_bear and adx>18 and mdi>pdi and rsi>43 and
                    inst_score_short>=50 and safe_short and trendilo_short)

    # ── SINAIS FLEX ── lógica idêntica à versão HTML que gera sinais ────────────
    # MACD relaxado: direção (linha acima/abaixo do sinal) OU histograma acelerando 2 barras
    # Inclui consolidação em tendência (ml>sl com hist↓ = pullback válido em uptrend)
    macd_bull_r = (ml > sl_v) or (hist > hist_p and hist_p > hist_pp)
    macd_bear_r = (ml < sl_v) or (hist < hist_p and hist_p < hist_pp)
    # Volume: 2 velas consecutivas com bom volume (mais sólido)
    vol_avg=vols[-1]>vol_ma*1.1 and vols[-2]>vol_ma*0.9
    # Tendência relaxada: sem exigir e50>e200
    tbull_r=price>e200 and e10>e21 and e21>e50
    tbear_r=price<e200 and e10<e21 and e21<e50
    # Tendência ainda mais relaxada: só exige EMAs alinhadas (sem EMA200)
    tbull_loose=e10>e21 and e21>e50
    tbear_loose=e10<e21 and e21<e50

    # Score FLEX: sem bônus artificial — score real deve atingir o threshold
    flex_score = score

    # ── FILTROS INSTITUCIONAIS ─────────────────────────────────────────────────
    # sideways: squeeze+ADX<18 = sem direção confirmada; FLEX exige ADX>17 sem squeeze
    # com ADX 20-24 onde bb_squeeze acidental bloqueava scores +140
    sideways = bb_squeeze and adx < 18
    not_ext_long_tight  = (price - e21) / atr < 2.5 and rsi < 65   # teto 65: início de breakout
    not_ext_short_tight = (e21 - price) / atr < 2.5 and rsi > 43   # piso 43: não shortar já fraco

    # ── ANTI-PUMP / ANTI-DUMP / RSI VELOCITY ──────────────────────────────────
    # Evita entrar em ativo esticado >25% das últimas 48 velas (raw price, não HA)
    raw_c48 = [c["c"] for c in candles[-50:-1]]
    not_overextended_long  = (price - min(raw_c48)) / max(min(raw_c48), 1e-10) < 0.25
    not_overextended_short = (max(raw_c48) - price) / max(max(raw_c48), 1e-10) < 0.25
    # RSI velocity: bloqueia se RSI correu >18pts em ~3 velas (chasing)
    rsi_not_chasing_long  = (rsi - rsi_prev) < 18
    rsi_not_chasing_short = (rsi_prev - rsi) < 18
    # Volume não em fade: vela atual deve ser ≥50% da MA20 de volume
    vol_not_fade = vols[-1] >= vol_ma * 0.50

    # volume OK: spike claro OU OBV confirmando acumulação/distribuição
    vol_ok = v_strong or obv_bull
    vol_ok_s = v_strong or obv_bear

    # Confirmação HA: vela HA atual (corpo ≥30% do range) — 1 candle é suficiente com todos os outros gates
    ha_bull2 = ha_bull and ha_body_ok   # usa HA real (não raw), 1 vela
    ha_bear2 = ha_bear and ha_body_ok

    # Trendilo + OBV juntos = acumulação real confirmada — aceita RVOL levemente abaixo 1.2x
    flex_vol_ok   = v_good or (obv_bull and trendilo_long)
    flex_vol_ok_s = v_good or (obv_bear and trendilo_short)
    # DNA flow relaxado para FLEX: usa macd_bull_r (direção) em vez de macd_bull (estrito)
    dna_flex_bull = (macd_bull_r and bull_press and v_good) or dna_flow_bull
    dna_flex_bear = (macd_bear_r and bear_press and v_good) or dna_flow_bear

    long_flex = (flex_score > 38 and ha_bull2 and macd_bull_r and adx >= 14 and
                 not sideways and not_ext_long_tight and safe_long and flex_vol_ok and
                 vol_not_fade and rvol >= 0.5 and not_overextended_long and rsi_not_chasing_long and
                 (trendilo_long or kalman_up) and
                 (dna_flex_bull or trendilo_long))
    short_flex = (flex_score < -38 and ha_bear2 and macd_bear_r and adx >= 14 and
                  not sideways and not_ext_short_tight and safe_short and flex_vol_ok_s and
                  vol_not_fade and rvol >= 0.5 and not_overextended_short and rsi_not_chasing_short and
                  (trendilo_short or not kalman_up) and
                  (dna_flex_bear or trendilo_short))

    # ── SETUP — acumulação OBV + MACD em recuperação antecipada (antes dos outros dispararem)
    # Cenário: MACD ainda não cruzou positivo mas histograma JÁ está subindo (recuperação)
    # + OBV acumulando + acima do VWAP = dinheiro entrando antes da confirmação total
    long_setup  = (score > 50 and ha_bull2 and macd_recovering and adx > 18 and
                   obv_bull and v_good and above_vwap and
                   not sideways and not_ext_long_tight and safe_long and
                   price > e200 and inst_score_long >= 50)
    short_setup = (score < -50 and ha_bear2 and macd_exhausting and adx > 18 and
                   obv_bear and v_good and below_vwap and
                   not sideways and not_ext_short_tight and safe_short and
                   price < e200 and inst_score_short >= 50)

    # ── SCOUT — sinal secundário semi-agressivo: thresholds relaxados, risco 1% ──
    # Captura setups abaixo do FLEX mas com estrutura real. Posição pequena, R:R menor.
    # Condições: score>28 (vs 38 FLEX), ha_bull 1 candle (vs 2), adx≥11 (vs 14),
    # volume relaxado: só vol_not_fade (rvol≥0.6) — sem exigir v_good/obv_bull
    long_scout = (flex_score > 28 and ha_bull and macd_bull_r and adx >= 11 and
                  not sideways and not_ext_long_tight and safe_long and
                  vol_not_fade and not_overextended_long and rsi_not_chasing_long and
                  (dna_flow_bull or trendilo_long or kalman_up))
    short_scout = (flex_score < -28 and ha_bear and macd_bear_r and adx >= 11 and
                   not sideways and not_ext_short_tight and safe_short and
                   vol_not_fade and not_overextended_short and rsi_not_chasing_short and
                   (dna_flow_bear or trendilo_short or not kalman_up))

    # ── SURGE (pump/dump com volume explosivo — captura moves tipo HOME +16%) ────
    # ── SURGE (Pine: rvol_tier>=3 + 4%+ candle + break_h + not bb_break — sem trendilo)
    candle_bull_pct = (price - opens[-1]) / max(opens[-1], 1e-10)
    candle_bear_pct = (opens[-1] - price) / max(opens[-1], 1e-10)
    surge_break_h   = price > max(highs[-11:-1])  # rompeu máxima das últimas 10 velas
    surge_break_l   = price < min(lows[-11:-1])   # rompeu mínima das últimas 10 velas
    long_surge  = (rvol_tier >= 3 and candle_bull_pct > 0.04 and surge_break_h and
                   not bb_break_long and not exhaustion_top and
                   not vol_drying and kalman_up and ha_bull)
    short_surge = (rvol_tier >= 3 and candle_bear_pct > 0.04 and surge_break_l and
                   not bb_break_short and not exhaustion_bot and
                   not vol_drying and kalman_down and ha_bear)

    # ── MOMENTUM (Pine: rsi_fresh + ha_bull + flow_bull + adx>22 + v_strong + trl_bull + score>=70)
    rsi_fresh_long  = rsi_prev < 65 <= rsi < 73   # cruzou 65; teto 73 evita entrada muito sobrecomprada
    rsi_fresh_short = rsi_prev > 35 >= rsi > 32   # cruzou abaixo de 35, piso 32 evita sobrevendido
    # liq_top/liq_bot: SM varreu liquidez no topo/fundo e fechou abaixo/acima — contradiz breakout
    long_momentum  = (rsi_fresh_long  and ha_bull and dna_flow_bull and not liq_top and
                      adx > 22 and v_strong and trendilo_long  and inst_score_long  >= 60)
    short_momentum = (rsi_fresh_short and ha_bear and dna_flow_bear and not liq_bot and
                      adx > 22 and v_strong and trendilo_short and inst_score_short >= 60)

    # ── REBOUND — entrada no pullback pós-sobrevendido/sobrecomprado ─────────────
    # SHORT: RSI deu dip abaixo de 35 nos últimos 9 candles + voltou para 38-46
    # LONG:  RSI subiu acima de 65 nos últimos 9 candles + recuou para 54-62
    long_rebound  = (rsi_spiked_long  and rsi_rebounded_long  and
                     ha_bull and dna_flow_bull and trendilo_long  and
                     adx > 20 and v_good and kalman_up   and
                     not sideways and safe_long  and not_ext_long_tight)
    short_rebound = (rsi_dipped_short and rsi_rebounded_short and
                     ha_bear and dna_flow_bear and trendilo_short and
                     adx > 20 and v_good and not kalman_up and
                     not sideways and safe_short and
                     (e21 - price) / atr < 2.5)

    # ── BB BREAKOUT (Pine Script: Kalman trend + direção + quebra da banda) ──────
    # Entra no breakout acima/abaixo da BB quando Kalman confirma tendência e direção
    # Não exige safe_long/safe_short (estratégia de breakout, não de pullback)
    long_bb_break  = (bb_break_long  and bb_expand and kalman_up   and k_short_rising  and
                      flex_score > 40 and adx >= 15  and not sideways    and
                      not ext_above_ema21 and not vol_drying and rsi < 65)
    short_bb_break = (bb_break_short and bb_expand and kalman_down and k_short_falling  and
                      flex_score < -40 and adx >= 15 and not sideways    and
                      not ext_below_ema21 and not vol_drying and rsi > 46)

    # ── SMART MONEY REVERSAL (Pine: sm_bull + rsi>25 + not rsi_block + score>=60 — sem trendilo)
    long_sm  = (sm_bull and rsi > 25 and rsi < 65 and
                price > e200 and inst_score_long >= 60)
    short_sm = (sm_bear and rsi > 46 and rsi < 75 and
                price < e200 and inst_score_short >= 60)

    # ── DIV (Pine: rsi_div + ha_bull + v_good + not rsi_block — sem trendilo)
    long_div  = (rsi_div_bull and ha_bull and v_good and
                 rsi > 25 and rsi < 65 and not exhaustion_top and
                 inst_score_long >= 55)
    short_div = (rsi_div_bear and ha_bear and v_good and
                 rsi > 46 and rsi < 70 and price < e200 and not exhaustion_bot and
                 inst_score_short >= 55)

    # ── REVERSAL — fundo/topo extremo com estrutura de inversão ──────────────────
    # RSI < 25 → LONG: capitulação + primeiro sinal de reversão estrutural
    # RSI > 75 → SHORT: euforia + rejeição estrutural
    # Não exige score (extremo RSI já é filtro forte) mas exige wick + volume + HA virando
    long_reversal  = (rsi < 30 and ha_bull and v_strong and
                      (liq_bot or bull_absorb) and macd_recovering and not vol_drying and
                      adx > 12 and price > e200 * 0.96 and (dna_flow_bull or obv_bull))
    short_reversal = (rsi > 70 and ha_bear and v_strong and
                      (liq_top or bear_absorb) and macd_exhausting and not vol_drying and
                      adx > 12 and price < e200 * 1.04 and (dna_flow_bear or obv_bear))

    sig=None; sig_source=""
    if SIGNAL_MODE=="ELITE":
        if long_elite or early_long: sig="LONG"; sig_source="ELITE"
        elif short_elite or early_short: sig="SHORT"; sig_source="ELITE"
    else:  # FLEX — pullback > cross > bb_break > sm_sweep > surge > momentum > div > flex > scout
        if long_pullback: sig="LONG"; sig_source="PULLBACK"
        elif short_pullback: sig="SHORT"; sig_source="PULLBACK"
        elif long_cross: sig="LONG"; sig_source=f"CROSS:{cross_label}"
        elif short_cross: sig="SHORT"; sig_source=f"CROSS:{cross_label}"
        elif long_bb_break: sig="LONG"; sig_source="BB_BREAK"
        elif short_bb_break: sig="SHORT"; sig_source="BB_BREAK"
        elif long_sm: sig="LONG"; sig_source="SM_SWEEP"
        elif short_sm: sig="SHORT"; sig_source="SM_SWEEP"
        elif long_reversal: sig="LONG"; sig_source="REVERSAL"
        elif short_reversal: sig="SHORT"; sig_source="REVERSAL"
        elif long_surge: sig="LONG"; sig_source="SURGE"
        elif short_surge: sig="SHORT"; sig_source="SURGE"
        elif long_momentum:  sig="LONG";  sig_source="MOMENTUM"
        elif short_momentum: sig="SHORT"; sig_source="MOMENTUM"
        elif long_rebound:   sig="LONG";  sig_source="REBOUND"
        elif short_rebound:  sig="SHORT"; sig_source="REBOUND"
        elif long_div: sig="LONG"; sig_source="DIV"
        elif short_div: sig="SHORT"; sig_source="DIV"
        elif long_flex: sig="LONG"; sig_source="FLEX"
        elif short_flex: sig="SHORT"; sig_source="FLEX"
        elif long_setup:  sig="LONG";  sig_source="SETUP"
        elif short_setup: sig="SHORT"; sig_source="SETUP"
        elif long_scout:  sig="LONG";  sig_source="SCOUT"
        elif short_scout: sig="SHORT"; sig_source="SCOUT"

    # ── QUALIDADE DO SINAL (S / A / B) ───────────────────────────────────────
    # Conta quantos dos filtros premium estão alinhados
    quality_score = 0
    if sig == "LONG":
        quality_score += 3 if trend_bull else 0
        quality_score += 2 if align_bull else 0
        quality_score += 2 if macd_bull3 else (1 if macd_bull else 0)
        quality_score += 2 if ha_bull else 0
        quality_score += 2 if adx_long_ok else (1 if adx > 15 else 0)
        quality_score += 1 if obv_bull else 0
        quality_score += 1 if above_vwap else 0
        quality_score += 1 if v_strong else 0
        quality_score += 1 if kalman_accel_up else 0
        quality_score += 1 if e200_rising else 0
        quality_score += 1 if f_strong else 0
        quality_score += 1 if trend_consistent_bull else 0
    elif sig == "SHORT":
        quality_score += 3 if trend_bear else 0
        quality_score += 2 if align_bear else 0
        quality_score += 2 if macd_bear3 else (1 if macd_bear else 0)
        quality_score += 2 if ha_bear else 0
        quality_score += 2 if adx_short_ok else (1 if adx > 15 else 0)
        quality_score += 1 if obv_bear else 0
        quality_score += 1 if below_vwap else 0
        quality_score += 1 if v_strong else 0
        quality_score += 1 if kalman_accel_down else 0
        quality_score += 1 if e200_falling else 0
        quality_score += 1 if f_strong else 0
        quality_score += 1 if trend_consistent_bear else 0

    if quality_score >= 14:   signal_grade = "S"   # setup perfeito
    elif quality_score >= 11: signal_grade = "A"   # setup sólido
    elif quality_score >= 6:  signal_grade = "B"   # setup básico
    else:                     signal_grade = "B"

    # Log de diagnóstico detalhado — mostra cada condição do long/short_flex
    if not sig:
        if score > 25:
            b=[]
            if not macd_bull_r: b.append(f"macd_r=F(ml{'>' if ml>sl_v else '<'}sl hist{'↑' if hist>hist_p else '↓'})")
            if not ha_bull:     b.append(f"ha=F({'+' if closes[-1]>opens[-1] else '-'}{'+' if closes[-2]>opens[-2] else '-'})")
            if adx<17:          b.append(f"adx={adx:.1f}<17")
            if sideways:        b.append(f"sideways(bbsq={bb_squeeze} adx={adx:.1f})")
            if not safe_long:   b.append(f"safe_long=F(bbtop={near_bb_top} ext={ext_above_ema21} dry={vol_drying} exh={exhaustion_top})")
            if rsi >= 70: b.append(f"rsi={rsi:.1f} sobrecomprado (≥65)")
            if not not_ext_long_tight: b.append(f"ext={(price-e21)/atr:.1f}ATR rsi={rsi:.0f}")
            bb_info = f"bb_break={'✓' if bb_break_long else f'F(p<={bb_upper:.4f})'} k={'↑' if kalman_up else '↓'} ks={'↑' if k_short_rising else '↓'}"
            b.append(bb_info)
            log.info(f"  LONG-BLOCKED {sym}: score={score:+d} flex={flex_score:+d} | {'; '.join(b) if b else 'FLEX OK mas grade-B?'}")
        elif score < -25:
            b=[]
            if not macd_bear_r: b.append(f"macd_r=F(ml{'<' if ml<sl_v else '>'}sl hist{'↓' if hist<hist_p else '↑'})")
            if not ha_bear:     b.append(f"ha=F({'+' if closes[-1]>opens[-1] else '-'}{'+' if closes[-2]>opens[-2] else '-'})")
            if adx<17:          b.append(f"adx={adx:.1f}<17")
            if sideways:        b.append(f"sideways(bbsq={bb_squeeze} adx={adx:.1f})")
            if not safe_short:  b.append(f"safe_short=F(bbbot={near_bb_bot} ext={ext_below_ema21} dry={vol_drying} exh={exhaustion_bot} rsi={rsi:.0f}≤30={rsi<=30})")
            if rsi <= 35: b.append(f"rsi={rsi:.1f} sobrevendido")
            bb_info = f"bb_break={'✓' if bb_break_short else f'F(p>={bb_lower:.4f})'} k={'↓' if kalman_down else '↑'} ks={'↓' if k_short_falling else '↑'}"
            b.append(bb_info)
            log.info(f"  SHORT-BLOCKED {sym}: score={score:+d} flex={flex_score:+d} | {'; '.join(b) if b else 'FLEX OK mas grade-B?'}")
        else:
            log.info(f"  no-sig {sym}: score={score:+d} insuf")

    return {"price":price,"score":score,"atr":atr,"rsi":rsi,"adx":adx,
            "kalman_up":kalman_up,"trend":"BULL" if trend_bull else "BEAR" if trend_bear else "NEUTRO",
            "sig":sig,"sig_source":sig_source,"swing_low":swing_low,"swing_high":swing_high,
            "ha_bull":ha_bull,"obv_bull":obv_bull,"above_vwap":above_vwap,
            "signal_grade":signal_grade,"quality_score":quality_score,
            "tbull_r":tbull_r,"tbear_r":tbear_r,"tbull_loose":tbull_loose,"tbear_loose":tbear_loose,
            "bb_break_long":bb_break_long,"bb_break_short":bb_break_short,
            "v_strong":v_strong,"obv_bear":obv_bear,
            # Institucional
            "rvol":rvol,"rvol_label":rvol_label,"rvol_tier":rvol_tier,
            "inst_score_long":inst_score_long,"inst_score_short":inst_score_short,
            "inst_cls_long":inst_cls_long,"inst_cls_short":inst_cls_short,
            "liq_bot":liq_bot,"liq_top":liq_top,
            "dna_flow_bull":dna_flow_bull,"dna_flow_bear":dna_flow_bear,
            "dna_flex_bull":dna_flex_bull,"dna_flex_bear":dna_flex_bear,
            "trendilo_long":trendilo_long,"trendilo_short":trendilo_short}

def analyze_mtf_entry(sym, candles_15m, h1_bull, h1_bear):
    """Entrada na 15m dado setup confirmado na 1h.
    Procura pullback até EMA21/EMA50 com bounce — stop no swing da correção."""
    n = len(candles_15m)
    if n < 50: return None
    # Heikin Ashi como base — mesma abordagem do analyze()
    ha_raw = ha_series(candles_15m)
    closes = [c["c"] for c in ha_raw]   # HA close
    highs  = [c["h"] for c in ha_raw]   # HA high
    lows   = [c["l"] for c in ha_raw]   # HA low
    opens  = [c["o"] for c in ha_raw]   # HA open
    vols   = [c["v"] for c in candles_15m]  # volume real
    price  = candles_15m[-1]["c"]           # preço real

    e10_arr = ema_series(closes, 10); e10 = e10_arr[-1]
    e21_arr = ema_series(closes, 21); e21 = e21_arr[-1]
    e50_arr = ema_series(closes, 50); e50 = e50_arr[-1]
    e200_arr = ema_series(closes, 200); e200 = e200_arr[-1]
    atr_arr = atr_series(candles_15m, 14); atr = max(atr_arr[-1], 1e-10)

    ml, sl_v, hist, hist_p, hist_pp_1h = macd_calc(closes)
    macd_bull_r = (ml > sl_v) or (hist > hist_p and hist_p > hist_pp_1h)
    macd_bear_r = (ml < sl_v) or (hist < hist_p and hist_p < hist_pp_1h)

    # HA bull/bear — closes e opens já são HA
    ha_body    = abs(closes[-1] - opens[-1])
    ha_body_ok = ha_body > atr * 0.2
    ha_bull = closes[-1] > opens[-1] and closes[-2] > opens[-2] and ha_body_ok
    ha_bear = closes[-1] < opens[-1] and closes[-2] < opens[-2] and ha_body_ok

    rsi = rsi_calc(closes[-50:])
    vol_ma = sum(vols[-20:]) / 20
    # Volume surge: spike claro no bounce (não só acima da média)
    vol_surge = vols[-1] > vol_ma * 1.2 and vols[-1] >= vols[-2]
    # RVOL 1H — exibido no Telegram (mostra volume real da entrada, não do H4)
    rvol_1h = vols[-1] / max(vol_ma, 1e-10)
    rvol_tier_1h = (4 if rvol_1h >= 3.0 else 3 if rvol_1h >= 2.0 else
                    2 if rvol_1h >= 1.5 else 1 if rvol_1h >= 1.2 else 0)
    rvol_label_1h = ("INST" if rvol_tier_1h==4 else "VSTRONG" if rvol_tier_1h==3 else
                     "STRONG" if rvol_tier_1h==2 else "GOOD" if rvol_tier_1h==1 else "LOW")
    v_good_1h = rvol_tier_1h >= 1

    obv = obv_calc(closes, vols)
    obv_ema = ema_series(obv, 20)
    obv_bull = obv[-1] > obv_ema[-1] and obv[-1] > obv[-6]
    obv_bear = obv[-1] < obv_ema[-1] and obv[-1] < obv[-6]

    _, _, adx, adx_p_mtf = dmi_adx(candles_15m[-60:])
    adx_rising_mtf = adx > adx_p_mtf

    # EMA200 direção: confirma tendência macro no 30m
    e200_rising_mtf  = e200_arr[-1] > e200_arr[-6]
    e200_falling_mtf = e200_arr[-1] < e200_arr[-6]

    # Origem do pullback: preço veio de acima da EMA21 (pullback real, não breakdown)
    came_from_above = any(closes[i] > e21_arr[i] for i in range(-8, -2))
    came_from_below = any(closes[i] < e21_arr[i] for i in range(-8, -2))

    # Alinhamento das EMAs: tendência estrutural confirmada
    ema_aligned_long  = e10 > e21 > e50
    ema_aligned_short = e10 < e21 < e50

    # Mercado lateral: EMAs coladas + ADX fraco = sem direção
    sideways_mtf = abs(e21 - e50) / atr < 0.3 and adx < 22

    # Trendilo: ALMA do % de variação vs bandas RMS — confirma momentum direcional
    import math as _math
    pch_m = [0.0] + [(closes[i]-closes[i-1])/closes[i]*100 for i in range(1, len(closes))]
    avpch_m = alma_series(pch_m, 50, 0.85, 6)
    rms_m = [_math.sqrt(sum(v*v for v in avpch_m[max(0,i-49):i+1])/min(i+1,50))
             for i in range(len(avpch_m))]
    trendilo_long_mtf  = not _math.isnan(avpch_m[-1]) and avpch_m[-1] >  rms_m[-1]
    trendilo_short_mtf = not _math.isnan(avpch_m[-1]) and avpch_m[-1] < -rms_m[-1]

    # Kalman Filter — confirma momentum direcional no 30m
    ks_m = kalman_filter(closes, 50); kl_m = kalman_filter(closes, 150)
    kalman_up_mtf   = ks_m[-1] > kl_m[-1]
    kalman_down_mtf = ks_m[-1] < kl_m[-1]
    ks_spread = ks_m[-1] - kl_m[-1]; ks_spread_p = ks_m[-2] - kl_m[-2]
    kalman_accel_up_mtf = ks_spread > ks_spread_p > 0
    kalman_accel_dn_mtf = ks_spread < ks_spread_p < 0

    # VWAP — suporte/resistência dinâmica por volume
    vwap_mtf      = vwap_calc(candles_15m)
    above_vwap_mtf = price > vwap_mtf
    below_vwap_mtf = price < vwap_mtf

    # Flow (pressão de vela — body-weighted volume)
    flow_raw_m = [((c["c"]-c["o"])/max(c["h"]-c["l"],1e-10))*c["v"] for c in candles_15m]
    flow_ema_m = ema_series(flow_raw_m, 13)
    flow_sma_m = sum(abs(f) for f in flow_ema_m[-20:]) / 20
    f_bull_mtf = flow_ema_m[-1] > 0 and abs(flow_ema_m[-1]) > flow_sma_m * 0.8
    f_bear_mtf = flow_ema_m[-1] < 0 and abs(flow_ema_m[-1]) > flow_sma_m * 0.8

    # Bollinger Bands — não entrar em extremo da banda
    bb_u_m, bb_l_m, _, _, _ = bb_calc(closes)
    bb_pos_m = (price - bb_l_m) / max(bb_u_m - bb_l_m, 1e-10)
    not_bb_top = bb_pos_m < 0.88
    not_bb_bot = bb_pos_m > 0.12

    # Força da tendência: EMA21 suficientemente afastada da EMA50
    trend_strong_mtf = abs(e21 - e50) / atr > 0.35

    # Zona de pullback: entrada só quando preço está próximo da EMA
    near_ema21_long  = abs(price - e21) < atr * 0.9 and price > e200
    near_ema50_long  = abs(price - e50) < atr * 1.2 and price > e200
    near_ema21_short = abs(price - e21) < atr * 0.9 and price < e200
    near_ema50_short = abs(price - e50) < atr * 1.2 and price < e200

    in_pullback_long  = near_ema21_long  or near_ema50_long
    in_pullback_short = near_ema21_short or near_ema50_short

    # Bounce: MACD OU HA (igual ao app HTML) + preço subindo + volume
    bounce_long  = (macd_bull_r or ha_bull) and price > opens[-1] and (vol_surge or obv_bull)
    bounce_short = (macd_bear_r or ha_bear) and price < opens[-1] and (vol_surge or obv_bear)

    # Não perseguir: entrada só perto da EMA, não esticado
    not_chasing_long  = (price - e21) / atr < 1.8
    not_chasing_short = (e21 - price) / atr < 1.8

    # Stop no swing da correção (últimas 12 velas = estrutura mais real)
    swing_low  = min(lows[-13:-1])
    swing_high = max(highs[-13:-1])
    stop_long  = swing_low  - atr * 0.5
    stop_short = swing_high + atr * 0.5

    # Evitar compra no topo (RSI≥65) e venda no fundo extremo (RSI≤25)
    rsi_ok_long  = rsi < 65
    rsi_ok_short = rsi > 43

    sig = None
    if (h1_bull and in_pullback_long and bounce_long and
            adx >= 17 and not sideways_mtf and
            not_chasing_long and rsi_ok_long and ema_aligned_long):
        sig = "LONG"
    elif (h1_bear and in_pullback_short and bounce_short and
              adx >= 17 and not sideways_mtf and
              not_chasing_short and rsi_ok_short and ema_aligned_short):
        sig = "SHORT"

    if not sig:
        return None

    is_long = sig == "LONG"
    stop    = stop_long if is_long else stop_short
    near21  = near_ema21_long if is_long else near_ema21_short

    # Quality score MTF (0–10)
    quality_mtf = 0
    if is_long:
        quality_mtf += 2 if kalman_accel_up_mtf else (1 if kalman_up_mtf else 0)
        quality_mtf += 2 if vol_surge else (1 if vols[-1] > vol_ma else 0)
        quality_mtf += 1 if above_vwap_mtf else 0
        quality_mtf += 1 if f_bull_mtf else 0
        quality_mtf += 1 if obv_bull else 0
        quality_mtf += 1 if trendilo_long_mtf else 0
        quality_mtf += 1 if trend_strong_mtf else 0
    else:
        quality_mtf += 2 if kalman_accel_dn_mtf else (1 if kalman_down_mtf else 0)
        quality_mtf += 2 if vol_surge else (1 if vols[-1] > vol_ma else 0)
        quality_mtf += 1 if below_vwap_mtf else 0
        quality_mtf += 1 if f_bear_mtf else 0
        quality_mtf += 1 if obv_bear else 0
        quality_mtf += 1 if trendilo_short_mtf else 0
        quality_mtf += 1 if trend_strong_mtf else 0
    # max = 9pts: S≥6 (kalman_accel+vol+2extras), A≥4, B abaixo
    grade_mtf = "S" if quality_mtf >= 6 else "A" if quality_mtf >= 4 else "B"

    mid_body_1h = (highs[-1] + lows[-1]) / 2
    return {
        "sig": sig, "sig_source": f"MTF_PULLBACK [1h→30m] EMA{'21' if near21 else '50'}",
        "price": price, "atr": atr,
        "swing_low": swing_low, "swing_high": swing_high,
        "rsi": rsi, "adx": adx, "score": 0,
        "kalman_up": kalman_up_mtf, "trend": "BULL" if is_long else "BEAR",
        "signal_grade": grade_mtf, "quality_score": quality_mtf,
        # RVOL e DNA Flow do H1 (não do H4) para exibição correta no Telegram
        "rvol": rvol_1h, "rvol_label": rvol_label_1h,
        "dna_flow_bull": (ml > sl_v and price > mid_body_1h and v_good_1h),
        "dna_flow_bear": (ml < sl_v and price < mid_body_1h and v_good_1h),
        "trendilo_long": trendilo_long_mtf, "trendilo_short": trendilo_short_mtf,
    }

# ── WHATSAPP (CallMeBot) — só sinais reais, sem diagnósticos ─────────────────

async def send_whatsapp(session, wa_text):
    """Envia mensagem via CallMeBot. WA_PHONE e WA_APIKEY devem estar configurados."""
    if not WA_PHONE or not WA_APIKEY:
        return
    import urllib.parse
    url = (f"https://api.callmebot.com/whatsapp.php"
           f"?phone={WA_PHONE}&text={urllib.parse.quote(wa_text)}&apikey={WA_APIKEY}")
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status == 200:
                log.info("✅ WhatsApp enviado")
            else:
                body = await r.text()
                log.warning(f"⚠️ WhatsApp status {r.status}: {body[:80]}")
    except Exception as e:
        log.warning(f"WhatsApp erro (não crítico): {e}")

# ── WATCHLIST ────────────────────────────────────────────────────────────────

async def send_watchlist(session, tf, watchlist):
    """Mensagem consolidada: moedas próximas de sinal — aviso, não sinal."""
    if not TG_TOKEN or not TG_CHATID or not watchlist: return

    def _tf(t):
        t = t.lower()
        if t.endswith('h'): return f"H{t[:-1]}"
        return t.upper()

    tf_lbl = _tf(tf)
    now    = datetime.now().strftime("%H:%M - %d/%m/%Y")

    def fmt(sh, sc, rsi, adx, df, trl):
        sign = "+" if sc >= 0 else "-"
        dna  = "DNA✅" if df else "DNA-"
        trl2 = "Trl✅" if trl else "Trl-"
        return f"• {sh} {sign}{abs(sc)} | RSI {rsi:.0f} | ADX {adx:.0f} | {dna} {trl2}"

    longs  = [(sh,sc,rsi,adx,df,trl) for d,sh,sc,rsi,adx,df,trl in watchlist if d=="LONG"]
    shorts = [(sh,sc,rsi,adx,df,trl) for d,sh,sc,rsi,adx,df,trl in watchlist if d=="SHORT"]

    lines = [f"📡 SETUP EM FORMACAO | {tf_lbl}\n"]
    if longs:
        lines.append("🟢 Aguardando LONG:")
        lines += [fmt(*e) for e in longs[:5]]
    if shorts:
        if longs: lines.append("")
        lines.append("🔴 Aguardando SHORT:")
        lines += [fmt(*e) for e in shorts[:5]]
    lines += ["", f"⚠️ Aguardar confirmacao - ainda nao e sinal", f"⏰ {now}"]

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with session.post(url, json={"chat_id": TG_CHATID, "text": "\n".join(lines)},
                                timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            if data.get("ok"):
                names = ", ".join(sh for _,sh,*_ in watchlist[:6])
                log.info(f"📡 Watchlist [{tf}]: {len(watchlist)} moedas — {names}")
            else:
                log.warning(f"Watchlist API erro: {data.get('description','?')} — code {data.get('error_code','?')}")
    except Exception as e:
        log.warning(f"Watchlist erro: {e}")

# ── TELEGRAM ─────────────────────────────────────────────────────────────────

async def send_telegram(session, sym, label, short, sig_type, price, atr, score,
                        rsi, adx, trend, kalman_up, swing_low, swing_high,
                        sig_source, tf, signal_grade, extra=None):
    is_long=sig_type=="LONG"
    if extra is None: extra = {}
    rvol_lbl    = extra.get("rvol_label", "")
    rvol_val    = extra.get("rvol", 0.0)
    inst_sc     = extra.get("inst_score", 0)
    inst_cls_v  = extra.get("inst_cls", "")
    dna_flow_ok = extra.get("dna_flow", False)
    trl_ok      = extra.get("trendilo_dir", False)
    liq_event   = extra.get("liq_event", "")
    # ── STOP ADAPTATIVO ──────────────────────────────────────────────────────
    # Multiplicador ATR por tipo de sinal
    stop_atr_mult = (2.0 if sig_source == "SURGE"     else  # breakout: wicks grandes
                     1.2 if sig_source == "SM_SWEEP"  else  # stop hunt: nível + buffer
                     1.8 if sig_source in ("FLEX","SETUP") else  # anti-sweep: mais espaço
                     1.5)                                    # padrão todos os outros

    atr_stop = price - stop_atr_mult * atr if is_long else price + stop_atr_mult * atr

    # Stop estrutural: swing_low/swing_high + buffer 0.3 ATR (anti stop-hunt)
    struct_stop = swing_low - atr * 0.3 if is_long else swing_high + atr * 0.3
    swing_dist  = abs(price - struct_stop)

    # Usar estrutural quando: sinal de tendência/pullback + swing próximo (0.3–2.5 ATR)
    use_struct = (sig_source not in ("SURGE", "BB_BREAK", "MOMENTUM") and
                  atr * 0.3 < swing_dist < atr * 2.5 and
                  (struct_stop < price if is_long else struct_stop > price))

    if use_struct:
        # Anti-sweep: usa o stop MAIS LARGO para sobreviver varreduras de liquidez
        stop = min(atr_stop, struct_stop) if is_long else max(atr_stop, struct_stop)
        stop_label = "Estrutura"
    else:
        stop = atr_stop
        stop_label = f"{stop_atr_mult:.1f} ATR"

    risk = abs(price - stop)
    if risk <= 0: return

    # ── TP POR GRADE + TIPO DE SINAL ─────────────────────────────────────────
    if sig_source == "SCOUT":
        r1, r_final = 1.2, 2.0   # sinal fraco → alvo curto
    elif signal_grade == "S":
        r1, r_final = 2.2, 4.5   # sinal forte → alvo proporcional
    elif signal_grade == "A":
        r1, r_final = 1.8, 3.5   # sinal sólido → alvo médio-alto
    else:
        r1, r_final = 1.5, 2.5   # sinal básico → alvo médio

    # Ajuste fino por tipo de sinal
    if sig_source == "SURGE":
        r1      = max(1.5, r1 - 0.5)           # fechar parcial rápido — fades quickly
        r_final = max(3.0, r_final - 1.0)
    elif sig_source == "DIV":
        r_final = max(2.5, r_final - 0.5)      # divergência = convergência, não extensão

    tp1   = price + risk * r1      if is_long else price - risk * r1
    final = price + risk * r_final if is_long else price - risk * r_final

    # Cálculo de posição: SCOUT=1%, outros por grade (B=2%, A=3%, S=5%)
    risk_pct_grade = RISK_SCOUT if sig_source == "SCOUT" else RISK_BY_GRADE.get(signal_grade, RISK_PCT)
    risk_amount    = CAPITAL * risk_pct_grade
    contracts      = risk_amount / risk if risk > 0 else 0
    pos_value      = contracts * price
    pos_5x         = pos_value / 5

    _stop=stop; _tp1=tp1; _final=final; _r1=r1; _r_final=r_final

    grade_info={
        "S": ("🏆 GRADE S — Setup perfeito",),
        "A": ("⭐ GRADE A — Setup sólido",),
        "B": ("📊 GRADE B — Setup básico",),
    }
    grade_label=grade_info[signal_grade][0]

    def _tf_label(t):
        t = t.lower()
        if t.endswith('d'): return f"D{t[:-1]}"
        if t.endswith('h'): return f"H{t[:-1]}"
        return t.upper()
    tf_label = _tf_label(tf)

    if sig_source.startswith("MTF"):
        mode_tag=f"📡 MTF PULLBACK H4→{tf_label}"; cross_info=""
    elif sig_source=="PULLBACK":
        mode_tag="🎯 DNA PULLBACK"; cross_info=""
    elif sig_source.startswith("CROSS"):
        mode_tag="🔀 DNA CROSS"
        cross_info=sig_source.split(":",1)[1]
    elif sig_source=="SM_SWEEP":
        mode_tag="🏦 SMART MONEY SWEEP"; cross_info=""
    elif sig_source=="SURGE":
        mode_tag="⚡ DNA SURGE"; cross_info=""
    elif sig_source=="MOMENTUM":
        mode_tag="🚀 DNA MOMENTUM"; cross_info=""
    elif sig_source=="REBOUND":
        mode_tag="↩️ RSI REBOUND"; cross_info=""
    elif sig_source=="DIV":
        mode_tag="📐 RSI DIVERGÊNCIA"; cross_info=""
    elif sig_source=="REVERSAL":
        mode_tag="🔄 REVERSÃO EXTREMA"; cross_info=""
    elif sig_source=="SETUP":
        mode_tag="🔭 DNA SETUP"; cross_info=""
    elif sig_source=="SCOUT":
        mode_tag="🔵 DNA SCOUT"; cross_info=""
    elif SIGNAL_MODE=="ELITE":
        mode_tag="🔬 DNA ELITE KALMAN"; cross_info=""
    else:
        mode_tag="⚡ DNA FLEX"; cross_info=""

    def d(v): return f"{v:.6f}" if v<0.01 else f"{v:.4f}" if v<1 else f"{v:.2f}"
    def esc(v):
        # Escape para texto fora de backticks (MarkdownV2)
        s=str(v)
        s=s.replace('\\','\\\\')
        for ch in r"_*[]()~`>#+=|{}.!-": s=s.replace(ch,f"\\{ch}")
        return s
    def raw(v):
        # Dentro de backticks só backslash precisa ser escapado
        return str(v).replace('\\','\\\\')

    now=datetime.now().strftime("%H:%M — %d/%m/%Y")
    k_str="↑" if kalman_up else "↓"
    cross_line=f"📉 Cross: {esc(cross_info)}\n" if cross_info else ""

    rvol_line = (f"📊 RVOL: `{raw(f'{rvol_val:.2f}')}x` {esc(rvol_lbl)}" if rvol_lbl else "")
    flow_line = ("✅" if dna_flow_ok else "—") + " DNA Flow"
    trl_line  = ("✅" if trl_ok else "—") + " Trendilo"
    inst_line = (f"\n🏛 Score Inst: *{esc(str(inst_sc))}/100* {esc(inst_cls_v)}" if inst_sc else "")
    liq_line  = (f"\n🔍 SM: {esc(liq_event)}" if liq_event else "")
    scout_warn = "\n⚠️ _Sinal secundário — risco reduzido \\(1%\\) — semi\\-agressivo_" if sig_source == "SCOUT" else ""

    text=(
        f"🚨 *{esc(mode_tag)} — {sig_type}*\n\n"
        f"{'🟢' if is_long else '🔴'} *{esc(label)}* \\| 🕐 Gráfico: *{esc(tf_label)}*\n"
        f"{cross_line}"
        f"{esc(grade_label)}{inst_line}{liq_line}{scout_warn}\n\n"
        f"💰 Entrada: `${raw(fmt_price(price))}`\n"
        f"🛑 Stop: `${raw(d(stop))}` \\({esc(stop_label)}\\)\n"
        f"🎯 TP1 \\({esc(str(r1))}R\\): `${raw(d(tp1))}` → fechar 50% \\+ mover stop → entrada\n"
        f"🏆 TP Final \\({esc(str(r_final))}R\\): `${raw(d(final))}` → fechar 50%\n\n"
        f"📐 *Gestão de risco \\({esc(str(int(risk_pct_grade*100)))}% de ${raw(f'{CAPITAL:.0f}')}\\)*\n"
        f"  Risco: `${raw(f'{risk_amount:.2f}')}`\n"
        f"  Spot: `{raw(f'{contracts:.4f}')} {raw(short)}` \\(aprox `${raw(f'{pos_value:.2f}')} USDT`\\)\n"
        f"  5x Lev: `${raw(f'{pos_5x:.2f}')} collateral`\n\n"
        f"📊 Score: *{esc(score)}/145* \\| RSI: {esc(f'{rsi:.0f}')} \\| ADX: {esc(f'{adx:.0f}')}\n"
        + (f"{esc(rvol_line)}\n" if rvol_line else "")
        + f"🔬 {esc(flow_line)} \\| {esc(trl_line)}\n"
        + f"📈 Trend: {esc(trend)} \\| Kalman: {esc(k_str)}\n"
        f"⏰ {esc(now)}"
    )
    url=f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with session.post(url,json={"chat_id":TG_CHATID,"text":text,"parse_mode":"MarkdownV2"},
                                timeout=aiohttp.ClientTimeout(total=10)) as r:
            data=await r.json()
            if data.get("ok"):
                log.info(f"✅ {sig_type} {short} Grade:{signal_grade} Score:{score} RSI:{rsi:.0f} ADX:{adx:.0f} [{sig_source}]")
                # ── Trade Journal ───────────────────────────────────────────────
                append_journal(sym, tf, sig_type, price, _stop, _tp1, _final,
                               _r1, _r_final, signal_grade, score, rsi, adx, sig_source)
                # ── WhatsApp — mensagem limpa só com o sinal ────────────────────
                import re as _re
                wa_tipo  = _re.sub(r'[^\w\s\-→/]', '', mode_tag).strip()
                wa_flow  = "✅" if dna_flow_ok else "—"
                wa_trl   = "✅" if trl_ok      else "—"
                wa_rvol  = f"RVOL {rvol_val:.2f}x {rvol_lbl} | " if rvol_lbl else ""
                wa_liq   = f"SM: {liq_event} | " if liq_event else ""
                wa_text  = (
                    f"SINAL {sig_type} — {label} [{_tf_label(tf)}] Grade {signal_grade}\n"
                    f"Tipo: {wa_tipo}\n\n"
                    f"Entrada: ${fmt_price(price)}\n"
                    f"Stop: ${d(_stop)} ({stop_label})\n"
                    f"TP1 ({_r1}R): ${d(_tp1)}\n"
                    f"TP Final ({_r_final}R): ${d(_final)}\n\n"
                    f"Risco ${risk_amount:.2f} | 5x ${pos_5x:.2f} collateral\n"
                    f"RSI {rsi:.0f} | ADX {adx:.0f} | {wa_rvol}"
                    f"DNA Flow {wa_flow} | Trendilo {wa_trl} | {wa_liq}"
                    f"{now}"
                )
                await send_whatsapp(session, wa_text)
            else: log.warning(f"❌ {data.get('description')}")
    except Exception as e: log.error(f"Erro: {e}")

# ── MEXC (formato igual ao Binance, sem bloqueio de IPs cloud) ───────────────
# MEXC usa "60m" em vez de "1h" e "4h" em vez de "4H"
_MEXC_TF={"1h":"60m","2h":"120m","4h":"4h","6h":"6h","8h":"8h","12h":"12h","1d":"1d"}

async def fetch_candles(session, sym, tf, limit=250):
    interval=_MEXC_TF.get(tf,tf)
    url=f"https://api.mexc.com/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}"
    delays=[1,2,4]  # backoff: 1s, 2s, 4s
    for attempt in range(3):
        try:
            async with session.get(url,timeout=aiohttp.ClientTimeout(total=10)) as r:
                status=r.status
                if status==404:
                    log.warning(f"fetch_candles {sym} [{tf}]: HTTP 404 — símbolo não encontrado, ignorando")
                    return None  # don't retry on 404
                if status==429:
                    log.warning(f"fetch_candles {sym} [{tf}]: HTTP 429 — rate limit, aguardando 5s (tentativa {attempt+1}/3)")
                    await asyncio.sleep(5)
                    if attempt<2: continue
                    return None
                data=await r.json()
            if not isinstance(data,list):
                log.warning(f"fetch_candles {sym} [{tf}]: {str(data)[:80]}")
                return None
            if len(data)<60: return None
            return [{"o":float(k[1]),"h":float(k[2]),"l":float(k[3]),"c":float(k[4]),"v":float(k[5])} for k in data]
        except asyncio.TimeoutError:
            wait=delays[attempt] if attempt<len(delays) else delays[-1]
            log.warning(f"fetch_candles {sym} [{tf}]: timeout (tentativa {attempt+1}/3), aguardando {wait}s")
            if attempt<2: await asyncio.sleep(wait)
        except Exception as e:
            wait=delays[attempt] if attempt<len(delays) else delays[-1]
            log.warning(f"fetch_candles {sym} [{tf}]: {e} (tentativa {attempt+1}/3), aguardando {wait}s")
            if attempt<2: await asyncio.sleep(wait)
    log.warning(f"fetch_candles {sym} [{tf}]: falha após 3 tentativas — ignorando")
    return None

def load_state():
    try:
        if STATE_FILE.exists(): return json.loads(STATE_FILE.read_text())
    except: pass
    return {}

def save_state(state):
    try: STATE_FILE.write_text(json.dumps(state))
    except: pass

# ── RASTREADOR DINÂMICO DE MOEDAS ─────────────────────────────────────────────

# Stablecoins e tokens alavancados para excluir
_EXCLUDE = {"USDC","BUSD","TUSD","FDUSD","DAI","USDP","PAXG","WBTC","WETH",
            "EUR","GBP","BRL","UST","USDD","FRAX","USD1","USDE","USDT0",
            "AIXDROP",
            # Moedas FRACO: backtest mostra avg_r negativo ou -1R em todos os trades
            "PENDLE","GIGGLE","USELESS","EDEN","PLAY","MAGMA","CHIP",
            "SLX","JGGL","MYX","SENTIS","XPL","TAO"}
_EXCLUDE_SUB = ("UP","DOWN","BULL","BEAR","3L","3S","2L","2S","5L","5S")

async def fetch_top_usdt_pairs(session, min_vol_m=1.0, max_pairs=400):
    """Busca top pares USDT do MEXC ordenados por volume 24h (USD)."""
    url="https://api.mexc.com/api/v3/ticker/24hr"
    try:
        async with session.get(url,timeout=aiohttp.ClientTimeout(total=15)) as r:
            data=await r.json()
        if not isinstance(data,list): return []
        pairs=[]
        for t in data:
            sym=t["symbol"]
            if not sym.endswith("USDT"): continue
            base=sym[:-4]
            if base in _EXCLUDE: continue
            if any(sub in base for sub in _EXCLUDE_SUB): continue
            try:
                vol=float(t.get("quoteVolume","0"))
                if vol < min_vol_m*1e6: continue
                pairs.append((sym,base,vol))
            except: continue
        pairs.sort(key=lambda x:x[2],reverse=True)
        return pairs[:max_pairs]
    except Exception as e:
        log.warning(f"Scanner: erro ao buscar pares — {e}"); return []

def quick_rank(candles):
    """Score rápido para ranquear moedas candidatas. Retorna 0 se não serve."""
    if len(candles)<60: return 0
    closes=[c["c"] for c in candles]
    vols=[c["v"] for c in candles]
    price=closes[-1]
    # ATR%
    atr=atr_series(candles,14)[-1]
    atr_pct=(atr/price)*100
    if atr_pct<0.25 or atr_pct>4.0: return 0
    # ADX
    try: _,_,adx,_=dmi_adx(candles[-60:])
    except: return 0
    if adx<18: return 0   # sem tendência clara
    # Trend
    e200=ema_series(closes,200)[-1]
    trend_ok=abs(price-e200)/e200>0.01  # preço pelo menos 1% afastado da EMA200
    # Volume crescente
    vol_ma=sum(vols[-20:])/20
    vol_ok=vols[-1]>vol_ma*1.2  # acima da média por margem real
    # Score composto
    atr_ideal=max(0,25-abs(atr_pct-1.5)*8)
    score=adx*0.40 + (20 if trend_ok else 0) + (15 if vol_ok else 0) + atr_ideal
    return score

async def scan_best_coins(session, tf="15m", top_n=20):
    """Varre o mercado e retorna as top_n moedas com melhores condições agora."""
    log.info(f"🔍 Rastreador iniciado — buscando melhores moedas [{tf}]...")
    pairs=await fetch_top_usdt_pairs(session)
    if not pairs:
        log.warning("Rastreador: sem dados, mantendo lista atual"); return None

    # Busca candles em lotes paralelos de 15
    async def _fetch_pair(sym, base, vol_usd):
        try:
            candles = await fetch_candles(session, sym, tf, limit=250)
            if candles:
                s = quick_rank(candles)
                if s > 0:
                    return (sym, f"{base}/USDT", base, s, vol_usd)
        except Exception:
            pass
        return None

    scored = []
    batch_size = 15
    for i in range(0, len(pairs), batch_size):
        batch = pairs[i:i+batch_size]
        results = await asyncio.gather(*[_fetch_pair(sym, base, vol) for sym, base, vol in batch])
        for r in results:
            if r:
                scored.append(r)
                log.info(f"  ✓ {r[2]:8s} | Score {r[3]:.0f} | Vol ${r[4]/1e6:.0f}M")
        if i + batch_size < len(pairs):
            await asyncio.sleep(0.05)

    scored.sort(key=lambda x:x[3],reverse=True)
    top=[(s,l,b) for s,l,b,_,_ in scored[:top_n]]
    if not top: return None

    names=[b for _,_,b in top]
    log.info(f"✅ Top {len(top)} selecionadas: {', '.join(names)}")
    return top

# ── MAIN ──────────────────────────────────────────────────────────────────────

def in_trading_hours():
    """Só opera 09h-13h e 14h-21h no horário de Brasília (BRT = UTC-3)."""
    from datetime import timezone, timedelta
    brt = timezone(timedelta(hours=-3))
    h = datetime.now(brt).hour
    return (9 <= h < 13) or (14 <= h < 21)

async def _fetch_safe(session, sym, tf):
    """Busca candles sem lançar exceção — retorna None em caso de falha."""
    try:
        return await fetch_candles(session, sym, tf)
    except Exception:
        return None

async def _prefetch_batch(session, coins, tf, batch_size=15):
    """Busca candles de todas as moedas em lotes paralelos. Retorna lista alinhada com coins."""
    results = []
    for i in range(0, len(coins), batch_size):
        batch = coins[i:i+batch_size]
        fetched = await asyncio.gather(*[_fetch_safe(session, sym, tf) for sym,_,_ in batch])
        results.extend(fetched)
        if i + batch_size < len(coins):
            await asyncio.sleep(0.05)
    return results

async def run_cycle(session, last_sig, tf, coins):
    """Executa um ciclo completo de análise em todas as moedas para um timeframe."""
    now=time.time(); sent=0
    cooldown=max(tf_to_minutes(tf)*60, 14400)  # mínimo 4h entre sinais por moeda
    candidates=[]  # (abs_score, short, score, rsi, adx, reason)
    watchlist =[]  # (dir, short, score, rsi, adx, dna_flow, trendilo)
    cycle_risk  = 0.0   # risco acumulado no ciclo (teto MAX_CYCLE_RISK)
    scout_sent  = 0     # SCOUTs enviados no ciclo
    longs_sent  = 0     # LONGs enviados (anti-correlação)
    shorts_sent = 0     # SHORTs enviados
    MAX_SIGNALS_PER_CYCLE = 3  # máximo 3 sinais por ciclo

    # Pré-busca paralela de candles (lotes de 15 simultâneos)
    all_candles = await _prefetch_batch(session, coins, tf)

    # H4 direction filter: H1 e 30m usam H4 para confirmar direção
    all_h4_candles = None
    if tf in ("1h", "30m"):
        log.info(f"[{tf}] Buscando H4 de {len(coins)} moedas para filtro de direção...")
        all_h4_candles = await _prefetch_batch(session, coins, "4h")

    def _h4_ok(h4_candles, sig_direction):
        """Retorna True se H4 confirma a direção do sinal H1."""
        if h4_candles is None: return True   # sem H4 → não bloqueia
        r4 = analyze(None, h4_candles)
        if not r4: return True
        h4_rsi  = r4["rsi"]
        h4_vol  = r4.get("v_strong", False) or r4.get("obv_bull", False)
        h4_vols = r4.get("v_strong", False) or r4.get("obv_bear", False)
        h4_bull = (r4["score"] > 15 and r4.get("tbull_r", False) and
                   r4["adx"] >= 13 and h4_rsi < 65 and h4_vol)
        h4_bear = (r4.get("tbear_r", False) and r4["adx"] >= 13 and
                   h4_vols and r4["score"] < -15 and h4_rsi > 43)
        # Só bloqueia se H4 for FORTEMENTE oposto (score < -30 para LONG, > 30 para SHORT)
        if sig_direction == "LONG"  and h4_bear and r4["score"] < -30: return False
        if sig_direction == "SHORT" and h4_bull and r4["score"] >  30: return False
        return True

    for (sym,label,short), candles, h4c in zip(
            coins, all_candles,
            all_h4_candles if all_h4_candles else [None]*len(coins)):
        if sent >= MAX_SIGNALS_PER_CYCLE:
            log.info(f"[{tf}] Limite de {MAX_SIGNALS_PER_CYCLE} sinais por ciclo atingido")
            break
        if not candles: continue
        result=analyze(sym,candles)
        if not result: continue
        grade=result.get("signal_grade","B")

        # ATR% — excluir moedas muito voláteis para $200
        atr_pct=(result["atr"]/result["price"])*100 if result["price"] else 0
        if atr_pct > 4.0:
            log.info(f"[{tf}] {short:7s} | ATR {atr_pct:.1f}% > 4% — muito volátil, ignorando")
            continue

        log.info(f"[{tf}] {short:7s} | Score {result['score']:+4d} | RSI {result['rsi']:5.1f} | ADX {result['adx']:5.1f} | K:{'UP' if result['kalman_up'] else 'DN'} | Grade:{grade} | {result['sig_source'] or result['sig'] or '—'}")
        if result["sig"]:
            # Grade A/S direto; Grade B só passa se score muito alto (≥60)
            if grade == "B" and abs(result["score"]) < 65:
                log.info(f"  ⚠️ {short} Grade B ignorado — score {result['score']:+d} insuficiente")
                candidates.append((abs(result["score"]),short,result["score"],result["rsi"],result["adx"],"grade-B"))
                continue
            # H4 direction filter (H1 apenas)
            if tf == "1h" and not _h4_ok(h4c, result["sig"]):
                log.info(f"  🚫 {short} [{tf}] {result['sig']} bloqueado — H4 oposto à direção H1")
                candidates.append((abs(result["score"]),short,result["score"],result["rsi"],result["adx"],"H4 oposto"))
                continue
            key_dir = f"{sym}_{tf}_{result['sig']}"
            key_any = f"{sym}_{tf}"
            same_dir_blocked = now - last_sig.get(key_dir, 0) < cooldown
            flip_blocked     = now - last_sig.get(key_any, 0) < 7200
            if same_dir_blocked or flip_blocked:
                mins = int((cooldown - (now - last_sig.get(key_dir, 0))) / 60)
                log.info(f"  ⏳ {short} [{tf}] cooldown {mins}min")
                candidates.append((abs(result["score"]),short,result["score"],result["rsi"],result["adx"],"cooldown"))
                continue
            # ── Tetos de segurança ─────────────────────────────────────────────
            _is_long = result["sig"] == "LONG"
            _src     = result.get("sig_source", "")
            _risk_pct = RISK_SCOUT if _src == "SCOUT" else RISK_BY_GRADE.get(grade, RISK_PCT)

            # 1. Teto de risco por ciclo (10%)
            if cycle_risk + _risk_pct > MAX_CYCLE_RISK:
                log.info(f"  🛑 {short} bloqueado — risco ciclo {cycle_risk*100:.0f}%+{_risk_pct*100:.0f}% > {MAX_CYCLE_RISK*100:.0f}%")
                continue
            # 2. SCOUT: máximo 2 por ciclo
            if _src == "SCOUT" and scout_sent >= MAX_SCOUT_PER_CYCLE:
                log.info(f"  🔵 {short} SCOUT bloqueado — limite {MAX_SCOUT_PER_CYCLE}/ciclo atingido")
                continue
            # 3. Correlação: máximo 2 LONGs e 2 SHORTs por ciclo
            if _is_long and longs_sent >= MAX_LONG_PER_CYCLE:
                log.info(f"  📊 {short} LONG bloqueado — {MAX_LONG_PER_CYCLE} LONGs/ciclo atingido (correlação)")
                continue
            if not _is_long and shorts_sent >= MAX_SHORT_PER_CYCLE:
                log.info(f"  📊 {short} SHORT bloqueado — {MAX_SHORT_PER_CYCLE} SHORTs/ciclo atingido (correlação)")
                continue

            last_sig[key_dir] = now
            last_sig[key_any] = now
            cycle_risk  += _risk_pct
            scout_sent  += 1 if _src == "SCOUT" else 0
            longs_sent  += 1 if _is_long else 0
            shorts_sent += 0 if _is_long else 1
            sent += 1
            _extra = {
                "rvol_label":    result.get("rvol_label",""),
                "rvol":          result.get("rvol",0.0),
                "inst_score":    result.get("inst_score_long" if _is_long else "inst_score_short",0),
                "inst_cls":      result.get("inst_cls_long" if _is_long else "inst_cls_short",""),
                "dna_flow":      result.get("dna_flow_bull" if _is_long else "dna_flow_bear",False),
                "trendilo_dir":  result.get("trendilo_long" if _is_long else "trendilo_short",False),
                "liq_event":     ("LIQ BOT ↑" if result.get("liq_bot") else
                                  "LIQ TOP ↓" if result.get("liq_top") else ""),
            }
            await send_telegram(session,sym,label,short,result["sig"],result["price"],
                                result["atr"],result["score"],result["rsi"],result["adx"],
                                result["trend"],result["kalman_up"],
                                result["swing_low"],result["swing_high"],result["sig_source"],tf,grade,
                                extra=_extra)
        else:
            candidates.append((result["score"],short,result["score"],result["rsi"],result["adx"],result.get("sig_source","no-sig")))
            # ── Watchlist: moedas próximas de sinal (sem limite sup — sig=None já filtra)
            _sc=result["score"]; _rsi=result["rsi"]; _adx=result["adx"]
            _df_l=result.get("dna_flex_bull",False); _df_s=result.get("dna_flex_bear",False)
            _trl_l=result.get("trendilo_long",False); _trl_s=result.get("trendilo_short",False)
            _kal=result.get("kalman_up",False)
            # Qualquer coin sem sinal com score e RSI saudáveis + ao menos 1 indicador
            if (_sc > 12 and _rsi < 72 and _adx >= 8 and
                    (_kal or _trl_l or _df_l or _sc > 40)):
                watchlist.append(("LONG",  short, _sc, _rsi, _adx, _df_l, _trl_l))
            elif (_sc < -12 and _rsi > 35 and _adx >= 8 and
                    (not _kal or _trl_s or _df_s or _sc < -40)):
                watchlist.append(("SHORT", short, _sc, _rsi, _adx, _df_s, _trl_s))

    if sent == 0 and candidates:
        # Top LONG: maior score positivo
        top_long  = sorted([c for c in candidates if c[2]>0],  key=lambda x: x[2], reverse=True)[:3]
        # Top SHORT: maior score negativo (mais bearish)
        top_short = sorted([c for c in candidates if c[2]<0],  key=lambda x: x[2])[:3]

        lines = []
        if top_long:
            best_adx_l = max(adx for _,_,_,_,adx,_ in top_long)
            best_sc_l  = top_long[0][2]
            best_rsi_l = top_long[0][3]
            motivo_l   = ("🔴 RSI sobrecomprado" if best_rsi_l >= 65
                          else "📉 ADX baixo"      if best_adx_l < 17
                          else "📊 Score baixo"    if best_sc_l < 50
                          else "⏳ MACD/HA pendente")
            lines.append(f"📈 LONG — {motivo_l}")
            lines += [f"  {sh}: {sc:+d} | RSI {rsi:.0f} | ADX {adx:.0f}" for _,sh,sc,rsi,adx,_ in top_long]
        if top_short:
            best_adx_s = max(adx for _,_,_,_,adx,_ in top_short)
            best_sc_s  = top_short[0][2]
            best_rsi_s = top_short[0][3]
            motivo_s   = ("🔴 RSI sobrevendido" if best_rsi_s <= 40
                          else "📉 ADX baixo"    if best_adx_s < 17
                          else "📊 Score baixo"  if best_sc_s > -50
                          else "⏳ MACD/HA pendente")
            lines.append(f"📉 SHORT — {motivo_s}")
            lines += [f"  {sh}: {sc:+d} | RSI {rsi:.0f} | ADX {adx:.0f}" for _,sh,sc,rsi,adx,_ in top_short]

        if lines:
            log.info(f"[{tf}] Sem sinais — " + " | ".join(lines[:3]))

    # ── Watchlist: envia se houver moedas próximas e cooldown ≥1h vencido
    log.info(f"[{tf}] Watchlist: {len(watchlist)} moedas encontradas")
    if watchlist:
        wl_key = f"_watchlist_{tf}"
        if now - last_sig.get(wl_key, 0) >= 3600:
            await send_watchlist(session, tf, watchlist)
            last_sig[wl_key] = now

    return sent

async def run_mtf_cycle(session, last_sig, coins):
    """Ciclo MTF paralelo: prefetch H4 em lote → filtra → prefetch 1H em lote → sinal."""
    now = time.time()
    sent = 0
    cooldown_mtf = 14400
    setup_coins = []

    # BTC trend + RSI macro — filtro em 4H
    btc_bull_filter = btc_bear_filter = False
    btc_rsi_heat = btc_rsi_panic = False
    btc_p = 0
    btc_candles = await fetch_candles(session, "BTCUSDT", "4h")
    if btc_candles and len(btc_candles) >= 50:
        btc_c = [c["c"] for c in btc_candles]
        btc_e21  = ema_series(btc_c, 21)[-1]
        btc_e50  = ema_series(btc_c, 50)[-1]
        btc_e200 = ema_series(btc_c, 200)[-1]
        btc_p    = btc_c[-1]
        btc_rsi  = rsi_calc(btc_c[-50:])
        btc_bull_filter = btc_p > btc_e21 > btc_e50 and btc_p > btc_e200 * 0.98
        btc_bear_filter = btc_p < btc_e21 < btc_e50 and btc_p < btc_e200 * 1.02
        btc_rsi_heat  = btc_rsi > 72   # BTC sobrecomprado — risco LONG elevado
        btc_rsi_panic = btc_rsi < 28   # BTC sobrevendido  — risco SHORT elevado
        log.info(f"[MTF] BTC 4H: {'BULL ↑' if btc_bull_filter else 'BEAR ↓' if btc_bear_filter else 'NEUTRO'} | RSI {btc_rsi:.0f}{'🔥' if btc_rsi_heat else '🧊' if btc_rsi_panic else ''} | ${btc_p:.0f}")

    # ── PASS 1: prefetch H4 de todas as moedas em paralelo ──────────────────
    log.info(f"[MTF] Prefetch H4 ({len(coins)} moedas)...")
    all_h4 = await _prefetch_batch(session, coins, "4h")

    # Analisa H4 e monta lista de moedas com setup válido
    filtered = []  # (sym, label, short, r4h, h4_bull, h4_bear)
    for (sym, label, short), candles_4h in zip(coins, all_h4):
        if not candles_4h:
            continue
        r4h = analyze(sym, candles_4h)
        if not r4h:
            continue
        h4_rsi   = r4h["rsi"]
        h4_vol   = r4h.get("v_strong", False) or r4h.get("obv_bull", False)
        h4_vol_s = r4h.get("v_strong", False) or r4h.get("obv_bear", False)
        h4_bull  = (r4h["score"] > 15 and r4h.get("tbull_r", False) and
                    r4h["adx"] >= 13 and h4_rsi < 65 and h4_vol)
        h4_bear  = (r4h.get("tbear_r", False) and r4h["adx"] >= 13 and
                    h4_vol_s and r4h["score"] < -15 and h4_rsi > 43)
        if not (h4_bull or h4_bear):
            log.info(f"[MTF] {short:7s} | 4H sem setup | Score {r4h['score']:+d} RSI4H {h4_rsi:.0f}")
            continue
        direction = "BULL" if h4_bull else "BEAR"
        if short not in ("BTC", "WBTC"):
            # BTC trend filter — aplica a TODOS os grades sem exceção
            if h4_bull and btc_bear_filter:
                setup_coins.append((short, direction, r4h["score"], h4_rsi, "BTC em queda"))
                log.info(f"[MTF] {short:7s} | LONG bloqueado — BTC 4H em queda")
                continue
            if h4_bear and btc_bull_filter:
                setup_coins.append((short, direction, r4h["score"], h4_rsi, "BTC em alta"))
                log.info(f"[MTF] {short:7s} | SHORT bloqueado — BTC 4H em alta")
                continue
            # BTC RSI macro filter — mercado superaquecido/em pânico
            if h4_bull and btc_rsi_heat:
                log.info(f"[MTF] {short:7s} | LONG bloqueado — BTC RSI {btc_rsi:.0f} > 72 (sobrecomprado)")
                continue
            if h4_bear and btc_rsi_panic:
                log.info(f"[MTF] {short:7s} | SHORT bloqueado — BTC RSI {btc_rsi:.0f} < 28 (sobrevendido)")
                continue
        log.info(f"[MTF] {short:7s} | 4H {direction} ✓BTC | Score {r4h['score']:+d} → buscando entrada 1H...")
        filtered.append((sym, label, short, r4h, h4_bull, h4_bear))

    if not filtered:
        log.info("[MTF] Nenhuma moeda com setup H4 válido")
    else:
        # ── PASS 2: prefetch 1H apenas das moedas que passaram o H4 ────────
        log.info(f"[MTF] Prefetch 1H ({len(filtered)} moedas com setup H4)...")
        coins_1h = [(sym, label, short) for sym, label, short, _, _, _ in filtered]
        all_1h = await _prefetch_batch(session, coins_1h, "1h")

        for (sym, label, short, r4h, h4_bull, h4_bear), candles_1h in zip(filtered, all_1h):
            h4_rsi    = r4h["rsi"]
            direction = "BULL" if h4_bull else "BEAR"
            if not candles_1h:
                continue
            result = analyze_mtf_entry(sym, candles_1h, h4_bull, h4_bear)
            if not result:
                setup_coins.append((short, direction, r4h["score"], h4_rsi, "pullback 1H pendente"))
                log.info(f"[MTF] {short:7s} | 1H sem entrada (não está no pullback)")
                continue
            mtf_grade   = result.get("signal_grade", "A")
            mtf_quality = result.get("quality_score", 0)
            log.info(f"[MTF] {short:7s} | ✅ 1H {result['sig']} Grade:{mtf_grade} Q:{mtf_quality}/9 | {result['sig_source']} | RSI {result['rsi']:.1f} | ADX {result['adx']:.1f}")
            if mtf_grade == "B":
                setup_coins.append((short, direction, r4h["score"], h4_rsi, "Grade B"))
                log.info(f"[MTF] {short:7s} | Grade B ignorado — setup insuficiente")
                continue
            key = f"{sym}_MTF"
            if now - last_sig.get(key, 0) >= cooldown_mtf:
                last_sig[key] = now
                sent += 1
                _is_long_mtf = result["sig"] == "LONG"
                _extra_mtf = {
                    "rvol_label":   result.get("rvol_label", ""),
                    "rvol":         result.get("rvol", 0.0),
                    "inst_score":   r4h.get("inst_score_long" if _is_long_mtf else "inst_score_short", 0),
                    "inst_cls":     r4h.get("inst_cls_long" if _is_long_mtf else "inst_cls_short", ""),
                    "dna_flow":     result.get("dna_flow_bull" if _is_long_mtf else "dna_flow_bear", False),
                    "trendilo_dir": result.get("trendilo_long" if _is_long_mtf else "trendilo_short", False),
                    "liq_event":    ("LIQ BOT ↑" if r4h.get("liq_bot") else
                                     "LIQ TOP ↓" if r4h.get("liq_top") else ""),
                }
                await send_telegram(session, sym, label, short, result["sig"],
                                    result["price"], result["atr"], r4h["score"],
                                    result["rsi"], result["adx"], result["trend"],
                                    result["kalman_up"],
                                    result["swing_low"], result["swing_high"],
                                    result["sig_source"], "1h", mtf_grade,
                                    extra=_extra_mtf)
            else:
                mins = int((cooldown_mtf - (now - last_sig.get(key, 0))) / 60)
                setup_coins.append((short, direction, r4h["score"], h4_rsi, f"cooldown {mins}min"))
                log.info(f"  ⏳ {short} [MTF] cooldown {mins}min")

    # BTC bear filter ativo — log apenas
    if sent == 0 and btc_bear_filter:
        log.info("🐻 BTC bear — LONGs bloqueados")

    # MTF setups em análise — log apenas
    if sent == 0 and setup_coins:
        log.info(f"[MTF] {len(setup_coins)} setup(s) H4 ativos sem sinal 1H")

    return sent

async def run_test(session):
    """Modo de teste: analisa BTC e SOL em 15m com dados reais e manda sinal forçado."""
    log.info("🧪 TEST MODE — Analisando BTC e SOL em 15m com dados reais...")
    test_coins=[("BTCUSDT","BTC/USDT","BTC"),("SOLUSDT","SOL/USDT","SOL")]
    for sym,label,short in test_coins:
        candles=await fetch_candles(session,sym,"15m")
        if not candles:
            log.warning(f"❌ Sem dados para {short}"); continue
        result=analyze(sym,candles)
        if not result:
            log.warning(f"❌ Análise falhou para {short}"); continue
        grade=result.get("signal_grade","B")
        # Em teste força envio independente de sinal real, usando direção do score
        sig_force="LONG" if result["score"]>=0 else "SHORT"
        sig_src=result["sig_source"] or f"TEST({result['score']:+d})"
        log.info(f"🧪 {short} | Score {result['score']:+d} | Grade {grade} | Enviando sinal {sig_force}...")
        _is_l = sig_force == "LONG"
        _extra_t = {
            "rvol_label":   result.get("rvol_label",""),
            "rvol":         result.get("rvol",0.0),
            "inst_score":   result.get("inst_score_long" if _is_l else "inst_score_short",0),
            "inst_cls":     result.get("inst_cls_long" if _is_l else "inst_cls_short",""),
            "dna_flow":     result.get("dna_flow_bull" if _is_l else "dna_flow_bear",False),
            "trendilo_dir": result.get("trendilo_long" if _is_l else "trendilo_short",False),
            "liq_event":    ("LIQ BOT ↑" if result.get("liq_bot") else
                             "LIQ TOP ↓" if result.get("liq_top") else ""),
        }
        await send_telegram(session,sym,label,short,sig_force,result["price"],
                            result["atr"],result["score"],result["rsi"],result["adx"],
                            result["trend"],result["kalman_up"],
                            result["swing_low"],result["swing_high"],
                            f"TESTE — {sig_src}","15m",grade, extra=_extra_t)
        await asyncio.sleep(1)
    log.info("✅ Teste concluído — verifique o Telegram!")

async def _tg_notify(session, text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with session.post(url, json={"chat_id": TG_CHATID, "text": text},
                                timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            if not data.get("ok"):
                log.warning(f"⚠️ Notificação TG: {data.get('description')}")
    except Exception as e:
        log.warning(f"⚠️ Notificação TG falhou: {e}")

async def main():
    if not TG_TOKEN or not TG_CHATID:
        log.error("❌ Configure TG_TOKEN e TG_CHATID!"); return

    if TEST_MODE:
        log.info("🧪 GAUSS+DNA — MODO TESTE ATIVADO")
        async with aiohttp.ClientSession() as session:
            await run_test(session)
        return


    tf_min_base=min(tf_to_minutes(tf) for tf in TIMEFRAMES)
    scan_tf=TIMEFRAMES[0]
    mode_str="LOOP CONTÍNUO" if LOOP_MODE else "EXECUÇÃO ÚNICA"
    scan_str="DINÂMICO" if DYNAMIC_SCAN else "LISTA FIXA"
    log.info(f"🚀 GAUSS+DNA v2 | {SIGNAL_MODE} | TFs: {','.join(TIMEFRAMES)} | Coins: {scan_str} | {mode_str}")

    log.info("✅ Bot pronto — enviando apenas sinais reais ao Telegram")

    last_sig=load_state()
    cycle=0
    active_coins=list(COINS)
    last_scan_cycle=0

    async with aiohttp.ClientSession() as session:
        # ── Notificação de início ──────────────────────────────────────────────
        now_str = datetime.now().strftime("%H:%M — %d/%m/%Y")
        coins_count = len(COINS)
        await _tg_notify(session,
            f"🤖 GAUSS+DNA iniciado\n"
            f"⏰ {now_str}\n"
            f"📊 TFs: {', '.join(TIMEFRAMES)} | Moedas: {coins_count}\n"
            f"🔄 Modo: {mode_str} | Ciclo: {CYCLE_INTERVAL}s"
        )

        # ── Teste de conectividade — log apenas ──────────────────────────────
        for test_url,label in [
            ("https://api.mexc.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=250","MEXC 15m"),
            ("https://api.mexc.com/api/v3/klines?symbol=BTCUSDT&interval=60m&limit=250","MEXC 60m"),
        ]:
            try:
                async with session.get(test_url,timeout=aiohttp.ClientTimeout(total=8)) as _r:
                    _body=await _r.json()
                    log.info(f"✅ {label}: {len(_body) if isinstance(_body,list) else '?'} velas")
            except Exception as _e:
                log.warning(f"⚠️ {label}: {str(_e)[:60]}")

        # Scanner inicial antes do primeiro ciclo (top 50 para não começar cego)
        if DYNAMIC_SCAN:
            result=await scan_best_coins(session,scan_tf,min(50,SCANNER_TOP))
            if result: active_coins=result
            last_scan_cycle=0

        while True:
            cycle+=1

            if LOOP_MODE and cycle>1:   # ciclo 1 roda imediatamente
                wait=seconds_to_candle_close(tf_min_base)
                if CYCLE_INTERVAL > 0:
                    wait=min(wait, CYCLE_INTERVAL)
                if wait>3:
                    log.info(f"⏳ Próximo ciclo em {wait:.0f}s ({wait/60:.1f}min)...")
                    await asyncio.sleep(wait+2)

            # Rescan periódico (a cada SCAN_EVERY ciclos)
            if DYNAMIC_SCAN and cycle>1 and (cycle-last_scan_cycle)>=SCAN_EVERY:
                result=await scan_best_coins(session,scan_tf,SCANNER_TOP)
                if result: active_coins=result
                last_scan_cycle=cycle

            log.info(f"── Ciclo #{cycle} | {datetime.now().strftime('%H:%M:%S %d/%m')} | {len(active_coins)} moedas ──")
            # MTF (4H→1H ou 1H→30m) + FLEX no timeframe de entrada
            total=0
            try:
                has_mtf = (("4h" in TIMEFRAMES and "1h" in TIMEFRAMES) or
                           ("1h" in TIMEFRAMES and ("30m" in TIMEFRAMES or "15m" in TIMEFRAMES)))
                if has_mtf:
                    sent_mtf = await run_mtf_cycle(session, last_sig, active_coins)
                    total += sent_mtf
            except Exception as e:
                log.error(f"❌ MTF erro ciclo #{cycle}: {e}")
            try:
                # FLEX no timeframe menor (entrada) — HTF coberto pelo MTF
                if "4h" in TIMEFRAMES:
                    base_tf = next((t for t in TIMEFRAMES if t != "4h"), "1h")
                else:
                    base_tf = next((t for t in TIMEFRAMES if t != "1h"), TIMEFRAMES[0])
                sent=await run_cycle(session, last_sig, base_tf, active_coins)
                total+=sent
                save_state(last_sig)
                log.info(f"✅ Ciclo #{cycle} concluído. Sinais: {total}")
            except Exception as e:
                log.error(f"❌ FLEX erro ciclo #{cycle}: {e}")

            if LOOP_MODE and cycle % 5 == 0:
                log.info(f"💓 Ciclo #{cycle} | {len(active_coins)} moedas")

            if not LOOP_MODE:
                break

if __name__=="__main__":
    asyncio.run(main())
