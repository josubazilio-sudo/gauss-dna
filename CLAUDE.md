# GAUSS+DNA — Regras de Prioridade Permanente

## REGRA #1 — RSI: ZONA DE ENTRADA (PRIORIDADE MÁXIMA)

**Nunca remover, relaxar ou criar exceções sem autorização explícita do usuário.**

### LONG (compra):
- RSI deve ser **< 55** no momento do sinal
- Objetivo: entrar quando RSI tem espaço para subir, longe de sobrecomprado

### SHORT (venda):
- RSI deve ser **> 45** no momento do sinal
- Objetivo: entrar quando RSI tem espaço para cair, longe de sobrevendido

### Aplicação:
- Válido para **TODOS** os tipos de sinal: SCOUT, FLEX, BB_BREAK, PULLBACK, CROSS, SM_SWEEP, DIV, SETUP, SURGE, MOMENTUM, REVERSAL, REBOUND
- Exceções únicas já existentes: REVERSAL (exige RSI < 30 para LONG e RSI > 70 para SHORT — zona oposta intencional), MOMENTUM (usa janela rsi_fresh_long/short — entrada no cruzamento de 65)
- Implementado em `analyze.py` como `rsi_zona_long` e `rsi_zona_short`

```python
# analyze.py — NÃO ALTERAR sem autorização
rsi_zona_long  = rsi < 55
rsi_zona_short = rsi > 45
```

---

## REGRA #2 — Volume mínimo para sinais

- `vol_nao_fade` (SCOUT/FLEX): volume ≥ 80% da média (`vol_ma * 0.80`)
- BB_BREAK: RVOL ≥ 0.80 + OBV confirmado
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
- LONG: `not liq_topo` (não entrar após varredura de topo)
- SHORT: `not liq_fundo` (não entrar após varredura de fundo)
- StochRSI: `stoch_esticado_up` = > 0.80 (bloqueia seguro_long)
