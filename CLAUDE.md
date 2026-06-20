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
| 3 | BB_BREAK | `bb_break_long`+`bb_expand`+`kalman_subindo`+`k_short_subindo`+`score>40`+`adx>=15`+`adx_subindo`(FL≥2)+`not lateralizado`+`not ext_acima_e21`+`obv_bull`+`not liq_topo`(FL≥3)+`preco>e200`(*novo 20/06 — caso SPCXUSDT, short_bb_break disparou sem checar tendência de fundo e foi pego por reversão violenta em ativo de baixa liquidez; mesmo filtro do SM_SWEEP*)+`rvol>=0.50-0.80`(por FL)+`rsi_zona_long`+`score_inst_long>=50` |
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

### Classificação de confluência — Ouro/Prata/Bronze (`notify.py enviar_sinal()`, autorizado 20/06)
Selo informativo na mensagem, não bloqueia nenhum sinal — mede qualidade real do setup além do gate mínimo
de entrada. 5 critérios (`dna_flow` e `trendilo` juntos | `rvol>=1.5` | `adx>20` e subindo | `score_inst>=65` |
RSI saudável: 40-68 LONG / 32-60 SHORT): `>=4/5`→🥇OURO | `3/5`→🥈PRATA | `<=2/5`→🥉BRONZE. Motivado pelo caso
LAB/USDT SURGE 20/06 (squeeze) — o sinal teria saído BRONZE (só RVOL batia), agora fica visível na mensagem.

### Stop / TP — `notify.py enviar_sinal()`
- `mult_atr` base: `2.0` SURGE | `1.2` SM_SWEEP | `1.8` FLEX/SETUP | `1.5` demais
- Usa stop estrutural (swing low/high ±0.3 ATR) se a distância ficar entre 0.3-2.5 ATR e do lado certo do preço
  — **exceto** SURGE/BB_BREAK/MOMENTUM (sempre ATR puro)
- R múltiplos base por grade: SCOUT `1.2R/2.0R` | S+/S `2.2R/4.5R` | A `1.8R/3.5R` | B `1.5R/2.5R`
- SURGE: r1-0.5 (min 1.5) / r_final-1.0 (min 3.0) | DIV: r_final-0.5 (min 2.5)
- Calibração por ADX: `<20` → r1×0.65 (min 0.8) / r_final×0.75 (min 1.5) | `20-24` → r1×0.85 (min 1.0) / r_final×0.90 (min 2.0)
- Teto estrutural: TP1 nunca passa de ~92% da distância até o próximo swing high/low

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
- **Risco fixo 1%/trade** (`RISK_INSTITUCIONAL` em `config.py`, usado tanto em `cycles.py` pro acúmulo de
  risco por ciclo quanto em `notify.py` pro tamanho real da posição) — ignora `RISK_BY_GRADE` neste modo.
- **Teto de ciclo 5%** (`MAX_CYCLE_RISK_INSTITUCIONAL`, vs 10% padrão) e **máximo 2 posições simultâneas**
  abertas (`MAX_POSICOES_INSTITUCIONAL`, checado via `len(estado["_posicoes_abertas"])` em `cycles.py` —
  reaproveita o rastreamento de resultado, ver seção abaixo).
- Fica bem mais raro que FLEX/SCOUT por desenho — não é bug se passar vários ciclos sem sinal nesse modo.

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
