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

### Após qualquer run do bot:
- **Autorizado a aplicar qualquer ajuste realmente necessário** com base no diagnóstico do run — sem pedir confirmação
- Aplicar → commit → push → disparar novo run automaticamente
- "Necessário" = bloqueador identificado, inconsistência, bug, ou threshold claramente errado

### Parar somente quando:
- Usuário disser explicitamente que o sinal chegou
- Usuário mostrar screenshot do sinal com os dados
- Usuário pedir para parar

### Exceções válidas para não agir:
- Mercado genuinamente em zona morta pós-dump (RSI médio < 32) E todos os candidatos têm 2+ bloqueadores de mercado (não de filtro) — neste caso, informar e aguardar 1 ciclo antes de agir novamente

### Mensagens ao usuário (pedido 20/06 — única coisa que deve chegar via bot)
O bot só envia 2 tipos de mensagem ao Telegram a partir de agora:
1. **Sinal real** (`notify.py enviar_sinal()`)
2. **Diagnóstico de ausência de sinal**, 1x por hora enquanto não houver sinal (`cycles.py _enviar_diagnostico()`,
   intervalo de 3600s tanto pra elegibilidade quanto pro envio — ver `main()`)
- Mensagem de "bot iniciado" e "watchlist/setup em formação" foram **removidas do Telegram** (ficam só no log) —
  eram ruído extra que o usuário não pediu.
- Sempre que eu (assistente) estiver numa sessão ativa e ler esse diagnóstico (colado pelo usuário, ou via log de
  run), devo **auditar antes de aceitar como "mercado parado"**: distinguir bug/contradição de filtro (→ corrigir,
  REGRA #0 acima) de condição genuína de mercado (→ só informar, sem inventar ajuste). Sinal nunca deve parar de
  disparar por falha de código — só por condição real de mercado.
- Limitação honesta: essa auditoria por mim só roda enquanto há uma sessão Claude Code ativa (não existe gatilho
  automático me chamando a cada hora sem sessão aberta). O que É garantidamente automático, mesmo sem sessão
  aberta, é o diagnóstico horário do próprio bot via Telegram (ponto 2 acima).
- Desde 20/06 o diagnóstico horário (ponto 2) também inclui um resumo de **resultado real das últimas 24h**
  (contagem por STOP/TP1_BE/TP2/EXPIRADO, winrate, R médio) — ver seção "RASTREAMENTO DE RESULTADO" abaixo.
  Continua sendo só 2 tipos de mensagem, o resumo é anexado ao diagnóstico existente, não é mensagem nova.

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
- Válido para **TODOS** os tipos de sinal: SCOUT, FLEX, BB_BREAK, PULLBACK, CROSS, SM_SWEEP, DIV, SETUP
- REVERSAL, SURGE, MOMENTUM, REBOUND não usam `rsi_zona` — têm janela de RSI própria embutida na condição do sinal
- Implementado em `analyze.py` como `rsi_zona_long` e `rsi_zona_short`

```python
# analyze.py — FLEX PRO 15/06 (bloqueia apenas extremos absolutos)
rsi_zona_long  = rsi < 75
rsi_zona_short = rsi > 25
```

---

## REGRA #2 — Volume mínimo para sinais

- `vol_nao_fade` (SCOUT): `max(volumes[-1], volumes[-2]) >= vol_ma * 0.80` (FL=3; 0.65 FL=2; 0.50 FL=1; 0.20 FL=0)
- SCOUT (autorizado 20/06 — caso TRUMP/USDT BRONZE 1/5 com RVOL 0.24x passou pelo `vol_nao_fade` solto demais):
  além do `vol_nao_fade` acima, agora exige também `ADX >= 25` (piso fixo, substituiu o `_adx_min` escalado por
  filtro 10/15) e `RVOL >= 1.2` — mesmo piso aplicado ao FLEX no mesmo dia. Torna SCOUT bem mais raro por
  desenho — aceito explicitamente pelo usuário como trade-off.
- BB_BREAK: RVOL ≥ 0.80 (FL=3; mais baixo em FL menor) + OBV confirmado
- SURGE: melhor das 2 últimas velas `rvol_tier_max2 >= 3` (3x+)
- Rompimento sem volume = falso rompimento

## REGRA #3 — Sessão perigosa

- 22h–08h UTC (Asian/madrugada): `_inst_min += 10` (cap 70)
- 08h e 13h UTC (abertura Londres/NY): `_inst_min += 10` (cap 70)

## REGRA #4 — Alavancagem dinâmica 3x–50x (autorizado 20/06 — plano dobrar banca)

- Base por grade: S+=45, S=32, A+=22, A=14, B=8
- Modificadores: +4 inst≥80, +2 inst≥70, -3 inst<55, +2 RVOL≥1.5, -1 RVOL<0.80
- Tetos por tipo: SCOUT=6x, MOMENTUM=28x, SURGE=30x, PREMIUM=30x, BREAKOUT/PUMP=22x, DUMP=16x, BB_BREAK=18x
- Cap por confiança: conf<60→6x, <70→14x, <80→22x, <90→35x
- **Teto de segurança por liquidação** (REGRA #4 nova, crítica): a alavancagem final nunca pode deixar a
  liquidação mais próxima que 1.3x a distância do stop, senão a corretora liquida a posição antes do stop
  disparar (perda = 100% da margem do trade, não os 2-7% planejados de risco). Fórmula em `notify.py`:
  `liq_cap = 100 / (1.3 * risco_pct)` — em stops apertados (ATR baixo) permite chegar a 50x; em stops largos
  o teto efetivo cai bem abaixo disso automaticamente.
- Clamp final: min 3x, máx 50x
- Risco por trade em `config.py` `RISK_BY_GRADE`: B=0.5%, A=1%, S=2%, S+=3% (SCOUT=1%, fora da tabela)
  - ⚠️ A grade "A+" é citada na fórmula de leverage (`notify.py` `_lev`) mas `graduar_sinal()` em `analyze.py`
    **nunca produz A+** (só retorna S+/S/A/B) — essa entrada do dict de leverage é código morto hoje.

## REGRA #5 — Defesas SMC (Smart Money)

- SCOUT e BB_BREAK: `adx_subindo` obrigatório
- LONG: `not liq_topo` (não entrar após varredura de topo) — **exceto SURGE** (contradição com surge_break_h)
- SHORT: `not liq_fundo` (não entrar após varredura de fundo) — **exceto SURGE** (contradição com surge_break_l)
- StochRSI: `stoch_esticado_up` = > 0.80 **E** rsi > 58 (bloqueia seguro_long) — `stoch_esticado_down` = < 0.05 **E** rsi < 35 (bloqueia seguro_short)
  - Correção 20/06: StochRSI normaliza pela faixa relativa dos últimos 14 períodos e satura em tendências fortes mesmo sem sobrecompra/sobrevenda real (ex: RSI 49 com stoch_rsi>0.95). Exigir RSI absoluto também evita bloquear LONG/SHORT válidos por saturação técnica do indicador.

---

## PONTO DE REFERÊNCIA — Estado funcional (10/06/2026)

Commit: `96f3f20` — estado após correções estruturais do dia 10/06

---

## SESSÃO 14/06/2026 — Melhorias aplicadas (⚠️ HISTÓRICO — superseded, ver MAPA COMPLETO no fim do arquivo)

**Commit base de restauração:** `a7226d8` → refatorado em `de4f1a2` → `12c45b5` → atual

### Correções críticas (14/06):
- RSI zona LONG: 60 → 55 (restaurado — não comprar topo) — *depois substituído pela FLEX PRO (REGRA #1)*
- `dump_rsi_spike_short`: removido de `seguro_short`
- `pump_rsi_spike_long`: ajustado — *removido por completo nas restaurações posteriores, não existe mais em `seguro_long`*
- Score inst por tipo de sinal (não mais fixo 60 para todos)
- Funding rate + OI: reduz inst_min em -5pts cada quando alinhados
- Sinal CORE adicionado com 11 critérios do operador — **removido em restauração posterior (commit `9db2d4f`), não existe no `analyze.py` atual**

A tabela de `inst_min` por tipo que existia aqui ficou obsoleta — o gate real hoje é mais simples
(ver "Gate de Score Institucional pós-sinal" no MAPA COMPLETO).

---

## MEMÓRIA INSTITUCIONAL — Mapa completo de bloqueadores

(Score Institucional, Grade e ordem de prioridade dos sinais → ver seção "MAPA COMPLETO DE CONDIÇÕES ATUAIS"
no fim deste arquivo — é a versão auditada linha a linha com o código, esta aqui era a versão antiga.)

---

## BLOQUEADORES MAIS COMUNS — Diagnóstico rápido

### "rsi_zona=F" → RSI fora da janela (REGRA #1, real no código hoje)
- LONG bloqueado: RSI >= 75 → extremo sobrecomprado
- SHORT bloqueado: RSI <= 25 → extremo sobrevendido
- **Ação**: aguardar RSI voltar para janela OU ver se REVERSAL/MOMENTUM/REBOUND ativa (têm janela própria)

### "seguro=F(bb_topo)" → Preço em topo das Bollinger Bands
- Sinal: pos_bb > 0.97 (preço > 97% da amplitude BB)
- **Ação**: normal — protege de comprar topo de band

### "seguro=F(stoch>0.xx)" → StochRSI esticado
- LONG: stoch_rsi > 0.80 AND rsi > 58 | SHORT: stoch_rsi < 0.05 AND rsi < 35
- **Ação**: aguardar StochRSI sair da saturação OU RSI absoluto recuar

### "inst<N" → Score institucional insuficiente (dois gates diferentes, não confundir)
1. **Gate embutido no sinal** (`analyze.py`, dentro da própria condição booleana — sinal nem é detectado sem isso):
   score_inst_long/short >= 50 (PULLBACK, CROSS, BB_BREAK, SURGE, FLEX, SETUP) | >= 60 (SM_SWEEP, MOMENTUM) |
   >= 55 (DIV) | sem gate de score_inst (REVERSAL, REBOUND, SCOUT — SCOUT usa "fluxo" no lugar)
2. **Gate pós-sinal** (`cycles.py` `executar_ciclo`, roda DEPOIS que o sinal já foi detectado):
   `_inst_min` = 35 (SCOUT) | 40 (REVERSAL/SM_SWEEP/DIV) | 45 (demais) — sobe para `max(_inst_min, 60)`
   em sessão perigosa (22h-08h UTC ou 08h/13h). MTF (H4→H1): score_min=40 e inst_min=40 fixos.
- **Ação**: verificar qual dos 9 fatores do `_score_inst()` está faltando (tendencia_bull/bear = maior peso 20pts)

### "fluxo=X/4" → Fluxo direcional insuficiente (só SCOUT)
- Soma de: dna_flow, f_bull/bear, trendilo, kalman < `_fluxo_min` (0 FL≤0, 1 FL=1, 2 FL≥2)
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

---

## MAPA COMPLETO DE CONDIÇÕES ATUAIS (auditado 20/06/2026 — bate linha a linha com o código)

Sempre que pedir um ajuste, comece por aqui antes de grepar o código. Pipeline:
`analyze.py:calcular_indicadores()` → `detectar_sinais()` → `graduar_sinal()` → `cycles.py:executar_ciclo()`
(filtra e envia) → `notify.py:enviar_sinal()` (monta stop/TP/leverage e manda pro Telegram).

### Modo (`config.py SIGNAL_MODE`, padrão `FLEX`)
- `FLEX`: roda a cascata de prioridade abaixo (1-12)
- `ELITE`: só ELITE/EARLY (item 0) — bem mais raro e filtrado

### Sinais — ordem de prioridade real em `detectar_sinais()` (primeiro que bater vence)

| # | Sinal | Condição resumida LONG (SHORT é o espelho) |
|---|-------|---------------------------------------------|
| 0 | ELITE/EARLY (só modo ELITE) | `tendencia_forte`+`tendencia_bull`+`alinhado_bull`+`e200_subindo`+`macd_bull3`+`ha_bull3`+`f_forte`+`adx_long_ok`+`rsi_bull_elite`+(`v_forte2` ou `obv_bull`)+`nao_ext_long`+`kalman_accel_up`+`acima_vwap`+`tend_consistente_bull`+(`impulso_bull` ou `liq_long`)+`score>65`+`seguro_long`. EARLY = exaustão (`exaustao_venda`) + `liq_long` + `absorb_bull` + `macd_recuperando` |
| 1 | PULLBACK | `pullback_bull`+`tbull_r`+`preco<e21*1.03`+`dna_flow_bull`+`adx>18`+`pdi>mdi`+`rsi_zona_long`+`score_inst_long>=50`+`seguro_long`+`trendilo_long`+`not liq_topo` |
| 2 | CROSS | `algum_cross_bull`+`dna_flow_bull`+`adx_long_ok`+`preco>e200`+`score_inst_long>=50`+`rsi_zona_long`+`seguro_long`+(`trendilo_long` ou `kalman_subindo`) |
| 3 | BB_BREAK | `bb_break_long`+`bb_expand`+`kalman_subindo`+`k_short_subindo`+`score>40`+`adx>=15`+`adx_subindo`(FL≥2)+`not lateralizado`+`not ext_acima_e21`+`obv_bull`+`not liq_topo`(FL≥3)+`preco>e200`(*novo 20/06 — caso SPCXUSDT, short_bb_break disparou sem checar tendência de fundo e foi pego por reversão violenta em ativo de baixa liquidez; mesmo filtro do SM_SWEEP*)+`preco>e50`(*novo 21/06 — segundo incidente real no mesmo ativo (SPACEX(PRE), removido da watchlist): sinal mostrou entrada divergente do preço real negociável; ao investigar, BB_BREAK só checava EMA200, permitindo disparar em pullback ainda acima/abaixo da EMA50 dentro da tendência maior — adicionado o mesmo alinhamento de EMA que `tendencia_bull/bear` já exige*)+`rvol>=0.50-0.80`(por FL)+`rsi_zona_long`+`score_inst_long>=50` |
| 4 | SM_SWEEP | `sm_bull`+`rsi>25`+`rsi_zona_long`+`preco>e200`+`score_inst_long>=60` |
| 5 | REVERSAL | `rsi<30`+`ha_bull`+`v_forte`+(`liq_fundo` ou `absorb_bull`)+`macd_recuperando`+`adx>12`+`preco>e200*0.96`+(`dna_flow_bull` ou `obv_bull`) — sem gate de `score_inst` |
| 6 | SURGE | `rvol_tier_max2>=3`(3x+)+`candle_bull_pct>0.03`+`surge_break_h`+`not exaustao_topo`+(`kalman_subindo` ou `k_short_subindo`)+`ha_bull`+`rsi<78`+`score_inst_long>=50`+(`dna_flow_bull` ou `trendilo_long`) — **não** usa `not liq_topo` (contradição com `surge_break_h`). *Exigência de fluxo adicionada 20/06 — SURGE sem nenhuma confirmação de fluxo (DNA Flow e Trendilo ambos "—") é puro spike de volume sem sustentação, propenso a squeeze (caso real LAB/USDT 20/06).* |
| 7 | MOMENTUM | `rsi_ant<65<=rsi<73`+`ha_bull`+`dna_flow_bull`+`not liq_topo`+`adx>22`+`v_forte`+`trendilo_long`+`score_inst_long>=60`+`mom_seguro_long` (ignora `stoch_esticado_up` no teto de RSI, mas ainda bloqueia se já saturado) |
| 8 | REBOUND | `rsi_spike_long`(rsi prévio>65)+`rsi_rebound_long`(54-62 e caindo do pico)+`ha_bull`+`dna_flow_bull`+`trendilo_long`+`adx>20`+`v_bom`+`kalman_subindo`+`not lateralizado`+`seguro_long`+`nao_ext_long_tight` |
| 9 | DIV | `rsi_div_bull`+`ha_bull`+`v_bom`+`rsi>25`+`rsi_zona_long`+`not exaustao_topo`+`adx>15`+`not lateralizado`+`preco>e200`+`score_inst_long>=55` |
| 10 | FLEX | `score>=40`+`ha_bull2`+`macd_bull_r`+`adx>=25`+`not lateralizado`+`nao_ext_long_tight`+`seguro_long`+`flex_vol_ok`+`rvol>=1.2`+`rsi_zona_long`+`nao_overext_long`+`rsi_nao_chasing_long`+`score_inst_long>=50`+(`liq_long` ou `liq_fundo` ou `trendilo_long`+`kalman_subindo`)+(`trendilo_long` ou `kalman_subindo` ou `dna_flex_bull`) — *`adx`/`rvol` subidos de 14/0.5 para 25/1.2 em 20/06 (caso TIA/USDT SHORT BRONZE 2/5, RVOL 0.65x/ADX 24 — sinal fraco demais pelo gate antigo)* |
| 11 | SETUP | `score>50`+`ha_bull2`+`macd_recuperando`+`adx>18`+`obv_bull`+`v_bom`+`acima_vwap`+`not lateralizado`+`nao_ext_long_tight`+`seguro_long`+(`liq_long` ou `liq_fundo`)+`preco>e200`+`score_inst_long>=50`+`rsi_zona_long` |
| 12 | SCOUT | `score>=_sc_min`(25 FL≤0/40 outros)+`ha_bull_1`+`macd_bull_r`+`adx>=25`(piso fixo, *antes era `_adx_min` 10/15 escalado por FL — endurecido 20/06 junto com `rvol>=1.2`, caso TRUMP/USDT BRONZE 1/5 RVOL 0.24x*)+`adx_subindo`(FL≥2)+`not lateralizado`+`nao_ext_long_tight`+`seguro_long`(FL≥1)+`vol_nao_fade`+`rvol>=1.2`+`nao_overext_long`+`rsi_nao_chasing_long`+`rsi_zona_long`+`not liq_topo`(FL≥3)+soma(`dna_flow_bull`,`f_bull`,`trendilo_long`,`kalman_subindo`)`>=_fluxo_min`(0/1/2 por FL) |

`seguro_long` = `not perto_bb_topo` E `not ext_acima_e21` E `not vol_secando` E `not exaustao_topo` E `rsi<70` E `not stoch_esticado_up`.
`seguro_short` = `not vol_secando` E `not exaustao_fund` E `rsi>27` E `not stoch_esticado_down`.

⚠️ Não existe sinal **CORE** no código atual (removido na restauração `9db2d4f` de 19-20/06). As menções a CORE
nas seções históricas acima são só registro do que já existiu.

### Score Institucional (0-100) — `analyze.py _score_inst()`
20pts tendência (preço>e200 e e10>e21>e50>e200) + 15pts ADX (>22, direção dominante, subindo) + 15pts flow
(dna_flow ou f_bull/bear+pressão) + 10pts HA última vela + 10pts trendilo + 10pts RSI subindo/caindo + 10pts
RVOL≥1.5x + 5pts divergência RSI + 5pts smart money sweep.

### Grade — `analyze.py graduar_sinal()`
pts 0-18: tendência(3) + alinhado(2) + MACD 3 barras ou normal(2/1) + HA(2) + ADX_ok ou ADX>15(2/1) + OBV(1) +
VWAP(1) + RVOL forte(1) + Kalman acelerando(1) + EMA200 subindo(1) + flow forte(1) + tendência consistente(1).
`S+`≥17 | `S`≥14 | `A`≥11 | `B`<11. Trava: S/S+ cai para A se `score_inst<70` ou RSI esticado (>65 LONG / <35 SHORT).
Grade **A+ nunca é gerada** — só existe na tabela de leverage (código morto lá).

### Gate pós-sinal — `cycles.py executar_ciclo()` (roda DEPOIS que o sinal já foi decidido acima)
- Score mínimo: `30` (REVERSAL/SM_SWEEP/DIV) ou `40` (todos os outros tipos)
- Score Inst mínimo (`_inst_min`): `35` SCOUT | `40` REVERSAL/SM_SWEEP/DIV | `45` demais — sobe para `max(.,60)`
  em sessão perigosa (22h-08h UTC ou abertura 08h/13h UTC)
- H4 confirma (quando tf é 1h/30m/15m): bloqueia LONG se H4 `score<-30` e H4 bear; bloqueia SHORT se H4
  `score>30` e H4 bull
- Cooldown: mesma direção = `tf_minutos*60s` (mínimo 2h); qualquer direção na mesma moeda/tf = 2h
- ATR > 4% do preço → ignora (volátil demais)
- Limites por ciclo: 3 sinais total, 2 SCOUT, 2 LONG, 2 SHORT (anti-correlação), 10% capital de risco acumulado
- FLEX sem `dna_flow`/`trendilo` e tendência NEUTRO → bloqueado (TP1 improvável)

### Ciclo MTF (H4→H1) — `cycles.py executar_ciclo_mtf()`, roda em paralelo quando TIMEFRAMES tem (4h+1h) ou (1h+30m/15m)
- H4 precisa achar setup (`score>±15`, `tbull_r`/`tbear_r`, `adx>=13`, RSI<65-75/>43, volume confirmado)
- Filtro BTC H4 macro (exceto na própria BTC/WBTC): bloqueia LONG se BTC H4 bear, bloqueia SHORT se BTC H4 bull;
  bloqueia LONG se BTC RSI>72, bloqueia SHORT se BTC RSI<28
- Entrada real busca a mesma cascata de sinais (1-12) em H1 via `analisar()` completo
- Gate mais apertado que o ciclo normal: `score_min=40` e `inst_min=40` fixos
- Cooldown 4h

### Classificação de confluência — Ouro/Prata/Bronze
⚠️ **SUPERSEDED 22/06** — não é mais selo informativo, é gate real de entrada. Ver seção dedicada
"CLASSIFICAÇÃO INSTITUCIONAL V2" no fim deste arquivo.

### Stop / TP — `notify.py enviar_sinal()`
- `mult_atr` base (distância do stop, intocado em 22/06): `2.0` SURGE | `1.5` SM_SWEEP/demais | `1.8` FLEX/SETUP
- Usa stop estrutural (swing low/high ±0.5 ATR) se a distância ficar entre 0.3-2.5 ATR e do lado certo do preço
  — **exceto** SURGE/BB_BREAK/MOMENTUM (sempre ATR puro)
- R múltiplos (TP1/TP2): ⚠️ **SUPERSEDED 22/06** — tabela antiga por grade/fonte/ADX removida. Ver
  "CLASSIFICAÇÃO INSTITUCIONAL V2" no fim deste arquivo pro esquema fixo atual (TP1=1R/TP2 por tier).
- Teto estrutural: TP1 nunca passa de ~92% da distância até o próximo swing high/low (piso mínimo caiu de
  0.8R pra 0.5R em 22/06, acompanhando o r1 base menor)

### Risco e alavancagem — ver REGRA #4 (já corrigida nesta auditoria)
`RISK_BY_GRADE` real: B=0.5% A=1% A+=1.5% S=2% S+=3% (SCOUT=1%, fora da tabela) | `MAX_CYCLE_RISK`=10%/ciclo

---

## MODO INSTITUCIONAL (autorizado 20/06, evoluído 20/06 — não substitui FLEX/SCOUT)

`SIGNAL_MODE=INSTITUCIONAL` ativa um 3º modo (além de FLEX/ELITE), separado da cascata 1-12 — roda
**em vez de**, não ao lado de FLEX (escolha de ciclo/run, igual ELITE). Objetivo pedido: "operar apenas
movimentos institucionais de alta probabilidade". Reaproveita os sinais TIPADOS já existentes (não é
mais uma condição monolítica única) — só 6 tipos ficam ativos, com prioridade quando mais de um bate:

1. **SM_SWEEP** (score_inst≥70) · 2. **MOMENTUM** (≥70) · 3. **SURGE** (≥75) · 4. **PULLBACK** (≥65) ·
5. **SETUP** (≥65) · 6. **FLEX** (≥80, prioridade mais baixa). SCOUT/DIV/REBOUND/BB_BREAK/CROSS/
REVERSAL/ELITE ficam **fora** deste modo (não fazem parte do conjunto pedido).

Cada um dos 6 exige a própria condição de entrada típica (`long_sm`, `long_momentum`, etc., a mesma
cascata 1-12) **E** todo um piso comum (`analyze.py`, bloco `_base_inst_long`/`_base_inst_short` dentro
de `detectar_sinais()`):

```
tendencia_bull/bear (e10>e21>e50>e200 + preco>e200, já existia)
adx > 25 e adx_subindo (adx atual > adx vela anterior)
rvol > 1.5
dna_flow_bull/bear + trendilo_long/short (fluxo precisa bater nos dois)
liq_fundo_12 / liq_topo_12 — sweep de liquidez nos últimos 12 candles (indicador NOVO,
  variante de liq_fundo/liq_topo que olhava só 1-2 velas; usa o mesmo sm_swing_h/sm_swing_l)
RSI: 35-68 LONG | 32-65 SHORT
StochRSI: <0.85 LONG | >0.15 SHORT (mais solto que o stoch_esticado_up/down padrão)
volume real > vol_ma e not vol_secando
distância da BB ≥1% do lado errado (anti-topo LONG / anti-fundo SHORT, indicador novo `pos_bb`
  agora exposto no dict — antes só existiam os booleanos perto_bb_topo/fund a 97%/3%)
estrutura_alta/baixa (pivôs HH+HL / LH+LL, já existia)
```

- **H4 obrigatório e rígido**: `cycles.py` usa `_h4_confirma_estrito()` (não o `_h4_confirma()` padrão)
  quando `SIGNAL_MODE=="INSTITUCIONAL"` — exige H4 **confirmando ativamente** a direção (h4_bull para
  LONG, h4_bear para SHORT), não só "ausência de divergência forte". Sem candle H4 disponível, bloqueia
  (o modo padrão deixa passar se H4 não veio). Qualquer divergência bloqueia.
- **Grade**: ainda pela própria Score Inst (não por `graduar_sinal()` por pontos) — `S`≥90, `A+`≥80,
  `A`≥70 — esse comportamento mudou de `if fonte=="INSTITUCIONAL"` para `if SIGNAL_MODE=="INSTITUCIONAL"`
  em `analyze.py:analisar()`, porque agora `fonte` vira o nome do tipo real (SM_SWEEP, FLEX, etc.), não
  mais a string fixa `"INSTITUCIONAL"`.
- **Cooldown próprio** (`config.py` `COOLDOWN_INSTITUCIONAL_MESMA_DIR`=3h, `..._OPOSTA`=2h) — só se aplica
  quando `SIGNAL_MODE=="INSTITUCIONAL"`; os outros modos continuam com o cooldown padrão (`tf_minutos`,
  mín. 2h mesma direção / 2h fixo oposta).
- **Risco por grade** (`RISK_INSTITUCIONAL_POR_GRADE` em `config.py` — ver AJUSTE INSTITUCIONAL ELITE
  abaixo, substituiu o risco fixo 1% original) usado tanto em `cycles.py` pro acúmulo de risco por ciclo
  quanto em `notify.py` pro tamanho real da posição — ignora `RISK_BY_GRADE` neste modo.
- **Teto de ciclo 5%** (`MAX_CYCLE_RISK_INSTITUCIONAL`, vs 10% padrão) e **máximo 3 posições simultâneas**
  abertas (`MAX_POSICOES_INSTITUCIONAL` — subiu de 2 pra 3 no AJUSTE INSTITUCIONAL ELITE, checado via
  `len(estado["_posicoes_abertas"])` em `cycles.py`, tanto no ciclo FLEX quanto no MTF — reaproveita o
  rastreamento de resultado, ver seção abaixo).
- Fica bem mais raro que FLEX/SCOUT por desenho — não é bug se passar vários ciclos sem sinal nesse modo.

---

## AJUSTE INSTITUCIONAL ELITE (autorizado 21/06 — "foco em qualidade e não quantidade")

Pedido do usuário pra endurecer ainda mais o modo `SIGNAL_MODE=INSTITUCIONAL` já existente (não criou um
modo novo — usuário escolheu evoluir o existente entre as opções apresentadas). Aplicado em `analyze.py`
(piso comum `_base_inst_long`/`_base_inst_short`), `config.py`, `notify.py` e `cycles.py`.

- **RSI mais estreito**: LONG `45-68` (subiu o piso de 35→45 — pedido original do usuário era 50, mas
  50 cortaria boa parte do pullback clássico que ainda é entrada institucional válida; 45 ainda corta
  oversold/chasing extremo, foi a opção que o usuário escolheu entre as apresentadas) | SHORT `32-50`
  (desceu o teto de 65→50 — evita short ainda em RSI neutro/forte, i.e. perseguir topo de correção).
- **Heikin Ashi obrigatório** (`ha_bull`/`ha_bear`) no piso comum — antes só vinha embutido em alguns
  sinais individuais (ex: `long_momentum`, `long_sm`), não em todos os 6 tipos do modo.
- **Score Institucional mínimo unificado em 80** pra todos os 6 tipos (SM_SWEEP/MOMENTUM/SURGE/PULLBACK/
  SETUP/FLEX) — pedido original do usuário era "Score≥75 e Confiança≥70%", mas `notify.py` calcula
  `confiança = score_inst - 10`, então confiança≥70% já implica score_inst≥80 (o piso mais estrito
  prevalecia mesmo assim) — unificado num só número em vez de manter dois redundantes.
- **Grade só S/A+** (`GRAUS_PERMITIDOS_INSTITUCIONAL = {"S","A+"}` em `config.py`, checado em
  `cycles.py:executar_ciclo()` e `executar_ciclo_mtf()`) — grade `A` (que ainda passava antes, e que ainda
  passa no FLEX/ELITE padrão) é bloqueada neste modo. Na prática a grade `A` já nem deveria mais ocorrer
  aqui, porque `analyze.py:analisar()` só atribui `A` quando `score_inst<80`, e o sinal não dispara nesse
  modo sem `score_inst>=80` — o filtro de grade fica como piso de segurança redundante, não como gate ativo.
- **Risco por grade em vez de fixo**: `RISK_INSTITUCIONAL_POR_GRADE = {"A+": 0.005, "S": 0.01}` em
  `config.py` (substituiu `RISK_INSTITUCIONAL=0.01` fixo) — S opera mais arriscado (1%) que A+ (0.5%),
  que agora é o degrau mais baixo aceito neste modo. Usado em `notify.py` (tamanho real da posição) e
  `cycles.py` (acúmulo de risco por ciclo).
- **Máximo de posições simultâneas 2→3** (`MAX_POSICOES_INSTITUCIONAL`) — pedido explícito do usuário.
- **Circuit breaker de stops consecutivos** (`STOPS_CONSECUTIVOS_PAUSA=3` em `config.py`): após 3 STOPs
  consecutivos em posições abertas sob este modo, pausa novas entradas institucionais até a próxima
  posição fechar como vitória (`TP1_BE` ou `TP2`) — reage a dado real de mercado, não a um tempo fixo
  (pedido original do usuário era "pausar até o próximo ciclo forte", interpretado como "até vencer", já
  que "ciclo forte" não tem definição objetiva no código). Implementado via:
  - `state.py registrar_posicao_aberta()` ganhou o parâmetro `modo` (guarda em que `SIGNAL_MODE` a posição
    foi aberta, já que o modo pode mudar entre runs cacheados em `last_signals.json`).
  - `cycles.py _atualizar_resultados()` incrementa `estado["_stops_consecutivos_inst"]` a cada `STOP` de
    posição com `modo=="INSTITUCIONAL"`, zera no primeiro `TP1_BE`/`TP2`.
  - `cycles.py executar_ciclo()` e `executar_ciclo_mtf()` bloqueiam nova entrada institucional quando
    `estado["_stops_consecutivos_inst"] >= STOPS_CONSECUTIVOS_PAUSA`.
- **Gestão (stop/TP) intocada** — por pedido explícito do usuário e pela regra de não tocar gestão antes de
  30-50 trades fechados (ver RASTREAMENTO DE RESULTADO abaixo), este ajuste não mexeu em `notify.py`
  stop/TP/leverage, só em filtros de entrada e risco/posição.

---

## RASTREAMENTO DE RESULTADO (autorizado 20/06 — "perde boas entradas, o que fazer")

Motivado por relato do usuário de que sinais "sobem considerável mas perde boas entradas" — sem dado real
de winrate, qualquer ajuste de stop/entrada seria às cegas (violaria a REGRA #1 de não alterar regras sem
evidência). `signals_log.csv` é só write-only e nem persistia entre runs do GitHub Actions — não dava pra
saber objetivamente se o problema é stop apertado, entrada tardia, ou se na real a maioria bate o alvo.

### Como funciona
- Toda vez que `enviar_sinal()` (`notify.py`) envia um sinal com sucesso, devolve um dict (não mais `True`
  puro) com `stop/tp1/tp2/r1/r_final`. O chamador (`cycles.py`, em `executar_ciclo()` e
  `executar_ciclo_mtf()`) usa esse dict pra registrar a posição via `registrar_posicao_aberta()`
  (`state.py`), guardada em `estado["_posicoes_abertas"]` — dentro do mesmo dict já cacheado entre runs via
  `last_signals.json`, sem precisar de arquivo de estado novo.
- A cada ciclo (`cycles.py main()`, logo após "Ciclo concluído"), `_atualizar_resultados()` busca o preço
  atual de cada símbolo em acompanhamento via `buscar_preco_atual()` (`scanner.py`, ticker simples MEXC,
  sem klines) e chama `verificar_posicoes_abertas()` (`state.py`) pra resolver as que já bateram TP/STOP.
- Taxonomia de resultado: `STOP` (bateu stop antes do TP1) | `TP1_BE` (bateu TP1, depois voltou ao preço de
  entrada — fecha com 50% da posição em lucro parcial e 50% no zero) | `TP2` (bateu o alvo final) |
  `EXPIRADO`/`EXPIRADO_SEM_DADO` (não resolveu em 72h — fica fora do cálculo de winrate, resultado incerto).
- R realizado: `STOP=-1.0` | `TP1_BE = r1*0.5` | `TP2 = r1*0.5 + r_final*0.5` | expirado = sem R (não conta).
- Cada posição fechada vai pro `resultados_log.csv` (novo, `;`-delimitado, mesmo estilo do `signals_log.csv`)
  via `registrar_resultado()`. `resumo_resultados(horas=24)` agrega contagem por resultado, winrate e R
  médio — esse resumo é anexado ao diagnóstico horário existente (`_enviar_diagnostico`), não cria mensagem
  nova no Telegram (ver regra dos "2 tipos de mensagem" acima).
- `bot.yml` cacheia `resultados_log.csv` junto com `last_signals.json` (`actions/cache/restore`/`save`),
  senão os dados seriam perdidos a cada run isolado do GitHub Actions.

### Limitações conhecidas
- Não há registro retroativo — só sinais enviados a partir deste commit entram no rastreamento. Vai levar
  algumas horas/dias até acumular dado suficiente pra winrate ser estatisticamente útil.
- `EXPIRADO`/`EXPIRADO_SEM_DADO` ficam fora do winrate — se aparecerem com frequência alta, é sinal de que o
  prazo de 72h (`_PRAZO_MAX_HORAS` em `state.py`) pode estar curto demais pro timeframe usado, ou que
  `buscar_preco_atual` está falhando pra algum símbolo (ex: delistado, símbolo mudou na MEXC).
- ⚠️ Não tomar nenhuma decisão de ajustar stop/entrada/TP **sem antes olhar esse resumo** — é exatamente o
  dado que faltava pra distinguir "stop apertado de mais" de "mercado genuinamente contra" de "está tudo
  bem, é variância normal".
- **Detalhamento por fonte/grade** (autorizado 21/06 — caso real de winrate 14%/7 trades, amostra pequena
  demais pra diagnosticar causa): `resumo_resultados()` (`state.py`) agora também agrega por `fonte` (tipo
  de sinal) e `grade`, contando STOP/total e R médio de cada grupo. `cycles.py` (`_enviar_diagnostico`)
  imprime uma linha extra por agrupamento (`por fonte: ...`, `por grade: ...`) só quando há mais de 1 grupo
  na amostra. É observabilidade pura — não muda stop/TP/entrada, só deixa o dado pronto pra quando a amostra
  chegar nos 30-50 trades necessários (regra acima) pra identificar se algum tipo de sinal específico está
  puxando o winrate pra baixo.

---

## AJUSTE PROFISSIONAL — DNA + GAUSS H1/30M (autorizado 21/06 — "qualidade acima de quantidade")

Pedido do usuário pra reduzir frequência de sinais e subir a barra de qualidade — menos sinais, mais
convicção. Implementado como **gates adicionais pós-sinal** (`cycles.py`), sem reescrever a cascata de 12
sinais em `analyze.py` (preserva todo o histórico de calibração por incidente já documentado neste arquivo).

- **Timeframes**: `config.py` agora filtra `TIMEFRAMES` pra só aceitar `30m`/`1h` — qualquer `5m`/`15m`
  vindo de env var é descartado (`_TF_PERMITIDOS`); se a lista ficar vazia, cai pra `["30m","1h"]`.
- **Filtro de Regime Global**: `cycles.py:_btc_h1_regime_neutro()` — busca BTCUSDT H1 uma vez por ciclo
  (`main()`, antes de `executar_ciclo_mtf`/`executar_ciclo`) e bloqueia LONG e SHORT em **todas** as moedas
  se `BTC ADX < 20` E `BTC RSI` entre 45-55 (mercado sem direção). Falha aberta (não bloqueia) se a busca do
  BTC falhar — mesma filosofia do `_h4_confirma` (sem dado, não bloqueia). Thresholds em `config.py`
  (`BTC_REGIME_ADX_MAX/RSI_MIN/RSI_MAX`).
- **RVOL adaptativo por TF**: `config.py RVOL_MIN_BY_TF = {"30m": 0.70, "1h": 0.80}` — gate novo em
  `executar_ciclo`/`executar_ciclo_mtf`, aplicado a todos os tipos de sinal (além do RVOL que cada sinal já
  pode exigir na própria condição em `analyze.py`, que continua intocada).
- **Piso de ADX universal**: `config.py ADX_MIN_GLOBAL = 20` — bloqueia qualquer sinal com `ADX < 20`,
  mesmo que a condição própria do sinal (ex: PULLBACK `adx>18`) já tenha deixado passar.
- **Qualidade mínima — só grade A/S**: `config.py GRAUS_PERMITIDOS = {"A","A+","S","S+"}` — `B` é
  bloqueado nos dois ciclos. SCOUT (que graduamente sai como B com frequência) fica bem mais raro por
  consequência direta, não é bug.
- **Smart Money Flow obrigatório**: o bloqueio que antes só valia pra FLEX em tendência neutra
  (`fonte=="FLEX" and not _dna and not _trl and _tend=="NEUTRO"`) foi generalizado pra **todos os tipos de
  sinal, sempre** — `not _dna and not _trl` (sem DNA Flow nem Trendilo alinhados na direção do sinal)
  bloqueia, independente de tendência ou fonte. Mesmo gate adicionado no `executar_ciclo_mtf` (que antes não
  tinha checagem de fluxo nenhuma). Efeito colateral esperado: REVERSAL (que só exige `dna_flow_bull or
  obv_bull`, não Trendilo) também pode ficar mais raro se só bater via OBV.
- **RSI Flex Pro (penalização gradual, REGRA #1 intacta)**: `analyze.py`, bloco do `score` — os gates duros
  (`rsi_zona_long<75` / `rsi_zona_short>25`) **não mudaram**. Adicionado só uma penalização gradual no
  `score` bruto, na mesma direção que ele já aponta (puxa pra zero, não inverte sinal): score>0 (lean LONG)
  com RSI>70 → -15, RSI>65 → -7; score<0 (lean SHORT) com RSI<30 → +15, RSI<35 → +7.
- **Bônus de ADX no score**: breakpoints do score subiram de `>30`/`>22` pra `>=30`/`>=25` (pedido
  explícito do usuário "score bonus em ADX>=25 e ADX>=30").
- **Gestão intocada**: `notify.py` (stop/TP/leverage/risco) não foi tocado neste ajuste — por pedido
  explícito do usuário, só revisar depois de 30-50 trades fechados (ver RASTREAMENTO DE RESULTADO acima).
- Nenhum dos gates novos altera `_detectar_bloqueadores_diag()` (diagnóstico horário) — esses motivos novos
  (`grade=B`, `adx<20`, `rvol<0.70`, `sem fluxo SMC`, `regime BTC neutro`) aparecem só no log do ciclo, não
  no resumo de diagnóstico enviado ao Telegram. Se isso virar um bloqueador frequente, vale considerar
  expor no diagnóstico horário também.

---

## FILTRO DE EXECUÇÃO V2 (autorizado 21/06 — caso real 78% STOP/24h)

Motivado por `resultados_log.csv` real: 18 trades fechados em 24h, 14 STOP, 4 TP2, **zero TP1_BE** — padrão
binário (ou corre limpo até TP2, ou vai direto pro stop), que aponta pra qualidade de entrada/confluência
insuficiente, não pra distância de stop/TP (que continua intocada, mesma regra de esperar 30-50 trades).

O usuário trouxe um documento próprio ("AJUSTE PROFISSIONAL V2") pedindo simultaneamente **afrouxar** quase
todo piso de detecção (ADX_MIN_GLOBAL 20→18, RVOL_MIN_BY_TF, score/score_inst por sinal, RSI até 78/22, etc,
objetivo declarado "aumentar frequência") **e** adicionar um "Filtro de Execução" final mais estrito
(Grade A/A+/S, Confiança≥65%, Score Inst≥70, ADX≥20, RVOL≥1.0, R:R≥1:2). Auditoria antes de aplicar achou
contradição real: `confiança = score_inst-10` (`notify.py` linha ~192, vale pra **todo** sinal, não só
INSTITUCIONAL) — logo "Confiança≥65%" já significa `score_inst≥75`, que é **mais apertado** que qualquer
piso de detecção do próprio documento (PULLBACK/FLEX pediam `score_inst≥45`) e mais apertado que o "Score
Inst≥70" do mesmo bloco (esse ficou redundante/morto, mesmo erro já corrigido uma vez no AJUSTE
INSTITUCIONAL ELITE). Aplicar o documento inteiro faria o filtro final dominar e anular o afrouxamento de
cima — resultado prático seria sinal **mais raro**, não mais frequente, e não atacaria o padrão binário
observado. Apresentado ao usuário, que escolheu aplicar **só** a camada final (mais seletiva, ataca o
STOP) e descartar o afrouxamento de cima (contraditório e sem efeito prático real de qualquer forma).

### O que foi implementado
- `config.py`: `INST_MIN_EXEC = 75` (score_inst mínimo unificado, equivalente a confiança≥65%) e
  `RVOL_MIN_EXEC = 1.0` (subiu pra `1.2` em 22/06, junto com a CLASSIFICAÇÃO INSTITUCIONAL V2 — ver seção
  dedicada no fim do arquivo) — constantes novas, não substituem `RVOL_MIN_BY_TF`/o `_inst_min` tiered por
  tipo de sinal (35-60), são um piso adicional por cima (`max(...)`), pra manter a calibração por incidente
  já documentada nas seções acima.
- `cycles.py executar_ciclo()`: `_rvol_min_tf = max(RVOL_MIN_BY_TF.get(tf,0.80), RVOL_MIN_EXEC)` e
  `_inst_min = max(_inst_min, INST_MIN_EXEC)` — só quando `FILTER_LEVEL>=1` (preserva o modo debug/force
  `FILTER_LEVEL=0` sem o piso novo).
- `cycles.py executar_ciclo_mtf()`: mesmo piso aplicado em `_inst_min_mtf` (antes fixo 40) e `_rvol_mtf`
  (antes fixo 0.80 do TF "1h").
- `ADX≥20` do documento já existia (`ADX_MIN_GLOBAL`), `Grade A/A+/S` já existia (`GRAUS_PERMITIDOS` —
  manteve S+ também, sem motivo pra bloquear o que é estritamente melhor que S). `R:R≥1:2` já estava
  satisfeito pelas grades que passam o filtro de grade (`notify.py`: A=1.8R/3.5R, A+=2.0R/4.0R,
  S/S+=2.2R/4.5R, mesmo após calibração por ADX baixo) — nenhuma mudança necessária ali.
- Efeito esperado: sinais mais raros (objetivo real era reduzir STOP, não aumentar frequência — a parte
  "aumentar frequência" do documento original foi descartada por contradizer este filtro). Validar com o
  próximo lote de `resultados_log.csv` antes de qualquer novo ajuste de seletividade.

---

## BB_BREAK — DEFESA DE STOCHRSI ESGOTADO (autorizado 21/06 — casos reais CVX e ASTER)

Usuário reportou (com print do gráfico) dois sinais BB_BREAK SHORT reais (CVX/USDT e ASTER/USDT, ambos
30M) entrando "depois do movimento" — RSI já em 30-32 (perto do piso de 25 da REGRA #1) e, no caso do
ASTER, StochRSI em 0.0114 (extremamente saturado). Pedido: o sinal devia esperar o RSI "pronto pra
descer" (ainda com espaço pra continuar), não disparar quando o indicador já esgotou.

Auditoria em `analyze.py` achou a causa raiz: `long_bb_break`/`short_bb_break` (linha ~560) é o **único**
tipo de sinal da cascata 1-12 que não checa StochRSI saturado (`stoch_esticado_up`/`stoch_esticado_down`,
REGRA #5) — PULLBACK, CROSS, SM_SWEEP, FLEX, SETUP, DIV, REBOUND todos usam `seguro_long`/`seguro_short`
(que inclui esse check), BB_BREAK nunca usou. Não dá pra simplesmente adicionar `seguro_long`/`seguro_short`
inteiro: `perto_bb_topo`/`perto_bb_fund` (`pos_bb>0.97`/`<0.03`) é **sempre verdadeiro** quando
`bb_break_long`/`short` já é verdadeiro (preço já rompeu a banda, logo `pos_bb>1.0` ou `<0.0`) — geraria
contradição igual à já documentada do SURGE com `liq_topo`/`liq_fundo`.

Fix aplicado: adicionado só o pedaço relevante e sem contradição —
`not stoch_esticado_up` em `long_bb_break`, `not stoch_esticado_down` em `short_bb_break`. Bloqueia
exatamente o padrão dos dois casos reais (RSI já no fim da janela + StochRSI já saturado <0.05/>0.80),
sem tocar nos outros 10 critérios do BB_BREAK nem na REGRA #1 (rsi_zona continua intocada).

---

## BB_BREAK — RSI COM ESPAÇO PRA CORRER (autorizado 21/06 — 3º caso real, WUSDT)

Mesmo dia, 3º incidente real de BB_BREAK: WUSDT LONG entrou com RSI=68 (StochRSI não estava saturado,
então o fix anterior não pegou este caso) e a posição bateu STOP — preço rompeu a banda, chegou perto do
TP1 e devolveu o movimento todo. Olhando os 3 casos reais juntos (CVX SHORT RSI~30-32, ASTER SHORT
RSI~30, WUSDT LONG RSI=68): todos entraram a menos de ~10 pontos do limite absoluto de `rsi_zona`
(75 LONG / 25 SHORT, REGRA #1) — ou seja, o RSI já estava no fim do espaço que a REGRA #1 permite antes de
travar, exatamente o padrão que o usuário descreveu repetidamente como "comprar/vender depois que o
movimento já aconteceu" / "só comprar quando o RSI tem espaço pra subir, não pra descer".

Fix aplicado: piso/teto adicional **só no BB_BREAK** (não altera `rsi_zona_long`/`short`, que é a REGRA #1
e continua `<75`/`>25` pra todos os outros 11 sinais da cascata) — `long_bb_break` agora exige também
`rsi < 65`, `short_bb_break` exige também `rsi > 35`. Dá ~10 pontos de margem até o teto/piso absoluto da
REGRA #1 antes de disparar, em vez de deixar o BB_BREAK romper banda já quase no limite. Validação:
os 3 incidentes reais (CVX, ASTER, WUSDT) teriam sido bloqueados por este piso novo.

Não toca em stop/TP/leverage (gestão) nem nos outros 10 critérios do BB_BREAK — só fecha a margem de RSI
especificamente pra este tipo de sinal, que agora soma 3 incidentes reais na mesma sessão (a taxa mais
alta de qualquer tipo de sinal monitorado hoje, ver `por fonte: BB_BREAK:3/3STOP` no resumo de 24h).

---

## RISCO PELA METADE — TEMPORÁRIO (autorizado 21/06 — banca real em $86)

Banca real caiu pra $86 (de capital inicial ~$93-100) sob winrate 26%/24h (dado de *antes* dos 2 fixes de
qualidade de entrada do mesmo dia: Filtro de Execução V2 e defesa de RSI/StochRSI no BB_BREAK). Ainda não
há trades novos suficientes pra confirmar se os fixes melhoraram o winrate — perguntado ao usuário se
queria reduzir risco, pausar sinais, ou manter; resposta foi "sem preferência". Escolhido reduzir risco
(opção mais conservadora que não interrompe a coleta de dado novo, que é o que falta pra validar os fixes).

`config.py RISK_BY_GRADE`/`RISK_SCOUT` cortados pela metade: B 0.5%→0.25%, A 1%→0.5%, A+ 1.5%→0.75%,
S 2%→1%, S+ 3%→1.5%, SCOUT 1%→0.5%. Só afeta tamanho da posição (`valor_risco = CAPITAL * pct_risco` em
`notify.py`) — não toca em stop/TP/leverage nem em nenhum filtro de entrada. `RISK_PCT` (fallback genérico,
raramente usado já que todo grade conhecido tem entrada própria em `RISK_BY_GRADE`) não foi alterado.

**Reverter** pra tabela original (`{"B": 0.005, "A": 0.01, "A+": 0.015, "S": 0.02, "S+": 0.03}`,
`RISK_SCOUT=0.01`) quando os trades novos pós-fixes (Filtro V2 + BB_BREAK) confirmarem winrate melhor que
os 26% anteriores — checar `resumo_resultados()` no diagnóstico horário antes de reverter.

---

## TETO CONSERVADOR DE ALAVANCAGEM (autorizado 21/06 — review manual de sinal real)

Usuário revisou manualmente um sinal real (LONG, BB_BREAK, RSI 68, ADX~38, leverage sugerida 18x — auditado
e confirmado como o sinal das 10:55 UTC, **antes** dos dois fixes de BB_BREAK do mesmo dia; com o código
atual esse sinal já seria bloqueado por `rsi<65`, então não era mais um bug pendente) e considerou a
alavancagem alta demais pra banca real ($86-93). Pediu critério próprio: 5-10x por padrão, só liberar 15x+
com Score≥85 + ADX≥30 + RVOL≥2 + fluxo institucional + acima da MM200. Perguntado se aplicava ou mantinha
a fórmula da REGRA #4 esperando mais dados — resposta "sem preferência"; optei por aplicar (linha com a
redução de risco do mesmo dia: perfil mais defensivo enquanto a banca está baixa e a amostra de resultado
ainda é pequena).

`notify.py` (`enviar_sinal()`, após o teto de liquidação da REGRA #4): novo teto adicional —
`_lev = min(_lev, 10)` **a não ser que** todos batam: `score_inst>=85` E `adx>=30` E `rvol_val>=2` E
`dna_flow_ok` E `trendilo_ok` (fluxo nos dois indicadores, não só um) E a favor da MM200
(`tendencia=="ALTA"` LONG / `"BAIXA"` SHORT, mesmo campo que já alimenta o display da mensagem). Quando os
5 critérios batem, a fórmula original da REGRA #4 (grade + score_inst + RVOL + cap por fonte/confiança/
liquidação) continua valendo sem este teto extra — não criei um segundo número fixo tipo "15x", a
alavancagem final nesse caso vem só dos caps que já existiam.

Não toca em stop/TP/R:R (gestão de saída) nem no tamanho de posição (`RISK_BY_GRADE`, já reduzido à parte
no mesmo dia) — só no teto de alavancagem. Reverter junto com a revisão de gestão pós 30-50 trades, se os
dados mostrarem que o teto de 10x não fazia diferença real no resultado.

---

## SINAL ATRASADO + STOP APERTADO — PRIORIDADE ÚNICA (autorizado 21/06)

Usuário declarou explicitamente que, a partir de agora, **uma regra prevalece sobre todas as outras**:
não quebrar a banca com (1) sinal atrasado (entrada perto do fim do movimento), (2) stop apertado demais
(estopado por ruído antes da tese se confirmar), (3) sinal de má qualidade/risco — e pediu pra deixar de
seguir os processos burocráticos anteriores (ex: "esperar 30-50 trades antes de tocar gestão") quando eles
travarem uma solução direta pra esses 3 problemas. Isso **não revoga** as regras permanentes (REGRA #0-#5)
nem o histórico de calibração por incidente acima — é uma prioridade de desempate quando a cautela
processual conflitar com proteção de capital óbvia e já evidenciada por dado real (banca em $86, 78%
STOP/24h, múltiplos incidentes reais de entrada tardia).

### Fix 1 — Sinal atrasado (generalização de anti-chasing)
`nao_overext_long/short` (preço não pode estar >50% além do range das últimas 48 velas) e
`rsi_nao_chasing_long/short` (RSI não pode ter saltado >18pts numa vela só) já existiam em `analyze.py`
mas só eram aplicados a **FLEX e SCOUT**. Generalizados para mais 7 tipos de sinal: **PULLBACK, CROSS,
SM_SWEEP, BB_BREAK, SETUP, DIV, REBOUND** (este último só ganhou `nao_overext`, não `rsi_nao_chasing`,
porque sua entrada já é necessariamente um pullback de várias velas, não um salto de RSI numa vela só).
Deliberadamente **não** aplicado a REVERSAL, SURGE, MOMENTUM — esses 3 são, por desenho, sinais que
entram justamente perto de um extremo/spike (mesma razão pela qual SURGE já não usa `not liq_topo`/
`liq_fundo`, seria contradição direta com a própria condição de entrada do sinal). Só adiciona critério
(AND puro) — nunca afrouxa nada, então o efeito é sinais mais raros e mais seletivos, nunca menos seguros.

### Fix 2 — Stop apertado
`notify.py` (`enviar_sinal()`), dois ajustes:
- `SM_SWEEP` tinha o stop mais apertado do sistema (`mult_atr=1.2`, vs 1.5 padrão/1.8 FLEX-SETUP/2.0
  SURGE) sem nenhum incidente documentado que justificasse isso — subiu pra 1.5 (mesmo padrão de
  "demais"), removendo o caso especial.
- Buffer do stop estrutural (`stop_estrutural = swing_low/high ± atr*0.3`) subiu pra `atr*0.5` — dá mais
  espaço pro stop respirar além do swing antes de ser ativado, reduzindo sensibilidade a pavio de ruído
  no exato ponto da estrutura (que é onde o preço mais tende a tocar antes de reverter).

Fix 3 (sinal de má qualidade) já estava coberto pelo Filtro de Execução V2 + GRAUS_PERMITIDOS + ADX_MIN_
GLOBAL + Smart Money Flow obrigatório (ver seções acima) — nenhuma mudança nova necessária ali agora; o
Fix 1 acima também ataca esse pilar (entrada tardia é, na prática, um subtipo de sinal de baixa qualidade).

Não mexe em R:R, alvos (`r1`/`r_final`) nem leverage — só largura do stop e seletividade de entrada.
Validar com o próximo lote de `resultados_log.csv`: se a taxa de STOP cair sem reduzir TP2/TP1_BE na
mesma proporção, o diagnóstico (entrada tardia + stop apertado) estava certo.

### Fix 1b — RSI "criterioso" (mesmo dia, pedido seguinte do usuário)
Usuário pediu RSI mais criterioso/com espaço pra continuar, não só bloqueio de extremo absoluto — exatamente
o gap que ainda restava em **PULLBACK, CROSS, SM_SWEEP**: esses 3 usavam só `rsi_zona_long/short` (<75/>25,
REGRA #1), sem nenhum teto intermediário, enquanto FLEX/SCOUT/SETUP/REBOUND/DIV já tinham `nao_ext_long_
tight`/`short` (`(preco-e21)/atr<2.5 and (rsi<65 ou (adx>32 e rsi<75))` — teto efetivo de RSI 65, com
exceção até 75 só em tendência muito forte). Adicionado `nao_ext_long_tight`/`short` aos 3 que faltavam —
reusa o critério já calibrado em vez de inventar um número novo. R:R por grade já era generoso o
suficiente (A=1.8R/3.5R, S/S+=2.2R/4.5R — bem além do "risco 1 / retorno 2" pedido), não precisou de
mudança ali. *(R:R por grade citado aqui é histórico — a tabela foi removida em 22/06, ver seção abaixo.)*

---

## CLASSIFICAÇÃO INSTITUCIONAL V2 — GATE DE ENTRADA E SAÍDA EM 3 ESTÁGIOS (autorizado 22/06)

Pedido do usuário pra substituir o selo Ouro/Prata/Bronze antigo (informativo, nunca bloqueava nada) por
uma classificação que **é** o gate final de entrada, com regras de execução próprias por nível, e trocar a
tabela de R-múltiplo por grade/fonte/ADX por uma saída fixa em 3 estágios. Pedido explícito: "se precisar
deletar faça uma limpeza para não ficar muito assunto misturado" — por isso as seções antigas (Classificação
de confluência, tabela de R-múltiplo) acima foram marcadas como SUPERSEDED em vez de duplicadas.

### Classificação — `analyze.py classificar_v2()`, chamada dentro de `analisar()`, exposta como `result["classificacao"]`
Usa só `score_inst_long/short` (não soma "Confiança" separado — `confiança = score_inst-10` já é o mesmo
número, mesma redundância já corrigida uma vez no FILTRO DE EXECUÇÃO V2, ver seção acima):

- 🥇 **OURO**: `score_inst>=90` + `RVOL>=1.2` + `ADX>=25` + fluxo confirmado (`dna_flow` ou `trendilo` na
  direção) + Kalman alinhado (`kalman_subindo`/`kalman_descendo`) + MM200 favorável (`tendencia_bull`/`bear`)
  + RSI `40-65` LONG / `35-60` SHORT + liquidez varrida (`liq_fundo_12` LONG / `liq_topo_12` SHORT) +
  distância até a MM21 `<=3%` do preço
- 🥈 **PRATA**: `score_inst>=80` + `RVOL>=0.90` + `ADX>=22` + fluxo confirmado + Kalman alinhado + MM50
  favorável (`preco>e50` LONG / `preco<e50` SHORT) + RSI `35-70` LONG / `30-65` SHORT
- 🥉 **BRONZE**: `score_inst>=75` + `RVOL>=0.70` + `ADX>=20` + fluxo confirmado
- Nenhum dos 3 pisos atingido → `None`
- ⚠️ Pisos atualizados 22/06 (eram Score 85/75/65, RVOL 1.8/1.4/1.2) — ver "DNA+GAUSS INSTITUCIONAL V2"
  mais abaixo. Mudança aplicada **globalmente** (FLEX/ELITE/INSTITUCIONAL, não só institucional) por escolha
  explícita do usuário ao ser perguntado sobre o escopo.

### Regras de execução — gate real, em `cycles.py` (`executar_ciclo()` e `executar_ciclo_mtf()`)
- **OURO**: sempre opera (nenhuma checagem extra)
- **PRATA**: só opera se H1 estiver alinhado na direção do sinal. Quando o ciclo já é H1 (MTF, ou
  `executar_ciclo` com `tf=="1h"`), reusa `result["alinhado_bull"/"alinhado_bear"]` direto. Quando o ciclo
  é 30M, busca H1 separado por símbolo via prefetch novo (`todos_h1_align`, mesmo padrão do prefetch H4 já
  existente) e calcula alinhamento com `calcular_indicadores()` sobre essas velas.
- **BRONZE / sem classificação**: ignorado — sinal nem chega a ser enviado (vai pro diagnóstico horário
  como candidato bloqueado, motivo `v2=BRONZE`/`v2=none`)
- **Bloqueios universais explícitos do pedido** (`cycles.py`, antes do gate de classificação): `RSI>75`
  bloqueia LONG, `RSI<25` bloqueia SHORT (já cobertos por REGRA #1/`rsi_zona`, mas a checagem explícita foi
  adicionada igual mesmo assim por pedido direto), mercado lateral (`ind["lateralizado"]`) bloqueia os dois
  lados. `RVOL_MIN_EXEC` subiu de `1.0`→`1.2` em `config.py` pra bater com o "RVOL<1.2" do pedido (ADX<20 já
  era coberto por `ADX_MIN_GLOBAL`).
- `analisar()` também passou a expor no dict final (antes ficavam só dentro de `calcular_indicadores()`,
  nunca chegavam no `result` usado por `cycles.py`): `lateralizado`, `alinhado_bull/bear`, `adx_subindo`,
  `e21`, `e50` — corrige de quebra um bug latente onde `adx_subindo` sempre chegava `False` em `cycles.py`
  (lia de um dict que nunca tinha essa chave).

### Saída — `notify.py enviar_sinal()`, 3 estágios fixos (substitui a tabela por grade/fonte/ADX)
- **TP1 = 1R fixo** (`r1=1.0`, antes variava 1.2-2.2R por grade) → fecha 50% da posição, stop conceitual
  vai pra BE (break-even)
- **TP2 por tier de classificação** (`r_final`): OURO=4.0R | PRATA/BRONZE=3.0R → fecha 30%
- **Restante (20%, "runner")**: não tem alvo de preço fixo — segue MM10/MM21 e perda de estrutura (pivôs
  HH/HL ou LH/LL). Resolvido por `cycles.py _checar_runners()` (candle fresco, não ticker simples): fecha
  quando o preço perde MM10 **e** MM21 simultaneamente, ou quando `estrutura_alta`/`estrutura_baixa` vira
  falso.
- Teto estrutural do TP1 (nunca passa de ~92% da distância até o próximo swing) e o cálculo de stop em si
  (`mult_atr`, stop estrutural) ficaram **intocados** — só os R-múltiplos de alvo mudaram.

### Rastreamento de posição — 3 estágios (`state.py`)
- Antes: 2 estágios (aberta → tp1_atingido), `TP2` fechava 100% da posição de uma vez.
- Agora: 3 estágios (aberta → `tp1_atingido` → `tp1_atingido`+`tp2_atingido`="runner"). `tp2_atingido=True`
  não fecha a posição, só marca que virou runner — fica em `estado["_posicoes_abertas"]` até
  `_checar_runners()` resolver.
- `fechar_runner()` (novo) — remove a posição de `_posicoes_abertas` por identidade (`p is posicao`) e
  devolve o dict com `resultado="TP2_RUNNER"` pronto pra `registrar_resultado()`.
- R realizado novo: `TP2_RUNNER = r1*0.5 + r_final*0.3 + r_runner*0.2`, onde `r_runner` é calculado no
  momento do fechamento do runner (`(preco_saida-entrada)/risco`), não um valor fixo. O `TP2` antigo
  (binário, fechava tudo de uma vez) continua existindo só como branch legado em `registrar_resultado()`
  pra qualquer posição que já estivesse cacheada em `last_signals.json` antes deste commit — código novo
  nunca produz `TP2` puro.
- `_CAMPOS_RESULTADOS` (schema do `resultados_log.csv`) **não foi alterado** — `r_runner` e `classificacao`
  ficam só no JSON de estado (`last_signals.json`, sem schema fixo), não em colunas novas do CSV, pra não
  quebrar o arquivo já cacheado entre runs do GitHub Actions (mudar colunas de um CSV append-only quebra o
  header/linhas anteriores).
- Circuit breaker institucional (`_stops_consecutivos_inst`) passou a zerar também em `TP2_RUNNER`, não só
  `TP1_BE`/`TP2`.

### O que NÃO mudou
- Tamanho de posição (`RISK_BY_GRADE`/`RISK_INSTITUCIONAL_POR_GRADE`, ver RISCO PELA METADE acima)
- Alavancagem (REGRA #4 + TETO CONSERVADOR DE ALAVANCAGEM acima)
- Distância do stop (`mult_atr`, stop estrutural — só o Fix 2 de 21/06 já documentado acima)
- A cascata de 12 sinais em `analyze.py:detectar_sinais()` — a classificação V2 roda **depois** que um
  sinal já foi detectado, é uma camada adicional de gate/saída, não substitui nenhuma condição de entrada
  da cascata.

---

## DNA+GAUSS INSTITUCIONAL V2 — RECALIBRAÇÃO DO MODO INSTITUCIONAL (autorizado 22/06)

Usuário trouxe um documento próprio de especificação ("DNA+GAUSS INSTITUCIONAL V2", focado em TF 30M) pedindo
pra recalibrar o modo `SIGNAL_MODE=INSTITUCIONAL` com objetivo declarado "menos operações, menos entradas em
topo/fundo, maior taxa de TP2, Win Rate 45-55%, Profit Factor>1.5, drawdown reduzido". O documento tinha 3
pontos genuinamente ambíguos/com risco de contradição com a calibração já existente (mesmo padrão de
documentos anteriores do usuário, ver FILTRO DE EXECUÇÃO V2 acima) — perguntado ao usuário antes de aplicar:

1. **RVOL/ADX de entrada caem bastante** (RVOL 150%→70%, ADX 25→20) ao mesmo tempo que o objetivo é "menos
   operações" — confirmado que é proposital: quem filtra de fato agora é a classificação OURO/PRATA/BRONZE
   (que exige RVOL/ADX mais altos, ver tabela acima) + Score mínimo, não o piso de entrada bruto.
2. **Grade**: documento pedia "A, S, S+", mas o modo institucional usa grade por Score Inst (S>=90/A+>=80/
   A>=70), nunca produz S+ — confirmado manter esse esquema e só ampliar a faixa permitida pra incluir A
   (antes só S/A+ passavam).
3. **Escopo do OURO/PRATA/BRONZE**: confirmado aplicar globalmente (afeta também FLEX/ELITE, não só
   INSTITUCIONAL) — ver tabela atualizada na seção CLASSIFICAÇÃO INSTITUCIONAL V2 acima.

### O que foi implementado (`analyze.py`, bloco `_base_inst_long`/`_base_inst_short` dentro de `detectar_sinais()`)
- `ADX > 25` → `ADX > 20`
- `RVOL > 1.5` → `RVOL > 0.70`
- `RSI SHORT`: teto `50` → `55` (faixa agora `32-55`, RSI LONG `45-68` ficou igual)
- **ADX subindo com tolerância**: antes exigia `adx_subindo` (estritamente `adx > adx_anterior`); agora usa
  `_adx_subindo_tol = adx >= adx_anterior - 2` — permite uma leve queda de até 2 pontos sem bloquear (pedido
  explícito "ADX atual >= ADX anterior - 2"). Essa tolerância é local ao piso institucional, não mudou o
  `adx_subindo` global usado por SCOUT/BB_BREAK na cascata normal.
- **Score Inst mínimo** dos 6 tipos (SM_SWEEP/MOMENTUM/SURGE/PULLBACK/SETUP/FLEX): `80` → `75`.
- **Exceção de mercado lateral** (`cycles.py`, só quando `SIGNAL_MODE=="INSTITUCIONAL"`): o bloqueio
  universal de `lateralizado` (CLASSIFICAÇÃO V2) passa a abrir excepção se `bb_expand` (BB Width expandindo)
  **ou** `ADX > 25` — squeeze já rompendo não é mais tratado como lateral morto. `bb_expand` precisou ser
  adicionado ao dict de retorno de `analisar()` (já existia dentro de `calcular_indicadores()`, não chegava
  no `result` usado por `cycles.py`).
- `config.py GRAUS_PERMITIDOS_INSTITUCIONAL`: `{"S","A+"}` → `{"S","A+","A"}`.
- Classificação OURO/PRATA/BRONZE: ver tabela atualizada na seção anterior (mudança global, não só deste modo).

### O que NÃO mudou
- Cooldown institucional, risco por grade (`RISK_INSTITUCIONAL_POR_GRADE`), teto de ciclo/posições
  simultâneas, circuit breaker de stops consecutivos — nenhum desses foi mencionado no documento do usuário.
- H4 estrito (`_h4_confirma_estrito`), stop/TP/leverage (gestão) — intocados, mesma regra de só revisar
  gestão depois de amostra suficiente de trades fechados.
- A cascata de detecção dos 6 tipos de sinal em si (SM_SWEEP/MOMENTUM/etc.) — só o piso comum por cima.

---

## BACKTEST AUTOMÁTICO POR SINAL (autorizado 22/06)

Pedido do usuário: "toda moeda que der sinal já faça um backtest e guarde os resultados pra ajuste do bot" —
motivado por `resultados_log.csv` (resultado real) demorar horas/dias pra acumular amostra suficiente pra
calibrar filtros. Objetivo: dado de calibração rápido (minutos, não dias) pra complementar o rastreamento
real já existente, não substituí-lo.

### Como funciona (`auto_backtest.py`, módulo novo)
- Chamado por `cycles.py` logo depois que `enviar_sinal()` confirma envio com sucesso, em **ambos** os
  pontos de disparo (`executar_ciclo()` e `executar_ciclo_mtf()`): `await backtest_sinal(session, sym, tf,
  result["fonte_sinal"], result["sinal"])`.
- Busca até 500 candles históricos do mesmo símbolo/timeframe (`scanner.buscar_candles`) e varre uma janela
  deslizante (passo de 2 candles, cooldown de 6 candles entre ocorrências da mesma fonte/direção pra não
  contar a mesma ocorrência várias vezes) procurando outras vezes que `analyze.analisar()` já teria
  detectado o **mesmo tipo de sinal** (mesma `fonte_sinal`) na **mesma direção** no histórico recente.
- Cada ocorrência achada é resolvida pra frente (candle a candle, olhando high/low) usando a MESMA régua de
  stop/TP do sinal real — `notify.calcular_stop_tp()`, extraído de `enviar_sinal()` justamente pra ser
  reaproveitado aqui sem duplicar lógica de gestão. Resultado: `STOP` / `TP1_BE` / `TP2` / não resolvido
  (saiu da janela de candles disponível).
- Resultado agregado (1 linha por sinal real enviado, não por ocorrência) grava em `backtest_log.csv`
  (`;`-delimitado, novo arquivo — `config.BACKTEST_FILE`): `n_ocorrencias`, `n_stop`, `n_tp1_be`, `n_tp2`,
  `winrate`, `r_medio`.
- `resumo_backtest(horas=24)` agrega por `fonte` numa janela de tempo — anexado ao diagnóstico horário
  existente (`cycles.py _enviar_diagnostico()`, linha nova `Backtest auto (24h): ...`), mesmo padrão de
  `por_fonte`/`por_grade`/`por_timeframe` de `resumo_resultados()`. Não é mensagem nova no Telegram.
- `bot.yml` cacheia `backtest_log.csv` junto com `last_signals.json`/`resultados_log.csv` (`actions/cache`),
  senão o dado seria perdido a cada run isolado do GitHub Actions.

### Limitação conhecida (documentada no próprio módulo)
A saída real do bot tem 3 estágios (TP1=50%→BE, TP2=30%, 20% "runner" via MM10/MM21+estrutura, ver
CLASSIFICAÇÃO INSTITUCIONAL V2 acima). O backtest aproxima o runner como TP2 fechando os 50% finais de uma
vez (sem tracking candle-a-candle do trailing) — suficiente pra medir taxa de STOP e winrate de entrada,
**não é réplica exata** do `resultados_log.csv` real. Decisão de ajuste de filtro/gestão deve sempre
priorizar o dado real (`resumo_resultados()`) quando a amostra real for suficiente — o backtest automático é
um indicador adiantado (*leading indicator*) pra calibração rápida enquanto a amostra real ainda é pequena.

### Por timeframe (`state.py resumo_resultados()` / `cycles.py _enviar_diagnostico()`)
Resposta à pergunta "operar só H1 fica mais limpo?" (22/06): em vez de decidir sem dado, o resumo de
resultado real de 24h passou a também agregar por `timeframe` (campo que já existia no schema do
`resultados_log.csv`, só não era agregado) — aparece como `por timeframe: ...` no diagnóstico horário quando
houver mais de 1 timeframe na amostra. Quando a amostra acumular trades suficientes em 30M e 1H, esse
detalhamento mostra objetivamente se um dos dois timeframes está puxando o winrate pra baixo, antes de
restringir `TIMEFRAMES` pra só `1h` (mudança que hoje seria especulação, não dado).
