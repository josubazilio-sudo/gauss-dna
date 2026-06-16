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

### Após qualquer ajuste de código:
- **Sempre disparar o bot automaticamente** via `mcp__github__actions_run_trigger` com `filter_level=3, timeframes=30m,1h`
- Não pedir confirmação — o disparo pós-ajuste é autorizado permanentemente

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
- RSI deve ser **< 75** no momento do sinal *(FLEX PRO — autorizado 15/06)*
- Objetivo: bloquear apenas extremo sobrecomprado (>75), permite entradas em tendência 55-74

### SHORT (venda):
- RSI deve ser **> 25** no momento do sinal *(FLEX PRO — autorizado 15/06)*
- Objetivo: bloquear apenas extremo sobrevendido (<25), permite entradas em correção 26-40

### Aplicação:
- Válido para **TODOS** os tipos de sinal: SCOUT, FLEX, BB_BREAK, PULLBACK, CROSS, SM_SWEEP, DIV, SETUP, SURGE, MOMENTUM, REVERSAL, REBOUND, **CORE** (própria janela: 45-58 L / 42-55 S)
- Implementado em `analyze.py` como `rsi_zona_long` e `rsi_zona_short`

```python
# analyze.py — FLEX PRO 15/06 (bloqueia apenas extremos absolutos)
rsi_zona_long  = rsi < 75
rsi_zona_short = rsi > 25
```

---

## REGRA #2 — Volume mínimo para sinais

- `vol_nao_fade` (SCOUT/CORE): `max(volumes[-1], volumes[-2]) >= vol_ma * 0.80` (FL=3)
- BB_BREAK: RVOL ≥ 0.80 + OBV confirmado
- SURGE: melhor das 2 últimas velas `rvol_tier_max2 >= 3` (3x+)
- Rompimento sem volume = falso rompimento

## REGRA #3 — Sessão perigosa

- 22h–08h UTC (Asian/madrugada): `_inst_min += 10` (cap 70)
- 08h e 13h UTC (abertura Londres/NY): `_inst_min += 10` (cap 70)

## REGRA #4 — Alavancagem dinâmica 3x–20x

- Base por grade: S+=20, S=16, A+=13, A=10, B=7
- Modificadores: +2 inst≥80, +1 inst≥70, -2 inst<55, +1 RVOL≥1.5, -1 RVOL<0.80
- Tetos por tipo: SCOUT=5x, MOMENTUM=10x, SURGE=12x
- Clamp final: min 3x, máx 20x

## REGRA #5 — Defesas SMC (Smart Money)

- SCOUT e BB_BREAK: `adx_subindo` obrigatório
- LONG: `not liq_topo` (não entrar após varredura de topo) — **exceto SURGE** (contradição com surge_break_h)
- SHORT: `not liq_fundo` (não entrar após varredura de fundo) — **exceto SURGE** (contradição com surge_break_l)
- StochRSI: `stoch_esticado_up` = > 0.80 (bloqueia seguro_long)

---

## PONTO DE REFERÊNCIA — Estado funcional (10/06/2026)

Commit: `96f3f20` — estado após correções estruturais do dia 10/06

---

## SESSÃO 14/06/2026 — Melhorias aplicadas

**Commit base de restauração:** `a7226d8` → refatorado em `de4f1a2` → `12c45b5` → atual

### Correções críticas (14/06):
- RSI zona LONG: 60 → 55 (restaurado — não comprar topo)
- `dump_rsi_spike_short`: removido de `seguro_short` (bloqueava SHORTs válidos como SiREM)
- `pump_rsi_spike_long`: threshold elevado para >15pts E rsi>54 (menos agressivo)
- Score inst por tipo de sinal (não mais fixo 60 para todos)
- Funding rate + OI: reduz inst_min em -5pts cada quando alinhados
- **Sinal CORE adicionado** com 11 critérios do operador

### Score Inst por tipo (cycles.py):
| Tipo | inst_min base | Com sessão perigosa |
|------|--------------|---------------------|
| CORE | 25 | 35 |
| REVERSAL | 45 | 55 |
| SCOUT, SM_SWEEP, DIV | 50 | 60 |
| FLEX, SETUP, PULLBACK, CROSS, BB_BREAK, SURGE, REBOUND | 55 | 65 |
| MOMENTUM | 60 | 70 |

---

## MEMÓRIA INSTITUCIONAL — Mapa completo de bloqueadores

### Score Institucional (0-100) — analyze.py `_score_inst()`
```
20 pts: tendencia_bull/bear (preço > e200 AND e10>e21>e50>e200)
15 pts: adx_long/short_ok (adx > 22 AND pdi/mdi dominante AND adx subindo)
15 pts: dna_flow OR (f_bull/bear AND pressao_bull/bear)
10 pts: ha_bull_1 / ha_bear_1 (1 vela HA confirmada)
10 pts: trendilo_long / trendilo_short
10 pts: rsi_subindo / rsi_caindo
10 pts: v_forte (RVOL >= 1.5x média)
 5 pts: rsi_div_bull / rsi_div_bear
 5 pts: sm_bull / sm_bear
```
**Score mínimo para CORE** = 30 (ha+trl+rsi sempre verdadeiros quando CORE dispara).
**Por isso inst_min=25 para CORE** — garante que passa mas com margem para sessão perigosa.

### Grade do sinal — analyze.py `graduar_sinal()`
```
pts = tendencia_bull/bear (3) + alinhado (2) + macd_bull3/bear3 (2) +
      ha_bull/bear (2) + adx_ok (2) + obv (1) + vwap (1) + v_forte (1) +
      kalman_accel (1) + e200_subindo (1) + f_forte (1) + tend_consist (1)

S+: pts >= 17 | S: pts >= 14 | A: pts >= 11 | B: < 11
Trava: S/S+ degradado para A se score_inst < 70 ou RSI > 65 ou HA fraco
```

### Prioridade de sinais (ordem de verificação):
1. PULLBACK (tbull_r + pullback + dna_flow + adx_long_ok)
2. **CORE** (11 critérios do operador — ver abaixo)
3. CROSS (cruzamento de EMAs)
4. BB_BREAK (Bollinger Band breakout)
5. SM_SWEEP (Smart Money sweep + absorção)
6. REVERSAL (RSI extremo + divergência)
7. SURGE (breakout 3%+ de candle + rvol≥3x)
8. MOMENTUM (RSI cruzando 65/35)
9. REBOUND (RSI rebound de zona extrema)
10. DIV (divergência RSI vs preço)
11. FLEX (setup flexível)
12. SETUP (setup completo com OBV + VWAP)
13. SCOUT (sinal secundário)

---

## SINAL CORE — 11 Critérios Institucionais (14/06/2026)

```python
long_core = (
    45 <= rsi <= 58 and rsi_subindo and          # RSI zona momentum ascendente
    adx >= 18 and vol_nao_fade and not vol_secando and  # Força + volume
    kalman_subindo and trendilo_long and         # Momentum confirmado
    tbull_loose and ha_bull and                  # Estrutura + candle
    not liq_topo and preco > e200 and            # SMC + tendência macro
    preco <= e21 * 1.02                          # Próximo da EMA21 (≤2%)
)

short_core = (
    42 <= rsi <= 55 and rsi_caindo and
    adx >= 18 and vol_nao_fade and not vol_secando and
    not kalman_subindo and trendilo_short and
    tbear_loose and ha_bear and
    not liq_fundo and preco < e200 and
    preco >= e21 * 0.98
)
```

**inst_min = 25** (11 condições são o gate — score_inst será ≥30 sempre)
**score_min = 30** (score geral: mesma faixa de REVERSAL/SM_SWEEP)
**MTF inst_min = 40** (mais exigente em H4 confirmation)
**Stop: 1.5 ATR** | **Leverage: por grade (sem cap adicional)**

---

## BLOQUEADORES MAIS COMUNS — Diagnóstico rápido

### "rsi_zona=F" → RSI fora da janela
- LONG bloqueado: RSI >= 55 → mercado ja subiu, não perseguir
- SHORT bloqueado: RSI <= 40 → mercado já caiu, não vender fundo
- **Ação**: aguardar RSI voltar para janela OU ver se REVERSAL/MOMENTUM ativa

### "seguro=F(bb_topo)" → Preço em topo das Bollinger Bands
- Sinal: pos_bb > 0.97 (preço > 97% da amplitude BB)
- **Ação**: normal — protege de comprar topo de band

### "seguro=F(stoch>0.xx)" → StochRSI esticado
- stoch_rsi > 0.80 AND rsi > 58 → sobrecomprado no curto prazo
- **Ação**: aguardar StochRSI cair para < 0.70

### "seguro=F(pump_rsi(+Xpt))" → RSI subiu >15pts em 3 velas
- Pump detectado — não perseguir rally já feito
- **Ação**: aguardar RSI estabilizar

### "inst<N" → Score institucional insuficiente
- Min por tipo: CORE=25, SCOUT=50, outros=55, MOMENTUM=60
- **Ação**: verificar qual dos 9 fatores está faltando (tendencia_bull/bear = maior peso 20pts)

### "fluxo=X/4" → Fluxo direcional insuficiente
- Soma de: dna_flow, f_bull/bear, trendilo, kalman < 2
- **Ação**: esperar MACD, DNA e Kalman alinharem

### "adx=X<15" → ADX muito baixo
- Mercado lateral/ranging
- **Ação**: esperar ADX > 18 para CORE, > 22 para PULLBACK/CROSS

### "lateral" → Mercado lateralizado
- bb_squeeze (BB estreito) E adx < 15
- **Ação**: aguardar breakout do squeeze

---

## INDICADORES CALCULADOS MAS NÃO USADOS EM SINAIS
(disponíveis para futuras implementações)

- `e200_inclinada_up/down` — slope da EMA200 nos últimos 6 períodos (ótimo para confirmar tendência macro)
- `reteste_mm50_bull/bear` — padrão de reteste da MM50
- `correcao_bull/bear` — correção 2-6% em tendência (entrada em pullback profundo)
- `sombra_sup/inf` — proporção de wick superior/inferior (útil para rejeição de nível)

**FVG (Fair Value Gap) — NÃO implementado ainda:**
```python
# Padrão 3 velas: vela[-3].high < vela[-1].low = FVG bullish (imbalance)
# vela[-3].low > vela[-1].high = FVG bearish
# Instituições retornam para preencher FVGs — forte zona de suporte/resistência
```

---

## LÓGICA INSTITUCIONAL — Como operar como os fundos

### O que instituições FAZEM:
1. **Esperam pelo preço** — nunca perseguem, deixam o mercado vir até eles
2. **Operam em zonas de liquidez** — onde stops de varejo estão concentrados
3. **Confirmam com múltiplos TFs** — H4/D1 para bias, 15m/1h para entrada
4. **Usam order flow** — funding rate negativo = shorts pagando longs = alta mais provável
5. **Size correto** — nunca arriscam mais que 1-3% por trade
6. **Cut losses rápido** — saem quando estrutura quebra, não quando stop percentual bate

### O que instituições NÃO fazem:
- Comprar quando RSI > 70 (já estão vendendo)
- Vender quando RSI < 30 (já estão comprando)
- Operar na sessão asiática (22h-08h UTC) sem motivo forte
- Perseguir pumps ou dumps (vol_secando = saída deles)
- Operar em mercado lateral sem direcionalidade (ADX < 15)

### Funding rate como sinal institucional:
- Funding > +0.03%: longs estão pagando shorts → mercado sobreaquecido no LONG → favorece SHORT
- Funding < -0.03%: shorts pagando longs → mercado sobreaquecido no SHORT → favorece LONG
- Funding neutro (±0.01%): sem bias claro

### OI (Open Interest) como confirmação:
- OI +2%+ com preço subindo → novas posições LONG sendo abertas → sinal de alta válido
- OI -2%- com preço caindo → fechamento de longs (liquidação) → pode ser oportunidade SHORT
- OI crescendo contra a direção = smart money acumulando posição contrária ao movimento
