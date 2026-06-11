# GAUSS+DNA — Regras de Prioridade Permanente

## REGRA #0 — COMPORTAMENTO DO ASSISTENTE (PRIORIDADE ABSOLUTA)

**Enquanto o bot não disparar sinal: nunca aceitar estado parado. Agir.**

### Quando não há sinal:
1. **Buscar no histórico git** o último estado que estava dando sinais (`git log --oneline`)
2. **Comparar** o estado atual com esse estado e identificar o que mudou
3. **Procurar bloqueadores ocultos** — condições que se contradizem, filtros que bloqueiam o próprio gatilho (ex: `surge_break_h` + `not liq_topo` são contradição)
4. **Analisar o diagnóstico** por moeda: qual candidato está mais próximo e qual filtro específico está impedindo
5. **Propor e aplicar** o ajuste mais cirúrgico possível
6. **Disparar o bot** e aguardar novo diagnóstico
7. **Repetir** até aparecer sinal ou usuário dizer que apareceu

### Parar somente quando:
- Usuário disser explicitamente que o sinal chegou
- Usuário mostrar screenshot do sinal com os dados
- Usuário pedir para parar

### Exceções válidas para não agir:
- Mercado genuinamente em zona morta pós-dump (RSI médio < 32) E todos os candidatos têm 2+ bloqueadores de mercado (não de filtro) — neste caso, informar e aguardar 1 ciclo antes de agir novamente

---

## REGRA #1 — RSI: ZONA DE ENTRADA (PRIORIDADE MÁXIMA)

**Nunca remover, relaxar ou criar exceções sem autorização explícita do usuário.**

### LONG (compra):
- RSI deve ser **< 60** no momento do sinal *(autorizado 10/06 — era 55)*
- Objetivo: entrar com espaço para subir (60 captura sinais fracos pós-dump)

### SHORT (venda):
- RSI deve ser **> 40** no momento do sinal *(autorizado 10/06 — era 45)*
- Objetivo: entrar com espaço para cair (40 captura sinais fracos pós-dump)

### Aplicação:
- Válido para **TODOS** os tipos de sinal: SCOUT, FLEX, BB_BREAK, PULLBACK, CROSS, SM_SWEEP, DIV, SETUP, SURGE, MOMENTUM, REVERSAL, REBOUND
- Exceções já existentes: REVERSAL (RSI < 30 LONG / > 70 SHORT), MOMENTUM (janela rsi_fresh 65/42), SURGE (cap 22/78 — breakouts movem RSI junto)
- Implementado em `analyze.py` como `rsi_zona_long` e `rsi_zona_short`

```python
# analyze.py — autorizado pelo usuário em 10/06 (era 55/45, relaxado 65/35, ajustado 60/40)
rsi_zona_long  = rsi < 60
rsi_zona_short = rsi > 40
```

---

## REGRA #2 — Volume mínimo para sinais

- `vol_nao_fade` (SCOUT): melhor das 2 últimas velas >= 80% da média
- BB_BREAK: RVOL ≥ 0.80 + OBV confirmado
- SURGE: melhor das 2 últimas velas `rvol_tier_max2 >= 3` (3x+)
- Rompimento sem volume = falso rompimento

## REGRA #3 — Sessão perigosa

- 22h–08h UTC (Asian/madrugada): `_inst_min` = 60 (confirmação institucional forte obrigatória)
- 08h e 13h UTC (abertura Londres/NY): mesmo piso de 60 (primeiros 30min de risco)

## REGRA #4 — Alavancagem dinâmica 3x–10x

- Base por grade: S+=10, S=9, A+=8, A=7, B=5
- Modificadores: +1 inst≥80, -1 inst<45, +1 RVOL≥1.2, -1 RVOL<0.80, -2 armadilha
- SCOUT: teto 5x
- Clamp final: min 3x, máx 10x

## REGRA #5 — Defesas SMC (Smart Money)

- SCOUT e BB_BREAK: `adx_subindo` obrigatório
- LONG: `not liq_topo` (não entrar após varredura de topo) — **exceto SURGE** (contradição com surge_break_h)
- SHORT: `not liq_fundo` (não entrar após varredura de fundo) — **exceto SURGE** (contradição com surge_break_l)
- StochRSI: `stoch_esticado_up` = > 0.80 (bloqueia seguro_long)

---

## PONTO DE REFERÊNCIA — Estado funcional (10/06/2026)

Commit: `96f3f20` — estado após correções estruturais do dia 10/06

**Fixes aplicados nesta sessão:**
- SURGE: removido `not liq_topo/liq_fundo` (contradição com surge_break)
- SURGE: removido `rsi_zona_long/short` (breakouts movem RSI — cap 22/78)
- RVOL: lookback 2 velas (`rvol_tier_max2`, `vol_nao_fade` max das 2 últimas)
- MOMENTUM SHORT: janela estendida `rsi_ant > 42 >= rsi > 30`
- Diagnóstico: per-moeda com bloqueador específico, 4 LONG + 4 SHORT
- PRIORITY_WATCHLIST: 26 moedas do bubble escaneadas primeiro
- FLEX: bloqueado quando sem fluxo + tendência neutra
- Cron: 6h → 2h, timeframes fallback 30m → 15m
