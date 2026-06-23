# GAUSS+DNA — Regras de Prioridade Permanente

## REGRA #-3 — PARAR IMEDIATAMENTE QUANDO O USUÁRIO ESCREVER "STOP" (autorizado 23/06, prioridade máxima)

Sempre que a mensagem do usuário contiver "stop" (ou "pare"), interrompo **imediatamente** qualquer
ação/ferramenta em andamento — incluindo o loop de ajuste→disparo→diagnóstico da REGRA #0 — e não tomo
nenhuma nova ação até o usuário dar a próxima instrução. Isso vale mesmo em modo de execução autônoma/loop
(ex: aguardando resultado de um run do bot disparado anteriormente): não retomo o loop sozinho, não disparo
novo run, não aplico novo ajuste — só espero. É o caso mais extremo da REGRA #-1 (vontade do usuário sempre
prevalece): aqui não há ambiguidade a interpretar, é parada literal e imediata.

## REGRA #-2 — COMUNICAÇÃO SEMPRE EM PORTUGUÊS (autorizado 23/06)

Toda resposta do assistente ao usuário (chat, mensagens de status, resumos) é **sempre em português**,
nunca em inglês — pedido explícito do usuário ("não quero nada em inglês na minha tela"). Isso não afeta
nomes de variável/função em código (continuam em português onde já estavam, mas não é trocado código
existente em inglês só por causa desta regra) nem texto técnico de log — é sobre o que chega pra leitura
direta do usuário.

## REGRA #-1 — VONTADE DO USUÁRIO SEMPRE PREVALECE (autorizado 22/06, prioridade acima de todas as outras)

O que o usuário pede **agora** sempre tem prioridade sobre qualquer decisão antiga documentada neste
arquivo — mesmo que essa decisão tenha sido marcada como "regra permanente", "autorizado" ou justificada
com um incidente real no passado. Histórico de incidentes/calibração abaixo continua valendo como
**contexto** (por que algo ficou de um jeito), não como **trava** que precise de debate ou justificativa
extra pra ser revertida quando o usuário pedir o contrário.

Na prática:
- Se um pedido novo do usuário contradiz algo documentado abaixo, aplico o pedido novo direto — não preciso
  reabrir auditoria, pedir confirmação extra, ou defender a regra antiga antes de mudar.
- Não apago o histórico/justificativas antigas só porque uma regra foi superada — registro como
  "superseded" (mesmo padrão já usado nas seções V2→V3 abaixo), pra manter o "porquê" rastreável.
- Essa regra não desliga julgamento técnico: se um pedido for ambíguo ou tiver mais de uma interpretação
  razoável, ainda perguntar antes de agir (`AskUserQuestion`) — a prioridade aqui é sobre **conflito entre
  pedido novo e regra antiga**, não sobre adivinhar pedidos pouco claros.

---

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
2. **Diagnóstico**, **sempre no 1º ciclo de cada run** (ajustado 22/06 — pedido do usuário "sempre mandava
   mensagem quando dava o run... pra sempre saber que estava em atividade") + depois a cada 1h sem sinal
   dentro do mesmo run (relevante só em `LOOP_MODE`, já que o timeout do job hoje é ~55min — ver "TIMEOUT DO
   JOB MENOR QUE O CRON" abaixo, então cada run de cron já corresponde a 1 diagnóstico garantido). Antes
   (20/06-22/06) só mandava no 1º ciclo se `total_analisados>0`; isso foi removido — agora manda
   incondicionalmente no ciclo 1, mesmo que nenhuma moeda tenha sido analisada ainda, pra garantir que o
   usuário sempre recebe pelo menos 1 mensagem por hora confirmando que o bot está rodando. `cycles.py
   _enviar_diagnostico()`/`main()`.
- Mensagem de "bot iniciado" e "watchlist/setup em formação" continuam **removidas do Telegram** (ficam só
  no log) — o pedido de 22/06 foi atendido reforçando a garantia do diagnóstico (ponto 2), não recriando
  uma 3ª categoria de mensagem; mantém o princípio de só 2 tipos de mensagem chegando ao usuário.
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
  Ajustado 22/06 (pedido do usuário, print real do resumo "winrate 37%... por fonte/grade") — essa linha
  agora **sempre aparece** no diagnóstico, mesmo sem nenhum trade fechado na janela de 24h (antes ficava
  omitida por completo quando `resumo_resultados()` devolvia `None`, parecendo rastreamento quebrado em vez
  de "ainda sem dado"). `cycles.py _enviar_diagnostico()`: bloco `else` novo escreve "Resultados (24h):
  nenhum fechado ainda" nesse caso.

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

## CLASSIFICAÇÃO INSTITUCIONAL V2 — GATE DE ENTRADA E SAÍDA EM 3 ESTÁGIOS (22/06)

⚠️ **SUPERSEDED 22/06 (V3, mesmo dia)** — auditoria de 3 runs reais seguidos (~3h) achou ZERO sinais
enviados: o funil empilhado da V2 (grade letra + `ADX_MIN_GLOBAL=20` + `RVOL_MIN_EXEC=1.2` +
`score_inst>=75` fixo + sessão perigosa cravando 60) bloqueava até movimentos reais fortes (ALLO/GWEI/HUS,
ver prints do usuário). Usuário trouxe documento próprio "CLASSIFICAÇÃO INSTITUCIONAL V3" pra recalibrar —
ver seção dedicada abaixo pro esquema atual (pisos OURO/PRATA/BRONZE mais baixos, saída em 4 estágios em
vez de 3). Mantida aqui só como registro histórico do que existiu entre os dois pedidos do usuário no
mesmo dia.

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
   INSTITUCIONAL) — pisos já superseded pela V3, ver seção CLASSIFICAÇÃO INSTITUCIONAL V3 abaixo.

### O que foi implementado (`analyze.py`, bloco `_base_inst_long`/`_base_inst_short` dentro de `detectar_sinais()`)
- `ADX > 25` → `ADX > 20`
- `RVOL > 1.5` → `RVOL > 0.70`
- `RSI SHORT`: teto `50` → `55` (faixa agora `32-55`, RSI LONG `45-68` ficou igual)
- **ADX subindo com tolerância**: antes exigia `adx_subindo` (estritamente `adx > adx_anterior`); agora usa
  `_adx_subindo_tol = adx >= adx_anterior - 2` — permite uma leve queda de até 2 pontos sem bloquear (pedido
  explícito "ADX atual >= ADX anterior - 2"). Essa tolerância é local ao piso institucional, não mudou o
  `adx_subindo` global usado por SCOUT/BB_BREAK na cascata normal.
- **Score Inst mínimo** dos 6 tipos (SM_SWEEP/MOMENTUM/SURGE/PULLBACK/SETUP/FLEX): `80` → `75`.
- **Exceção de mercado lateral** (histórico — `cycles.py`, só quando `SIGNAL_MODE=="INSTITUCIONAL"`): pedido
  feito quando ainda existia o bloqueio universal de `lateralizado` da V2. Esse bloqueio universal (e a
  exceção dele) foi removido por completo na V3 do mesmo dia (mercado lateral hoje só penaliza -10 no
  score, nunca bloqueia, ver seção V3 abaixo) — `bb_expand` continua calculado em `analyze.py` (usado por
  `bb_break_long/short` na própria cascata), só não existe mais essa exceção específica em `cycles.py`.
- `config.py GRAUS_PERMITIDOS_INSTITUCIONAL`: `{"S","A+"}` → `{"S","A+","A"}`.
- Classificação OURO/PRATA/BRONZE: ver tabela atualizada na seção anterior (mudança global, não só deste modo).

### O que NÃO mudou
- Cooldown institucional, risco por grade (`RISK_INSTITUCIONAL_POR_GRADE`), teto de ciclo/posições
  simultâneas, circuit breaker de stops consecutivos — nenhum desses foi mencionado no documento do usuário.
- H4 estrito (`_h4_confirma_estrito`), stop/TP/leverage (gestão) — intocados, mesma regra de só revisar
  gestão depois de amostra suficiente de trades fechados.
- A cascata de detecção dos 6 tipos de sinal em si (SM_SWEEP/MOMENTUM/etc.) — só o piso comum por cima.

---

## CLASSIFICAÇÃO INSTITUCIONAL V3 — GATE DE ENTRADA E SAÍDA EM 4 ESTÁGIOS (autorizado 22/06)

Substitui a CLASSIFICAÇÃO INSTITUCIONAL V2 (acima, marcada SUPERSEDED) no mesmo dia. Motivado por auditoria
de 3 runs reais consecutivos (~3h de bot rodando) que confirmou **zero sinais enviados** — o funil
empilhado da V2 (grade letra bloqueando + `ADX_MIN_GLOBAL=20` + `RVOL_MIN_EXEC=1.2` + `score_inst>=75`
fixo pra todo sinal + sessão perigosa forçando piso 60) bloqueava até movimentos reais fortes que o usuário
mostrou com prints (ALLO +11.37%, GWEI +20.60%, HUS -24.41%). Usuário trouxe documento próprio
("CLASSIFICAÇÃO INSTITUCIONAL V3") com pisos OURO/PRATA/BRONZE bem mais baixos, regra de execução nova pra
BRONZE (antes sempre ignorado, agora opera condicionalmente), bloqueios universais reduzidos a só RSI/ADX/
RVOL/MM200, e saída em 4 estágios em vez de 3.

### Classificação — `analyze.py classificar_v2()` (nome mantido por compatibilidade, conteúdo é a V3)
⚠️ **SUPERSEDED 22/06 (V4, mesmo dia)** — usuário trouxe tabela própria com pisos mais altos em quase todos
os critérios (não foi pedido de afrouxamento, ver seção "CLASSIFICAÇÃO INSTITUCIONAL V4" mais abaixo pro
esquema atual). Mantida aqui só como registro histórico do que existiu entre os pedidos do mesmo dia.

Usa só `score_inst_long/short`:

- 🥇 **OURO**: `score_inst>=80` + `RVOL>=1.5` + `ADX>=22` + fluxo confirmado (`dna_flow` ou `trendilo` na
  direção, **obrigatório**) + Kalman alinhado + MM200 favorável + RSI `35-70` LONG / `30-65` SHORT +
  liquidez varrida (`liq_fundo_12` LONG / `liq_topo_12` SHORT) + distância até a MM21 `<=6%` do preço
- 🥈 **PRATA**: `score_inst>=70` + `RVOL>=1.2` + `ADX>=18` + Kalman alinhado + MM50 favorável + RSI `30-75`
  LONG / `25-70` SHORT — fluxo **opcional** (não checado)
- 🥉 **BRONZE**: `score_inst>=60` + `RVOL>=1.0` + `ADX>=15` — fluxo **ignorado** completamente
- Nenhum dos 3 pisos atingido → `None`
- Mudança de pisos V2→V3: Score mínimo cai bastante (90→80 OURO, 80→70 PRATA, 75→60 BRONZE), RVOL sobe um
  pouco (1.2→1.5 OURO, 0.90→1.2 PRATA, 0.70→1.0 BRONZE) — a barra de qualidade migra de "score altíssimo"
  pra "volume real + score moderado", bem menos raro. PRATA deixa de exigir fluxo (era obrigatório).
  Distância MM21 da OURO sobe de `<=3%` pra `<=6%` (deixa de cortar entrada em tendência já um pouco
  estendida). RSI das 3 faixas afrouxa nas duas pontas.

### Regras de execução — gate real, em `cycles.py` (`executar_ciclo()` e `executar_ciclo_mtf()`)
- **OURO**: sempre opera (nenhuma checagem extra)
- **PRATA**: só opera se H1 estiver alinhado na direção do sinal (igual V2 — `result["alinhado_bull/bear"]`
  direto quando o ciclo já é H1, ou busca H1 lazy por símbolo quando o ciclo é 30M)
- **BRONZE**: passa a operar (era sempre ignorado na V2) **quando** H1 alinhado **OU** `score_inst>=70` —
  novo na V3, pedido explícito do documento do usuário ("Operar apenas quando H1 alinhado OU Score≥70")
- **Nenhuma classificação**: ignorado — sinal nem chega a ser enviado (diagnóstico horário registra motivo
  `v3=none`)
- **Bloqueios universais** (`cycles.py`, antes do gate de classificação, bem mais curtos que a V2): `RSI>80`
  bloqueia LONG, `RSI<20` bloqueia SHORT (afrouxado de 75/25 da V2/REGRA #1 pro piso explícito do documento
  V3 — REGRA #1 original de 75/25 continua intocada dentro da própria cascata de `analyze.py`, isso é só o
  piso pós-cascata em `cycles.py`), `ADX<15` (`ADX_MIN_GLOBAL`, caiu de 20), `RVOL<1.0` (`RVOL_MIN_EXEC`,
  caiu de 1.2), e MM200 contra a direção (`tendencia` precisa favorecer LONG/SHORT). **Mercado lateral
  deixou de bloquear** (V3: "NÃO BLOQUEAR") — `analyze.py` agora aplica só uma penalidade de -10 no `score`
  bruto (puxa pra zero na mesma direção que o score já apontava, mesmo padrão do RSI Flex Pro), os sinais
  que ainda exigem `not lateralizado` na própria condição da cascata (BB_BREAK, SCOUT etc.) continuam
  bloqueando — só o piso universal pós-cascata mudou. O bloqueio universal "Smart Money Flow obrigatório
  pra todos os tipos" da V2 também foi removido — fluxo agora só é checado dentro da própria condição OURO
  em `classificar_v2()` (obrigatório lá), PRATA é opcional e BRONZE ignora, não precisa de checagem
  separada em `cycles.py`.
- **Grade letra (S+/S/A/B) deixou de bloquear** fora do modo `SIGNAL_MODE=="INSTITUCIONAL"` — `config.py
  GRAUS_PERMITIDOS` foi removido. A qualidade de entrada agora é gate só da classificação OURO/PRATA/BRONZE;
  grade letra continua existindo só pra dimensionar risco (`RISK_BY_GRADE`). No modo `INSTITUCIONAL`
  (separado, não tocado pela V3) `GRAUS_PERMITIDOS_INSTITUCIONAL` continua bloqueando normalmente.
- **Sessão perigosa (REGRA #3)** reimplementada: nos horários de risco (22h-08h UTC + abertura 08h/13h UTC)
  só **OURO** opera — PRATA e BRONZE são bloqueados nesses horários, independente do piso de score que
  bateriam fora deles. Substitui o mecanismo antigo de forçar `_inst_min` pra um piso fixo de 60.

---

## CLASSIFICAÇÃO INSTITUCIONAL V4 — TABELA PRÓPRIA DO USUÁRIO (autorizado 22/06)

Substitui a CLASSIFICAÇÃO INSTITUCIONAL V3 (acima, marcada SUPERSEDED) no mesmo dia, poucas horas depois.
Usuário trouxe tabela própria de pisos OURO/PRATA/BRONZE, explicitamente **mais apertada** que a V3 na
maioria dos critérios — direção contrária ao resto da sessão (que tinha sido só afrouxamento: vol_secando,
BTC_REGIME_ADX_MAX, exaustao). Como o pedido contradizia o esforço do dia, perguntei antes de aplicar
(`AskUserQuestion`) se era intencional; resposta do usuário foi explícita: **"Não quero apertar não quero
liberar sinal, vamos fazer isto"** — ou seja, não é pra debater aperto/afrouxamento, é pra implementar a
tabela exatamente como veio (REGRA #-1: vontade atual do usuário prevalece sobre a trajetória da sessão).

### Tabela aplicada (`analyze.py classificar_v2()`, nome da função mantido por compatibilidade)
- 🥇 **OURO**: `score_inst>=85` + `RVOL>=1.8` + `ADX>=25` + fluxo confirmado (`dna_flow` ou `trendilo` na
  direção, obrigatório) + MM200 favorável + liquidez varrida (`liq_fundo_12` LONG / `liq_topo_12` SHORT) +
  distância até a MM21 `<=3%` do preço
- 🥈 **PRATA**: `score_inst>=75` + `RVOL>=1.2` + `ADX>=20`
- 🥉 **BRONZE**: `score_inst>=65` + `RVOL>=0.7` + `ADX>=18`
- Nenhum piso atingido → `None`

Mudanças V3→V4: Score mínimo sobe em todos os degraus (80→85 OURO, 70→75 PRATA, 60→65 BRONZE). RVOL sobe
em OURO/PRATA (1.5→1.8 OURO, 1.2 PRATA igual) mas **desce em BRONZE** (1.0→0.7 — único afrouxamento da
tabela, e só nesse degrau). ADX sobe nos 3 (22→25 OURO, 18→20 PRATA, 15→18 BRONZE). Distância MM21 da OURO
volta a apertar de `<=6%` pra `<=3%` (era esse valor antes da V3). RSI absoluto, Kalman alinhado e MM50
favorável (gates da V3 em OURO/PRATA) saíram da classificação — não estavam na tabela nova do usuário, e a
zona de RSI já é gate da própria cascata de sinais (REGRA #1, `rsi_zona_long/short` 75/25) antes do sinal
chegar até `classificar_v2()` — remover esse check redundante aqui não reabre brecha real. "Conf" (campo
da tabela do usuário) não tem checagem própria: é redundante com Score (`confiança = score_inst-10` em
`notify.py`), confirmado matematicamente equivalente em todos os 3 degraus da tabela do usuário antes de
aplicar (ex: OURO Score≥85/Conf≥75 → 85-10=75, bate exato).

### Contradição descoberta e corrigida — piso universal de RVOL pré-classificação (`config.py`/`cycles.py`)
Antes de aplicar, auditei `cycles.py` por dependências da V3 e achei um problema real: o gate universal de
RVOL que roda **antes** de `classificar_v2()` ser chamado (`executar_ciclo()` e `executar_ciclo_mtf()`,
`_rvol_min_tf = max(RVOL_MIN_BY_TF.get(tf,0.80), RVOL_MIN_EXEC)`) calculava `max(0.70-0.80, 1.0) = 1.0`
pros dois timeframes — mais alto que o novo piso de BRONZE (`RVOL>=0.7`). Sem ajuste, o único afrouxamento
real da tabela nova (BRONZE RVOL 1.0→0.7) seria código morto: nenhum candidato com RVOL entre 0.7-1.0
chegaria a `classificar_v2()`, sempre bloqueado antes pelo piso universal antigo.

Fix: `config.py` `RVOL_MIN_EXEC` `1.0`→`0.7` e `RVOL_MIN_BY_TF["1h"]` `0.80`→`0.70` (30m já estava em 0.70)
— alinha os dois pisos universais ao degrau mais baixo da nova tabela (BRONZE), deixando a classificação
em si (`classificar_v2()`) ser o gate real de qualidade por tier, como já era a intenção da V3.

### O que NÃO mudou
- Regras de execução por tier em `cycles.py` (OURO sempre opera, PRATA exige H1 alinhado, BRONZE exige H1
  alinhado OU score_inst>=70, sessão perigosa exige OURO) — só consomem a string `"OURO"/"PRATA"/"BRONZE"`
  devolvida por `classificar_v2()`, não dependem dos números internos do tier.
- Bloqueios universais de RSI (>80 bloqueia LONG, <20 bloqueia SHORT), `ADX_MIN_GLOBAL` (15), MM200 —
  nenhum mencionado na tabela do usuário, mantidos como estavam na V3.
- Saída em 4 estágios (TP1=1.5R/TP2=3R/TP3=5R/runner), gestão de stop, alavancagem, tamanho de posição —
  nenhum tocado por este ajuste, mesma régua da V3.
- Modo `SIGNAL_MODE=="INSTITUCIONAL"` (separado, com sua própria grade/risco/cooldown) — intocado.

### Saída — `notify.py calcular_stop_tp()`/`enviar_sinal()`, 4 estágios fixos (substitui os 3 da V2)
- **TP1 = 1.5R fixo** → fecha 30% da posição, stop conceitual vai pra BE (break-even)
- **TP2 = 3R fixo** → fecha 40%
- **TP3 = 5R fixo** → fecha 20%
- **Restante (10%, "runner")**: não tem alvo de preço fixo — segue tendência. Resolvido por `cycles.py
  _checar_runners()` (candle fresco, não ticker simples): só encerra quando os **3 critérios batem
  juntos** — MM10 cruza abaixo da MM21 (LONG) / acima (SHORT) **E** fluxo (DNA Flow/Trendilo) perde força
  na direção do trade **E** volume cai (`RVOL<1.0`). Os 3 múltiplos (1.5/3/5) são **fixos pelo documento do
  usuário**, independente de tier/grade/fonte — substitui a tabela por tier (OURO=4R/PRATA=3R) da V2.
- O teto estrutural de TP1 que existia na V2 (nunca passar de ~92% da distância até o swing) **foi
  removido** — a V3 pede R-múltiplos fixos sem condicionar a estrutura, então o TP1 hoje é sempre
  `entrada ± 1.5×risco`, sem cap. O cálculo do stop em si (`mult_atr`, stop estrutural) ficou intocado —
  só os múltiplos/splits de alvo mudaram.

### Rastreamento de posição — 4 estágios (`state.py`)
- Antes (V2): 3 estágios (aberta → `tp1_atingido` → `tp1_atingido`+`tp2_atingido`="runner").
- Agora (V3): 4 estágios (aberta → `tp1_atingido` → `+tp2_atingido` → `+tp3_atingido`="runner").
  `registrar_posicao_aberta()` ganhou `tp3`/`r2`/`r3` (substituindo o `r_final` único da V2).
  `verificar_posicoes_abertas()` resolve TP1/TP2/TP3 no mesmo poll de preço se o preço já passou de vários
  de uma vez (mesmo padrão cascateado da V2). `fechar_runner()` (intocado na assinatura) agora só é chamado
  depois que `tp1_atingido`+`tp2_atingido`+`tp3_atingido` os 3 são verdadeiros — devolve `resultado=
  "TP3_RUNNER"` (renomeado de `"TP2_RUNNER"`).
- R realizado novo: `TP3_RUNNER = r1*0.3 + r2*0.4 + r3*0.2 + r_runner*0.1`, onde `r_runner` é calculado no
  momento do fechamento do runner, igual à V2. `TP1_BE` realiza `r1*0.3` (era `r1*0.5` na V2, porque agora
  o TP1 só fecha 30%, não 50%). Os resultados antigos `"TP2"` (binário, V1) e `"TP2_RUNNER"` (V2, 3
  estágios) continuam existindo só como branches legados em `registrar_resultado()` pra qualquer posição
  que já estivesse cacheada em `last_signals.json` antes deste commit (usam fallback `p.get("r2",
  p.get("r_final", 3.0))` já que posições antigas não têm `r2`/`r3` gravados) — código novo nunca produz
  `TP2`/`TP2_RUNNER`.
- `_CAMPOS_RESULTADOS` (schema do `resultados_log.csv`) **continua sem alteração** (mesma regra da V2) —
  `tp3`/`r2`/`r3`/`r_runner`/`classificacao` ficam só no JSON de estado, não em colunas novas do CSV.
- `resumo_resultados()` (winrate) passou a contar `TP2_RUNNER` e `TP3_RUNNER` como vitória, junto com
  `TP1_BE`/`TP2` (antes só esses dois contavam — gap real seria subestimar o winrate real assim que os
  primeiros runners V3 começarem a fechar).
- Circuit breaker institucional (`_stops_consecutivos_inst`) zera em `TP1_BE`/`TP2`/`TP2_RUNNER`/
  `TP3_RUNNER` (lista de vitórias ampliada, mesmo motivo do winrate acima).

### `auto_backtest.py` — acompanha a nova régua
`_simular_forward()` usa `tp1`/`tp3` (pulou o `tp2` intermediário de propósito — aproximação, não testa o
candle-a-candle de TP2 separado) e os pesos `r1*0.3 + r2*0.4 + r3*0.3` quando TP3 é atingido (30% final
aproxima TP3+runner juntos). Coluna `n_tp2` do CSV (schema legado, não alterado) hoje representa "bateu
TP3+runner aproximado", não mais o TP2 literal.

### O que NÃO mudou
- Tamanho de posição (`RISK_BY_GRADE`/`RISK_INSTITUCIONAL_POR_GRADE`)
- Alavancagem (REGRA #4 + TETO CONSERVADOR DE ALAVANCAGEM)
- Cálculo do stop em si (`mult_atr`, stop estrutural)
- A cascata de 12 sinais em `analyze.py:detectar_sinais()` — a classificação V3 roda **depois** que um
  sinal já foi detectado, é uma camada adicional de gate/saída, não substitui nenhuma condição de entrada
  da cascata. REGRA #1 (`rsi_zona_long/short` 75/25 dentro da própria cascata) também intocada — só o piso
  universal pós-cascata em `cycles.py` afrouxou pra 80/20.
- Modo `SIGNAL_MODE=="INSTITUCIONAL"` (separado, AJUSTE INSTITUCIONAL ELITE + DNA+GAUSS INSTITUCIONAL V2
  acima) — continua com sua própria grade (`GRAUS_PERMITIDOS_INSTITUCIONAL`), risco, cooldown e circuit
  breaker, nenhum desses tocado pela V3.

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
A saída real do bot tem 4 estágios desde a V3 (TP1=1.5R/30%→BE, TP2=3R/40%, TP3=5R/20%, 10% final "runner"
via MM10/MM21+fluxo+volume — ver CLASSIFICAÇÃO INSTITUCIONAL V3 abaixo). O backtest aproxima o TP3+runner
como um só evento (fecham juntos, sem tracking candle-a-candle do trailing) — suficiente pra medir taxa de
STOP e winrate de entrada, **não é réplica exata** do `resultados_log.csv` real. Decisão de ajuste de
filtro/gestão deve sempre priorizar o dado real (`resumo_resultados()`) quando a amostra real for
suficiente — o backtest automático é um indicador adiantado (*leading indicator*) pra calibração rápida
enquanto a amostra real ainda é pequena.

### Por timeframe (`state.py resumo_resultados()` / `cycles.py _enviar_diagnostico()`)
Resposta à pergunta "operar só H1 fica mais limpo?" (22/06): em vez de decidir sem dado, o resumo de
resultado real de 24h passou a também agregar por `timeframe` (campo que já existia no schema do
`resultados_log.csv`, só não era agregado) — aparece como `por timeframe: ...` no diagnóstico horário quando
houver mais de 1 timeframe na amostra. Quando a amostra acumular trades suficientes em 30M e 1H, esse
detalhamento mostra objetivamente se um dos dois timeframes está puxando o winrate pra baixo, antes de
restringir `TIMEFRAMES` pra só `1h` (mudança que hoje seria especulação, não dado).

---

## TIMEOUT DO JOB MENOR QUE O CRON — 2º CASO REAL DE GAP (autorizado 22/06)

Usuário reportou "bot não está enviando nada" — investigação (`mcp__github__get_job_logs`, linha a linha,
não só status do run) confirmou que o envio em si **funciona**: achou diagnósticos sendo entregues com
`ok:true` do Telegram tanto num run de 6min cancelado quanto num de 5h25min, incluindo um exatamente às
06:30 UTC (= 3:30 BRT, confirmado pelo usuário como a última mensagem recebida). `getChat` confirmou que
`TG_CHATID` aponta pro grupo certo, com permissão de postar — não era um Secret errado.

A causa raiz real: o run iniciado 01:11 UTC ocupou o runner até 06:37 (bateu o timeout do step "Rodar bot",
que era 325min) — e os ticks de cron de 07h e 08h foram **pulados** pelo GitHub Actions (comportamento
documentado: cron agendado não dispara se o run anterior ainda está ocupando o concurrency group), abrindo
um buraco de 2h11min sem nenhum run até o próximo `workflow_dispatch` manual às 08:48. Isso é a mesma causa
raiz já registrada uma vez nesta sessão (ver comentário em `bot.yml`, redução de cron de 2h→1h) — só que
reduzir o **cron** não resolve, porque o problema real é que o **timeout do job (325min) é maior que o
intervalo do cron (60min)**: qualquer run que dure o timeout completo garante matematicamente que pelo menos
um tick agendado vai cair "no meio" do runner ocupado e ser descartado.

### Fix aplicado (`bot.yml`)
- `timeout-minutes` do job (`scanner`) `330` → `58`
- `timeout-minutes` do step "Rodar bot" `325` → `55`
- Efeito: cada execução do bot (mesmo em `LOOP_MODE=true`) sempre termina sozinha antes do próximo tick
  horário do cron — o concurrency group nunca fica ocupado no momento em que um novo tick deveria disparar,
  eliminando a causa raiz do buraco (não só encurtando o timeout, que só reduziria o tamanho do buraco sem
  resolvê-lo). `LOOP_MODE` continua funcionando normalmente dentro da janela de 55min (vários ciclos de
  `CYCLE_INTERVAL=300s` cada); o cron horário assume a continuidade entre janelas.
- Não foi necessário mudar `TG_CHATID`/`TG_TOKEN` — ambos já estavam corretos (confirmado via `getChat` e
  via o timestamp 06:30 UTC citado pelo usuário batendo exatamente com um diagnóstico real do log).
- Pedido explícito do usuário nesta sessão: parar de disparar `workflow_dispatch` manualmente após cada
  ajuste (a cascata de disparos manuais + cron já estava causando cancelamentos em cadeia) — este fix foi
  commitado/pushado mas **sem** disparo manual automático; o próximo tick de cron (a cada hora) já assume
  a partir daqui.
- ⚠️ Nota de consistência (22/06, sessão seguinte): esse pedido contradiz a frase "Após qualquer ajuste de
  código: Sempre disparar o bot automaticamente... autorizado permanentemente" da REGRA #0 no topo deste
  arquivo. Auditoria confirmou o problema é real e recorrente: `mcp__github__actions_list` mostrou 3 runs
  consecutivos `cancelled` no mesmo dia, exatamente o padrão de disparos manuais em sequência cancelando o
  run anterior via concurrency group. Decisão (sessão 22/06, ajuste de `vol_secando`): quando o ajuste for
  pequeno/incremental e já existir um run em andamento, **não** disparar de novo — deixar o cron horário
  assumir. Só disparar manual de novo se o usuário pedir dado imediato ou não houver run em andamento.

---

## AUDITORIA DE OPORTUNIDADES PERDIDAS — vol_secando AFROUXADO (autorizado 22/06)

Pedido do usuário: avaliar se está perdendo boas oportunidades, **sem endurecer** mais nada — afrouxar até
um limite que ainda garanta sinal de qualidade (não afrouxar tudo de qualquer jeito). Em vez de adivinhar,
auditei um run real completo via `mcp__github__get_job_logs` (run 27976146741, 18:49-19:44 UTC, 12 ciclos,
~55min, dezenas de moedas por ciclo, run pego ANTES do print de resultado 24h ter sido mostrado):

- **3 dos 12 ciclos (25%) tiveram zero análise** — BTC H1 em regime neutro (`_btc_h1_regime_neutro()`)
  bloqueia LONG e SHORT em **todas** as moedas, não só nas correlacionadas a BTC. Genuíno (mercado sem
  direção no BTC), não é bug — registrado aqui só como contexto, não alterado nesta rodada.
- Nos outros 9 ciclos: **669 candidatos LONG/SHORT bloqueados** por `seguro_long`/`seguro_short` ou
  condição própria do sinal, **zero sinais reais disparados** no run inteiro. Top motivos (contagem real):
  1. `seguro=F(vol_sec...)` — 268 ocorrências (~40% de todos os bloqueios) — de longe o maior bloqueador
  2. `ha1=F` — 142 (Heikin-Ashi última vela, usado por SCOUT — trade-off já aceito, ver REGRA #2)
  3. `fluxo<N/4` — 135 (SCOUT, trade-off já aceito, ver REGRA #2 "torna SCOUT bem mais raro por desenho")
  4. `adx<15` — 105 (piso global `ADX_MIN_GLOBAL`, mercado genuinamente sem força de tendência)
  5. `macd_r=F` — 67 (condição própria de cada sinal)
  6. `seguro=F(exaustao)` — 60 (anti-chasing, intencional)
  7. `lateral` — 44 (BB squeeze)
  8. `rsi_zona` — ~50 no total somado (REGRA #1, intocada — não alterar sem pedido específico)

### Fix aplicado — só o maior blocker, isolado dos outros
`vol_secando` (`analyze.py`, dentro de `calcular_indicadores()`) exigia volume da última vela `< 25% da
média` **E** `< 50% do mínimo das últimas 3 velas` — limiar apertado demais pro próprio objetivo do filtro
(capturar esgotamento *extremo* de volume, não qualquer fade moderado). Sozinho respondia por ~40% de todo
bloqueio de `seguro_long`/`seguro_short` (usado por PULLBACK, CROSS, BB_BREAK, SM_SWEEP, SETUP, DIV,
REBOUND, FLEX, SCOUT — praticamente toda a cascata). Afrouxado pra `< 18% da média` **E** `< 40% do mínimo
das últimas 3 velas` — exige um fade ainda mais extremo antes de bloquear, sem remover a defesa.

### O que NÃO foi tocado nesta rodada (de propósito — mudança isolada pra medir o efeito real)
- `ha_bull_1`/`fluxo` do SCOUT — já é trade-off aceito explicitamente (REGRA #2, "SCOUT bem mais raro por
  desenho — aceito explicitamente pelo usuário")
- `ADX_MIN_GLOBAL` (15) — já é o piso mínimo desde a V3, abaixo disso deixaria de ser "força de tendência"
- REGRA #1 (RSI zona 75/25) e `seguro_long/short` (stoch saturado, exaustão, bb_topo/fundo) — defesas
  anti-chasing ligadas a incidentes reais documentados (BB_BREAK CVX/ASTER/WUSDT) — não tocadas sem pedido
  explícito do usuário nomeando especificamente esse filtro
- Filtro de regime BTC H1 (`_btc_h1_regime_neutro`) — bloqueia 25% dos ciclos por completo, candidato real
  a próxima rodada de afrouxamento se o usuário confirmar que quer revisar esse específico
- Validar com o próximo run real (via cron, sem disparo manual — ver nota de consistência acima) se o
  afrouxamento do `vol_secando` já é suficiente pra gerar sinal sem voltar a piorar o winrate/STOP-rate
  (winrate real 24h estava em 37% antes deste ajuste — ver "RASTREAMENTO DE RESULTADO").

---

## AUDITORIA DE DIA INTEIRO SEM SINAL — BTC_REGIME_ADX_MAX AFROUXADO (22/06)

Usuário perguntou diretamente: "em 300 criptomoedas no dia inteiro não deu nem um sinal?" — auditoria
real (não suposição) de todos os runs completos de 2026-06-22 (00:00-22:19 UTC, via `mcp__github__get_job_logs`,
6 runs completos + 2 cancelados spot-checados) confirmou: **zero sinais reais em todo o dia**, em qualquer
run, qualquer hora.

Duas causas reais, sem sobreposição de horário:
- **Madrugada/noite** (00:27-08:48 UTC e 20:18-21:52 UTC — várias horas seguidas): `_btc_h1_regime_neutro()`
  bloqueava 100% dos ciclos, todas as moedas, sem nem chegar a analisar (BTC H1 ADX~18-19, RSI~48-54 —
  dentro da faixa neutra antiga ADX<20/RSI 45-55).
- **Tarde** (14:02-18:49 UTC, mercado ativo): análise rodava normal, mas `vol_secando`/`exaustao` saturavam
  `seguro_long/short` — mesma causa já documentada em "AUDITORIA DE OPORTUNIDADES PERDIDAS" acima (fix do
  `vol_secando` já estava aplicado mas ainda não tinha passado por um run completo pra validar).

(Um run "success" de 4s às 11:59 UTC não é real — é o autoteste `TEST_MODE` do bot (`executar_teste()` em
`cycles.py`), manda 2 sinais fake só pra validar entrega no Telegram, não conta como scan de mercado.)

### Fix aplicado — só o filtro de regime BTC, isolado do vol_secando já tocado antes
`config.py BTC_REGIME_ADX_MAX`: `20` → `15` — alinhado ao piso global `ADX_MIN_GLOBAL` já usado no resto do
sistema (não inventei um número novo). Exige BTC genuinamente mais flat (ADX<15, não <20) antes de zerar o
ciclo inteiro pra todas as moedas. `BTC_REGIME_RSI_MIN/MAX` (45-55) intocados — mudança isolada numa
variável só, mesmo padrão do fix anterior, pra poder medir o efeito de cada filtro separadamente.

### O que NÃO foi tocado nesta rodada
- `vol_secando` — já afrouxado na rodada anterior, ainda sem run completo pra validar o efeito
- RSI/ADX/RVOL por sinal individual na cascata (`analyze.py`) — não identificados como bloqueador
  dominante nesta auditoria (o gargalo real era o filtro de regime zerando o ciclo inteiro, não os
  critérios por sinal)
- Validar com o próximo run completo (cron ou disparo manual) se a combinação dos dois fixes já é
  suficiente pra gerar pelo menos 1 sinal real, antes de seguir afrouxando outros filtros.

---

## "O QUE FALTA PRA DAR SINAL" — VALIDAÇÃO DOS 2 FIXES ANTERIORES + exaustao AFROUXADO (22/06)

Usuário perguntou diretamente o que ainda falta pra disparar sinal. Validado com o run real seguinte aos
2 fixes anteriores (vol_secando + BTC_REGIME_ADX_MAX, run `27990867580`, 23:24-00:19 UTC, 12 ciclos, 79
moedas/ciclo, **305 moedas no scanner** — confirma o "300 criptomoedas" que o usuário mencionou):

- **Filtro de regime BTC: 0 ocorrências neste run** (era o bloqueador #1 de ciclo inteiro antes do fix de
  ADX_MAX 20→15) — fix anterior funcionou, BTC não ficou neutro em nenhum momento deste run.
- Mas **ainda 0 sinais em 12/12 ciclos** — 665 candidatos bloqueados por `seguro_long/short`:
  1. `vol_secando` — 331 (49.8%) — **mesmo após o afrouxamento anterior** (0.25/0.5→0.18/0.40), continua
     o maior bloqueador isolado. Run caiu majoritariamente dentro da sessão perigosa (22h-08h UTC, REGRA
     #3) — pode ser parcialmente volume genuinamente fino no overnight, não só filtro apertado demais;
     recomendo validar num run de horário ativo (13h-21h UTC) antes de afrouxar uma 3ª vez.
  2. `exaustao_topo/fund` — 240 (36%) — 2º maior, ainda não tinha sido tocado.
  3. `rsi` (StochRSI absoluto) — 36 | `bb_topo/fund` — 26 | `stoch` — 20 | `ext_e21` — 12.
- Juntos, `vol_secando`+`exaustao` somam **85.7%** de todo bloqueio de `seguro_long/short`.

### Fix aplicado nesta rodada — exaustao_topo/fund (analyze.py)
Pavio (`sombra_sup`/`sombra_inf`, proporção do range da vela) `>0.40` → `>0.55` — exige rejeição de pavio
bem mais extrema antes de bloquear como "exaustão", mesmo padrão de mudança isolada de uma variável só.
O buffer de preço (`bb_range*0.02`) não foi tocado.

### O que NÃO foi tocado nesta rodada (de propósito)
- `vol_secando` — já tocado 2x (incluindo a rodada anterior); preferi não tocar uma 3ª vez até validar se
  o problema é mesmo o limiar ou se é genuinamente volume fino do horário noturno (sessão perigosa)
- StochRSI (`stoch_esticado_up/down`), `bb_topo/fund`, `ext_acima/abaixo_e21` — bloqueadores bem menores
  (3-5% cada), não justificam ainda outra mudança isolada
- Validar com o próximo run real (de preferência em horário ativo, 13h-21h UTC) se os 3 fixes somados
  (BTC regime + vol_secando + exaustao) já produzem pelo menos 1 sinal real.

---

## GAUSS+DNA v5.0 — GESTÃO DE RISCO EM DÓLAR FIXO (autorizado 23/06, banca real $90)

Substitui `CAPITAL`/`RISK_PCT`/`RISK_BY_GRADE`/`RISK_SCOUT`/a alavancagem dinâmica 3x-50x (REGRA #4) e a
saída em 4 estágios (V3/V4) por uma régua mais simples pra banca pequena: lote fixo em dólar por tier
(`classificar_v2()` PRATA/BRONZE — OURO desabilitado, exige banca>$500) e saída em 2 estágios.

- **Tamanho de posição** (`notify.py enviar_sinal()`): `MARGEM_POR_TIER_V5` = PRATA $30 / BRONZE $15
  (`config.py`). 2ª posição simultânea opera com `lote_reduzido=True` (margem pela metade) — parâmetro
  novo em `enviar_sinal()`, decidido em `cycles.py` por `len(estado["_posicoes_abertas"]) >= 1` no momento
  do envio.
- **Alavancagem dinâmica por tier, range 5x-20x** (autorizado 23/06, pedido "alavancagem de 5 x até 20
  pode ativar sinal real" — substitui o `ALAVANCAGEM_V5=3x` fixo original do dia): `config.py
  ALAVANCAGEM_POR_TIER_V5 = {"BRONZE": 5, "PRATA": 20, "OURO": 20}` — BRONZE (qualidade menor) no piso do
  range, PRATA (tier ativo mais alto hoje, já que OURO é inatingível nesta versão) no teto. `notify.py`
  consome via `ALAVANCAGEM_POR_TIER_V5.get(classificacao, 5)` (fallback 5x, mesmo padrão defensivo do
  fallback de `margem`). Tamanho de margem em dólar por tier (`MARGEM_POR_TIER_V5`) não muda — só o
  multiplicador de alavancagem deixou de ser fixo.
- **Saída em 2 estágios**: TP1 = 1:1R fecha 50%, stop conceitual vai pra BE; os 50% restantes seguem em
  trailing (50% do ganho desde o TP1, piso BE) — resolvido tick a tick em `state.py
  verificar_posicoes_abertas()`, resultado `TP1_TRAIL`. `auto_backtest.py` usa a mesma régua.
- **Circuit breakers globais** (`cycles.py _v5_bloqueio()`, checado em `executar_ciclo()` e
  `executar_ciclo_mtf()` antes de qualquer envio, independente de `SIGNAL_MODE`):
  - Sem trade nos primeiros `NO_TRADE_PRIMEIROS_MIN_V5=15min` de cada vela H1 (UTC)
  - Perda diária acumulada >= `PERDA_MAX_DIA_V5=$5.40` (~6% da banca) bloqueia novas entradas até o dia
    UTC virar (`estado["_v5_pnl_dia"]`, resetado por `estado["_v5_dia"]`)
  - 2 `STOP` consecutivos → pausa de `PAUSA_2_PERDAS_V5=7200s` (2h)
  - Máximo `MAX_POSICOES_V5=2` posições simultâneas abertas
  - P&L em dólar de cada posição fechada = `valor_risco * r_realizado` (`valor_risco` calculado em
    `enviar_sinal()` a partir do lote fixo e da distância real do stop, gravado na posição via
    `registrar_posicao_aberta()`, devolvido por `registrar_resultado()` agora que essa função `return
    r_realizado` em vez de nada) — acumulado em `cycles.py _atualizar_resultados()`.
- Gestão (cálculo do stop em si, `mult_atr`, stop estrutural) e a cascata de 12 sinais em `analyze.py`
  **intocadas** — este ajuste é só tamanho de posição, saída e circuit breaker, mesmo padrão dos ajustes
  anteriores de risco já documentados acima.

---

## AJUSTES PÓS-MERGE v5.0 — vol_secando e stoch_esticado (autorizado 23/06)

Pedido do usuário: zero sinais em runs reais após o merge de v5.0 — "ajuste até dar sinal, sem pergunta,
sem gastar mais de 1min por ajuste". Dois ajustes cirúrgicos aplicados em `analyze.py`, ambos validados
contra diagnóstico real (log do run / mensagem de diagnóstico do Telegram), nenhum dos dois toca REGRA #1
(`rsi_zona_long/short`) nem REGRA #5 (`liq_topo`/`liq_fundo`).

1. **`vol_secando`** (linha ~212): run de 11 ciclos pós-merge (`28001700665`) mostrou `vol_sec` ainda como
   o bloqueador mais frequente de `seguro_long/short`, mesmo após o afrouxamento de 22/06 (0.25/0.50 →
   0.18/0.40). Afrouxado de novo: `volumes[-1] < vol_ma*0.10 and volumes[-1] < min(vol3)*0.25` (era
   `0.18`/`0.40`) — exige fade de volume ainda mais extremo antes de bloquear.
2. **`stoch_esticado_up/down`** (linha ~115-118): mesmo run mostrou candidatos LONG fortes (GWEI +135,
   BDX +128/+145) com RSI dentro da zona REGRA #1 (62-70, bem abaixo do teto 75) travados isoladamente por
   StochRSI saturado em combinação com `bb_topo`. Afrouxado em 2 passos no mesmo dia: `stoch_rsi>0.80 and
   rsi>58` → `>0.90 and rsi>65` (1º ajuste, resolveu GWEI) → `>0.95 and rsi>65` (2º ajuste, mesmo dia,
   diagnóstico seguinte mostrou BDX RSI70/stoch=0.93 ainda bloqueado pelo teto de 0.90). `stoch_esticado_down`
   só teve o lado RSI ajustado (`<35`→`<30`) — nenhum candidato SHORT real ficou bloqueado isoladamente por
   esse lado nos diagnósticos auditados (os SHORT bloqueados no período eram todos por REGRA #1 genuína,
   RSI<25 num dump, e essa parte não foi tocada).
3. **Critério de quando afrouxar mais**: só ajustar quando o diagnóstico real (log do run ou mensagem do
   Telegram) mostrar um candidato específico, com score relevante e RSI dentro da REGRA #1, travado
   isoladamente por esse filtro auxiliar (stoch/vol_sec) — nunca afrouxar "no escuro" sem um caso real
   apontado pelo diagnóstico. Padrão a seguir caso o usuário peça novo ajuste de urgência: ler o diagnóstico
   colado, achar o motivo de bloqueio mais próximo de um candidato forte, e tocar só essa variável (mesmo
   padrão dos 2 ajustes acima) — não os bloqueios genuínos de REGRA #1/REGRA #5/ADX lateral, que são
   proteção de capital, não bug.

### Diagnóstico — números de fechados/STOP/winrate/R sempre explícitos (23/06)
Usuário exigiu ver fechados/STOP/winrate/R médio **sempre** como número, não frase — `cycles.py
_enviar_diagnostico()`, linha "Resultados (24h)": quando `resumo_resultados()` devolve `None` (sem trade
fechado na janela), a linha agora é `"0 fechados — STOP:0 TP:0 — winrate: 0% — R medio: 0.00"` em vez da
frase antiga "nenhum fechado ainda". Quando há dado real, o formato já mostrava os 4 números (não mudou).

---

## ESTRATÉGIA DE TESTE PARALELA — "O QUE DÁ CERTO" (autorizado 23/06)

Pedido do usuário: *"tem como criar uma estratégia separada teste pra agente testando o que dá certo"* —
quis uma estratégia paralela à real, pra descobrir empiricamente quais sinais hoje bloqueados pela camada
de confirmação V3 (`classificar_v2()`) teriam dado resultado bom. Perguntado se devia ser modo invisível
(nunca chega no Telegram) ou visível — usuário respondeu explícito: **"quero que vá para o telegram para
acompanhar"**. Implementado visível, com tag clara de "não é sinal real".

### Onde entra no pipeline (`cycles.py`)
Não é uma cascata de detecção nova — reaproveita exatamente os candidatos que `analyze.py` já decidiu serem
sinais válidos (passaram REGRA #1 `rsi_zona`, REGRA #5 `liq_topo/fundo`, e os pisos universais
`ADX_MIN_GLOBAL`, `RVOL_MIN_EXEC`, RSI 80/20, MM200, H4) mas que a camada de confirmação V3 ainda bloqueia
nesses 4 pontos exatos, tanto em `executar_ciclo()` quanto em `executar_ciclo_mtf()`:
1. `classificacao not in (OURO,PRATA,BRONZE)` — "v3=none"
2. Sessão perigosa exige OURO e o candidato só tem PRATA/BRONZE — "sessao perigosa"
3. PRATA sem H1 alinhado — "prata sem H1"
4. BRONZE sem H1 alinhado — "bronze sem H1"

Em cada um desses 4 pontos, em vez de só `continue`, chama `_tentar_sinal_teste()` (`cycles.py`) — que
reenvia o mesmo candidato via `enviar_sinal()` só que com `fonte=f"TESTE:{fonte_real}:{motivo_bloqueio}"`.
`notify.py` já tinha o tratamento `fonte.startswith("TESTE")` (usado antes só pelo `executar_teste()` de
autoteste de conectividade) → tag fixa "🧪 TESTE — NÃO OPERAR" na mensagem, deixando claro que não é sinal
real. Cooldown e cap por ciclo são próprios e independentes do real (chaves `teste_...`,
`MAX_SINAIS_TESTE_POR_CICLO=3` em `config.py`) — não consome o cooldown nem os limites de sinal real.

### Isolamento do dinheiro real (crítico — não pode interferir na conta real)
- **Não passa** por nenhum gate de risco/dinheiro real: `risco_ciclo`/`MAX_CYCLE_RISK`, `_v5_bloqueio()`
  (perda diária/circuit breaker de 2 stops), `MAX_POSICOES_INSTITUCIONAL`, `STOPS_CONSECUTIVOS_PAUSA`,
  `MAX_SCOUT/LONG/SHORT_PER_CYCLE` — todos esses só protegem o caminho real, e o de teste roda só nos 4
  pontos onde o sinal real já teria sido descartado de qualquer forma.
- Tracking de posição é uma lista própria, `estado["_posicoes_teste"]` (separada de
  `estado["_posicoes_abertas"]`) — `state.py` `registrar_posicao_aberta()`/`verificar_posicoes_abertas()`
  ganharam o parâmetro `chave_estado` (default `"_posicoes_abertas"`, sem mudar comportamento real) pra
  reaproveitar a mesma régua de TP1/trailing/STOP sem duplicar lógica.
- Resultado fechado grava em `teste_resultados_log.csv` (`config.TESTE_RESULTS_FILE`), arquivo **separado**
  de `resultados_log.csv` — `state.py` `registrar_resultado()`/`resumo_resultados()` ganharam o parâmetro
  `arquivo` (default `RESULTS_FILE`, comportamento real intocado) pelo mesmo motivo. `cycles.py
  _atualizar_resultados_teste()` (chamada em `main()` logo depois da real) resolve essas posições de teste
  a cada ciclo, sem tocar em nenhum contador de dinheiro real (`_v5_pnl_dia`, `_stops_consecutivos_inst`).
- `bot.yml`: `teste_resultados_log.csv` adicionado ao cache (`actions/cache/restore`/`save`), mesmo padrão
  de `resultados_log.csv`/`backtest_log.csv`, senão o dado seria perdido a cada run isolado do Actions.

### Diagnóstico horário
Linha nova `🧪 Teste (24h): N fechados — winrate X% — R medio Y` (via `resumo_resultados(arquivo=
TESTE_RESULTS_FILE)`), anexada depois do "Backtest auto" — comparável diretamente com a linha "Resultados
(24h)" real, pra eventualmente decidir se algum dos 4 bloqueios da V3 está custando sinais bons (winrate
teste melhor que o real sugere afrouxar aquele gate especificamente) ou se a V3 está certa em bloquear
(winrate teste pior confirma o gate como proteção válida).

### O que NÃO foi tocado
A cascata de 12 sinais (`analyze.py`), REGRA #1/REGRA #5, os pisos universais pré-classificação (ADX/RVOL/
RSI/MM200/H4) — a estratégia de teste só atua DEPOIS que esses já passaram, nunca os afrouxa. Tamanho de
posição/alavancagem real (v5.0) também intocados — posições de teste usam a mesma fórmula só pra ter um R
realizado comparável, nunca abrem posição real na corretora.

---

## REGRA #6 — PRIORIDADE: PEGAR O MOVIMENTO NO COMEÇO, NUNCA ATRASADO (autorizado 23/06)

Diretriz permanente pra qualquer ajuste futuro de detecção de sinal: entre dois candidatos, o sistema deve
sempre priorizar pegar o movimento **no início** (primeira confirmação real) sobre esperar confirmação
extra que só chega depois que o movimento já andou — moeda que já caiu/subiu 5-9% (ex: print real 23/06:
SPCX -8.4%, ALLO -5.8%, HUS -9.6%) já passou da janela de entrada útil; não dá pra "resolver" isso
retroativamente, o ganho real está em garantir que o *próximo* movimento seja pego mais cedo.

Mecanismos já existentes que servem exatamente esse objetivo (não são desculpa, é o que já impede entrada
tardia hoje): REGRA #1 (rsi_zona), `nao_overext_long/short`, `rsi_nao_chasing_long/short` (Fix 1, 21/06) —
bloqueiam entrar DEPOIS que o movimento já esticou. O lado que falta (entrar MAIS CEDO, não só evitar
entrar tarde) é o candidato natural pra próximo ajuste real: usar o próximo diagnóstico que mostrar um
candidato forte (score alto, RVOL subindo) bloqueado só por confirmação de 1 candle (ex: `ha1=F` sozinho,
sem nenhum outro bloqueio de mercado) como caso concreto pra afrouxar a exigência de confirmação nesse
ponto específico — mesmo padrão cirúrgico já usado hoje (vol_secando, stoch_esticado).

## AJUSTE 23/06 — perto_bb_topo/fund afrouxado (caso real KMNO)

Run real (`28023405483`, 2 ciclos): KMNO score+120 RSI64.2 ADX21.1 Kalman UP travado isoladamente em
`seguro=F(bb_topo)` — único filtro bloqueando esse candidato (não é REGRA #1 nem REGRA #5). `analyze.py`:
`perto_bb_topo` (`pos_bb>0.97`) → `pos_bb>0.99`; `perto_bb_fund` (`pos_bb<0.03`) → `pos_bb<0.01`. OPG
(score+128) também era candidato forte mas travava em `bb_topo`+`stoch=1.00` junto — bloqueio duplo, não
isolado, não tocado nesta rodada. Confirmado no run seguinte que o fix funcionou (KMNO saiu de
`seguro=F(bb_topo)` pra `sem detalhe`) — mas ainda não disparou sinal real: `sem detalhe` indica que o
bloqueio real está dentro da própria condição de algum dos 12 sinais tipados (`detectar_sinais()`), não
nos checks genéricos que `analisar()` decompõe (ver ajuste seguinte).

## AJUSTE 23/06 — diagnóstico "sem detalhe" decomposto em gatilho real

Mesmo caso KMNO (e ZRO, RSI~56-57 ADX~18.3 K:UP, mesmo padrão): depois do fix de `perto_bb_topo`, o
candidato passa em todos os checks genéricos de `analisar()` (macd_bull_r, ha_bull_1, adx>=15, não
lateralizado, seguro_long, rsi_zona, fluxo>=2) mas ainda não produz sinal — ou seja, o bloqueio real está
escondido dentro de uma das 12 condições tipadas de `detectar_sinais()` (PULLBACK precisa de toque recente
na EMA10/21; CROSS precisa de cruzamento de médias; SETUP precisa de `macd_recuperando`, ou seja MACD
*recuperando* de negativo, não apenas positivo contínuo; FLEX/SCOUT exigem ADX>=25 fixo) — nenhuma dessas
é satisfeita por uma tendência já estabelecida e contínua (ADX moderado 18-21, sem gatilho de entrada
fresco), e o diagnóstico genérico de `analisar()` não decompunha isso, só caía no fallback `"sem detalhe"`.

Fix: quando nenhum dos checks genéricos acima sinaliza nada (`not b`), `analyze.py:analisar()` agora
decompõe o motivo real testando os gatilhos específicos dos sinais mais plausíveis pro perfil ADX
moderado/RSI não-extremo (`pullback_bull`/`bear`, `algum_cross_bull`/`bear`, `macd_recuperando`/
`macd_esgotando`, `liq_long`/`fundo` ou `liq_short`/`topo`, `adx<25`) — log passa a mostrar
`gatilho:pullback=F,cross=F,...` em vez de `sem detalhe`. É só observabilidade (não muda nenhuma condição
de sinal) — usar o próximo run real pra identificar qual gatilho específico falta e decidir o próximo
ajuste cirúrgico (ex: permitir `macd_recuperando or macd_bull_r` no SETUP pra aceitar tendência já
positiva, não só recuperação — só aplicar depois de confirmar no log real, nunca "no escuro").

## REGRA #7 — RSI ANTI-ESTICADO: NÃO COMPRAR SOBRECOMPRADO, NÃO VENDER SOBREVENDIDO (corrigida 23/06)

Pedido original do usuário: "só ativar compra quando rsi estiver em ponto de subida não de descer e para
venda ai contrario". Interpretado nesta sessão, num primeiro momento, como gate de **inclinação** do RSI
(`rsi_subindo`/`rsi_caindo`) — implementado e documentado, depois revertido no mesmo dia: o usuário
corrigiu explicitamente ("oque quis dizer e sobre rsi sobi vendido não entra com o ponto já esticado") que
a intenção real era sobre RSI **esticado** (sobrecomprado/sobrevendido), não sobre a inclinação do candle
atual. `and i["rsi_subindo"]`/`and i["rsi_caindo"]` foram removidos dos 8 sinais onde tinham sido
adicionados (PULLBACK, CROSS, BB_BREAK, SM_SWEEP, REVERSAL, FLEX, SETUP, SCOUT) — `rsi_subindo`/
`rsi_caindo` continuam existindo em `analyze.py` só nos usos que já tinham antes (ELITE, `_score_inst()`,
`rsi_dinamico_long/short`), sem efeito sobre a cascata de 12 sinais.

### Auditoria feita antes de reverter — a defesa anti-esticado já existe e é robusta
Conferido sinal por sinal o que cada um já tem, além da REGRA #1 (`rsi_zona_long/short`, zona absoluta
75/25, intocada):
- **PULLBACK, CROSS, SM_SWEEP, FLEX, SETUP, SCOUT**: já têm `nao_overext_long/short` (preço não pode estar
  >50% do range das últimas 48 velas) + `rsi_nao_chasing_long/short` (RSI não saltou >18pts numa vela) +
  `nao_ext_long_tight/short` (teto efetivo de RSI ~65, até 75 só com ADX>32) — defesa já completa.
- **BB_BREAK**: além do mesmo `nao_overext`/`rsi_nao_chasing`, tem teto próprio **mais apertado ainda**
  (`rsi<65` LONG / `rsi>35` SHORT, fix "21/06 — RSI com espaço pra correr") + `not stoch_esticado_up/down`
  — defesa mais forte que o padrão dos outros sinais.
- **REVERSAL**: contrário por desenho (`rsi<30` LONG / `rsi>70` SHORT — entra justamente no extremo pra
  pegar a virada, com `ha_bull`+`v_forte`+`liq_fundo/absorb`+`macd_recuperando` como confirmação), não usa
  `rsi_zona` por desenho (já documentado) — anti-esticado não se aplica aqui do mesmo jeito, é exceção
  deliberada, mesmo padrão de SURGE/MOMENTUM/REBOUND.

Conclusão: a proteção que o usuário pediu já existe e já é robusta em todos os 7 sinais não-contrários.
Não havia (e ainda não há) um caso real de diagnóstico/log apontando um candidato específico travado
isoladamente por RSI esticado — por isso não foi adicionado nenhum threshold novo nesta correção, seguindo
o mesmo critério já estabelecido na sessão (só apertar/afrouxar threshold numérico com caso real
concreto, nunca "no escuro", ver "AJUSTE 23/06" acima). Se um diagnóstico futuro mostrar um candidato forte
travado especificamente por RSI esticado, é o gatilho certo pra apertar `nao_ext_long_tight`/
`rsi_nao_chasing` ou o teto próprio do sinal envolvido — mesmo padrão cirúrgico já usado nos ajustes
anteriores.

### O que NÃO foi tocado
REGRA #1 (`rsi_zona_long/short`, 75/25) e REGRA #5 (defesas SMC) intocadas. `notify.py` (stop/TP/
leverage), classificação V3/V4/v5.0, gestão de risco — nada disso foi tocado.

---

## vol_secando — 3ª RODADA DE AFROUXAMENTO (autorizado 23/06, run real pós-merge da alavancagem dinâmica)

Run real disparado em `main` logo após o merge de `claude/strategy-improvement-LUJWU` (alavancagem 5x-20x
por tier) mostrou, em só 2 ciclos/77 análises, dois candidatos com score bom e RSI normal bloqueados
**isoladamente** só por `vol_sec` (nenhum outro filtro pegando): TEL LONG score+100/RSI65 e NOCK SHORT
score-128/RSI31. Os outros candidatos do mesmo diagnóstico (BEAT RSI89 extremo, DYDX/MEGA ADX baixo, XPR/
RAVE sem sweep de liquidez, ZAMA StochRSI saturado) são bloqueios genuínos — defesas calibradas por
incidente real (REGRA #1/#5), não tocadas.

`vol_secando` já tinha sido afrouxado 2x no dia anterior (22/06: `0.25/0.50→0.18/0.40`→depois reescrito
direto pra `0.10/0.25` no merge da v5.0) e continuava sendo o bloqueador isolado mais frequente. Afrouxado
de novo em `analyze.py`: `volumes[-1] < vol_ma*0.10 and < min(vol3)*0.25` → `< vol_ma*0.06 and < min(vol3)*0.15`
— exige um esgotamento de volume ainda mais extremo antes de bloquear `seguro_long/short`.

Validar com o próximo run real se TEL/NOCK (ou candidatos equivalentes) passam a disparar sinal. Se
`vol_sec` continuar sendo o bloqueador isolado dominante mesmo depois desta 3ª rodada, é sinal de que o
filtro talvez devesse virar penalidade no score em vez de bloqueio binário — mudança estrutural maior,
só considerar se a abordagem atual (afrouxar o limiar) se esgotar.

---

## vol_secando — 4ª RODADA: BLOQUEIO BINÁRIO → ALERTA LEVE (autorizado 23/06)

A 3ª rodada (acima) não resolveu — auditoria do run seguinte (`28046849704`, main, commit `b20b17b`, 8
ciclos completos via log) mostrou `vol_sec` ainda como o bloqueador **isolado** (nenhum outro filtro
pegando) de vários candidatos com score alto e nada mais de errado: GRASSUSDT LONG score+145, DYDXUSDT
LONG score+130/+125, SUIUSDT SHORT score-130, XPRUSDT LONG score+98, SHXUSDT SHORT score-115, XMRUSDT
SHORT score-105, DNUSDT SHORT score-100 — confirma o esgotamento já previsto na nota da 3ª rodada (esses
não são TEL/NOCK especificamente, mas o mesmo padrão generalizado: 4 rodadas de afrouxar limiar não
eliminam o problema porque o filtro continua sendo um corte binário "tudo ou nada").

### O que foi implementado (`analyze.py`)
Em vez de afrouxar o número uma 5ª vez, `vol_secando` saiu da composição de `seguro_long`/`seguro_short`
(linha ~347-349) — não bloqueia mais a detecção do sinal na cascata (`detectar_sinais()`, usado por
PULLBACK/CROSS/BB_BREAK/SM_SWEEP/FLEX/SETUP/DIV/REBOUND/SCOUT/ELITE/EARLY). Continua existindo e sendo
calculado igual, e continua contado em `seguro_alertas_long/short` (`analyze.py` linha ~353-356) — sistema
de tolerância que já existia desde o GAUSS+DNA v5.0 mas estava sendo neutralizado: como `vol_secando`
também hard-bloqueava `seguro_long/short` *antes* da cascata, um sinal com `vol_sec=True` nunca chegava a
ser detectado, então `classificar_v2()` (que exige `seguro_alertas <= 1` pra PRATA/BRONZE) nunca via esse
candidato — o "alerta leve" já existia no código mas nunca tinha chance de ser exercido especificamente
por causa do `vol_sec`. Agora `vol_secando` sozinho não impede mais o sinal de ser detectado, mas ainda
soma 1 ponto no contador de alertas e pode custar o tier (PRATA/BRONZE) se vier combinado com qualquer
outro alerta leve (`perto_bb_topo`, `ext_acima_e21`, `exaustao_topo`, `stoch_esticado_up` ou os
equivalentes _fund/_abaixo/_down do lado short) — continua penalizando entrada de baixo volume, só deixou
de matar o candidato isoladamente.

### O que NÃO foi tocado nesta rodada
- `mom_seguro_long/short` (MOMENTUM, linha ~750-752) e `_vol_inst_ok` (modo INSTITUCIONAL, linha ~855)
  continuam com `not vol_secando` como bloqueio binário próprio — não apareceram como o bloqueador
  dominante neste log específico (MOMENTUM nem apareceu nos candidatos auditados), mudança isolada só
  no composto principal (`seguro_long/short`) usado pelos outros 9-10 tipos de sinal, mesmo padrão
  cirúrgico de só tocar o que o diagnóstico real aponta.
- `stoch_extremo` (bloqueio absoluto 0.00/1.00 em `classificar_v2()`) — não relacionado a `vol_sec`,
  intocado (caso real do mesmo log: NOCKUSDT travado por `stoch=0.00`, bloqueio genuíno, não bug).
- REGRA #1/#5, gestão (stop/TP/leverage), tamanho de posição — nenhum tocado.

Validar com o próximo run real se GRASS/DYDX/SUI/XPR (ou equivalentes) passam a ser classificados
PRATA/BRONZE e disparar sinal real. Se `seguro_alertas` combinado ainda travar a maioria por outro alerta
leve simultâneo, é o próximo ponto pra auditar — não afrouxar mais nenhum limiar isolado sem caso real novo.

---

## `classificar_v2()` — TOLERÂNCIA DE 1 MISS NO `_base` (autorizado 23/06 — caso real DNUSDT)

Pedido do usuário: "quero sinal reais pode resolver agora" — depois do fix de `vol_secando` (rodada acima)
confirmado funcionando (sinal de teste DNUSDT SHORT chegou ao Telegram via `_tentar_sinal_teste()`, prova
que passou a cascata de `detectar_sinais()`), o mesmo candidato ainda voltou `classificacao=None` em
`classificar_v2()`. Métricas reais do DN: `score_inst=90` (ELITE), `RVOL=1.55x` (STRONG), `ADX=47`, fluxo
confirmado, tendência baixa — excelente em praticamente todo eixo. Causa raiz isolada: `rsi_dinamico_short`
(`45<=rsi<=70 and rsi_caindo_3`) é `False` porque `RSI=29` (já abaixo do piso 45) — único fator do `_base`
que falhou.

`_base` original exigia **8 fatores simultâneos** (`rsi_din`, `stoch_mom`, `fluxo_ok`, `mm200_ok`,
`liq_varrida`, `seguro_alertas<=1`, `ha1_ok`, `vol_ok`) — mesmo padrão de funil empilhado já documentado
no comentário da CLASSIFICAÇÃO INSTITUCIONAL V3 (`analyze.py`, acima de `classificar_v2()`): "acumulado
filtro sobre filtro a cada incidente até o funil ficar bom demais pra deixar passar qualquer coisa,
incluindo movimentos reais e fortes" — e já corrigido uma vez no mesmo dia pra `vol_secando` (bloqueio
binário → alerta leve). DN é a evidência concreta de que o mesmo problema estrutural também existe aqui,
só que com `rsi_dinamico` como o elo isolado que quebra a cadeia.

Não toquei na **janela** de `rsi_dinamico_long/short` em si (decidido deliberadamente: RSI=29 com ADX=47
é uma tendência já madura/estendida — bloquear esse caso especificamente é consistente com a REGRA #6,
"pegar o movimento no começo, nunca atrasado", não é bug). Em vez disso, o `_base` agora tolera 1 miss
entre os 6 fatores "secundários" (`rsi_din`, `stoch_mom`, `fluxo_ok`, `liq_varrida`, `ha1_ok`, `vol_ok`) —
mesmo padrão de tolerância já usado em `seguro_alertas<=1` dentro do próprio `_base`. `mm200_ok`
(alinhamento com a tendência macro via MM200) continua **absoluto**, sem tolerância — é a linha de risco
que a seção "Lógica Institucional" deste arquivo já trata como não-negociável. `stoch_extremo` (bloqueio
0.00/1.00) também continua absoluto, intocado.

### O que NÃO foi tocado
- Pisos de score_inst/RVOL/ADX/dist_mm21 por tier (PRATA 85/1.5/25/2% — BRONZE 75/1.0/22) — continuam
  exigidos por cima do `_base`, são o controle de qualidade compensatório quando 1 dos 6 fatores falha.
- `rsi_dinamico_long/short` (janela 30-55/45-70) — intocado, ver justificativa acima.
- REGRA #1 (`rsi_zona`), REGRA #5, gestão (stop/TP/leverage/lote) — nenhum tocado.

Validar com o próximo run real se candidatos fortes com 1 fator secundário fraco (não `mm200_ok`) passam
a classificar PRATA/BRONZE e disparar sinal real de fato (não só teste). Se ainda travar, auditar qual dos
6 fatores está faltando com mais frequência nos próximos diagnósticos antes de tocar a tolerância de novo.
