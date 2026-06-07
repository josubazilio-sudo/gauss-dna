"""
GAUSS+DNA — Entry point
Ponto de entrada do bot. Executado pelo GitHub Actions e pelo run_bot.py.

Módulos:
  config.py      — variáveis de ambiente e constantes
  coins.py       — lista de moedas e filtros do scanner
  indicators.py  — cálculo de indicadores técnicos
  analyze.py     — análise: indicadores → sinais → grade
  notify.py      — envio via Telegram e WhatsApp
  scanner.py     — scanner dinâmico de moedas (MEXC)
  state.py       — persistência de cooldown e journal CSV
  cycles.py      — ciclos de execução e loop principal
"""
import asyncio
import logging
from cycles import main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

if __name__ == "__main__":
    asyncio.run(main())
