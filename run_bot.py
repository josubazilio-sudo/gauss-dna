#!/usr/bin/env python3
"""
GAUSS+DNA — Launcher PC
Configura variaveis de ambiente e inicia o bot automaticamente.
Edite a secao CONFIG abaixo antes de rodar.
"""

import os
import sys
import subprocess

# ═══════════════════════════════════════════════════════════════════════
#  CONFIG — preencha aqui antes de rodar
# ═══════════════════════════════════════════════════════════════════════

TG_TOKEN  = ""          # Token do seu bot Telegram  (obter com @BotFather)
TG_CHATID = ""          # ID do chat/canal          (obter com @userinfobot)

CAPITAL    = "97"        # Capital total em USD
RISK_PCT   = "0.03"      # Risco por trade: 0.03 = 3%
TIMEFRAMES = "30m,1h"    # Timeframes: "30m,1h" | "15m" | "1h"
SIGNAL_MODE = "FLEX"     # "FLEX" (mais sinais) | "ELITE" (poucos, precisos)
LOOP_MODE   = "true"     # "true" = roda em loop continuo | "false" = executa 1x
SCANNER_TOP = "50"       # Quantas moedas varrer (max 100)

# ═══════════════════════════════════════════════════════════════════════

def check_token(name, val):
    if not val or val.strip() == "":
        print(f"\n❌  {name} nao configurado!")
        print(f"   Abra run_bot.py e preencha a variavel {name} na secao CONFIG.\n")
        return False
    return True

def main():
    print("=" * 55)
    print("   GAUSS+DNA Bot — Launcher")
    print("=" * 55)

    if not check_token("TG_TOKEN", TG_TOKEN):
        sys.exit(1)
    if not check_token("TG_CHATID", TG_CHATID):
        sys.exit(1)

    # Configura variaveis de ambiente
    env = os.environ.copy()
    env.update({
        "TG_TOKEN":    TG_TOKEN.strip(),
        "TG_CHATID":   TG_CHATID.strip(),
        "CAPITAL":     CAPITAL,
        "RISK_PCT":    RISK_PCT,
        "TIMEFRAMES":  TIMEFRAMES,
        "TIMEFRAME":   TIMEFRAMES.split(",")[0],
        "SIGNAL_MODE": SIGNAL_MODE,
        "LOOP_MODE":   LOOP_MODE,
        "DYNAMIC_SCAN":"false",
        "SCANNER_TOP": SCANNER_TOP,
        "TEST_MODE":   "false",
    })

    print(f"\n  Capital   : ${CAPITAL}")
    print(f"  Risco/trade: {float(RISK_PCT)*100:.0f}%")
    print(f"  Timeframes : {TIMEFRAMES}")
    print(f"  Modo       : {SIGNAL_MODE}")
    print(f"  Loop       : {'continuo' if LOOP_MODE=='true' else 'unico'}")
    print(f"  Moedas     : top {SCANNER_TOP}")
    print("\n  Iniciando... (Ctrl+C para parar)\n")
    print("=" * 55)

    # Verifica se bot_actions.py existe
    bot_path = os.path.join(os.path.dirname(__file__), "bot_actions.py")
    if not os.path.exists(bot_path):
        print(f"❌  bot_actions.py nao encontrado em: {bot_path}")
        sys.exit(1)

    try:
        subprocess.run(
            [sys.executable, bot_path],
            env=env,
            check=True,
        )
    except KeyboardInterrupt:
        print("\n\n  Bot parado pelo usuario.")
    except subprocess.CalledProcessError as e:
        print(f"\n❌  Bot encerrou com erro: {e.returncode}")
        sys.exit(e.returncode)

if __name__ == "__main__":
    main()
