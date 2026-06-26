# REVISÃO DE CONDIÇÕES — GAUSS+DNA

> Arquivo cola — thresholds, tiers, sinais, bloqueadores.
> Copie e cole pra analisar o que precisa ser ajustado.

---

## 1. CLASSIFICAÇÃO v2 — OURO/PRATA/BRONZE (`analyze.py:612`)

| Tier | Score Inst | RVOL | ADX | RSI LONG | RSI SHORT | Dist MM21 | Exige |
|------|------------|------|-----|----------|-----------|-----------|-------|
| 🥇 OURO | >=90 | >=1.50 | >=25 | 45-62 | 38-55 | <=2.5% | fluxo + liq + not exaustao |
| 🥈 PRATA | >=80 | >=1.00 | >=20 | 42-65 | 35-58 | <=3.5% | fluxo + liq + not exaustao |
| 🥉 BRONZE | >=72 | >=0.35 | >=15 | 38-70 | 30-62 | <=4.0% | só not exaustao |

**GLOBAIS (antes dos tiers — qualquer um bloqueia):**
- `tendencia_bull/bear` — e10>e21>e50>e200 + preço>e200
- `ha_bull_1/ha_bear_1` — HA da última vela com corpo >0.2 ATR
- `macd_ok` — MACD bull_r OU recuperando (LONG) / bear_r OU esgotando (SHORT)

---

## 2. SINAIS — ORDEM DE PRIORIDADE (`detectar_sinais()`)

| # | Sinal | Score min | ADX min | RVOL min | Gate extra |
|---|-------|-----------|---------|----------|------------|
| 1 | PULLBACK | inst>=50 | >18 | - | `pullback_bull`+`tbull_r`+preço<e21*1.03+dna_flow+seguro+trendilo+not liq_topo |
| 2 | CORE | - | >=18 | - | RSI 45-58 LONG / 42-55 SHORT + rsi_subindo/caindo + kalman + trendilo + tbull/tbear_loose + ha_bull + not liq_topo/fundo + preço>e200 (LONG) / <e200 (SHORT) + preço <= e21*1.02 (LONG) / >=e21*0.98 (SHORT) + vol_nao_fade |
| 3 | CROSS | inst>=50 | adx_long_ok | - | algum_cross_bull/bear + dna_flow + preço>e200 (LONG) / <e200 (SHORT) + rsi_zona + seguro + trendilo/kalman |
| 4 | BB_BREAK | inst>=50 | >=15 | >=0.50-0.80 (FL) | bb_break+bb_expand+kalman+k_short+score>40+adx_subindo(FL>=2)+not lateral+not ext_e21+obv+not liq_topo(FL>=3)+preço>e200+e50+not stoch_esticado+rvol+RSI<65(L)/>35(S) |
| 5 | SM_SWEEP | inst>=60 | - | - | sm_bull/bear+RSI>25(L)/<75(S)+rsi_zona+preço>e200(L)/<e200(S) |
| 6 | REVERSAL | - | >12 | v_forte | RSI<30(L)/>70(S)+ha_bull/bear+liq_fundo/topo ou absorb+macd_recuperando/esgotando+preço>e200*0.96(L)/<e200*1.04(S)+dna_flow ou obv |
| 7 | SURGE | inst>=50 | - | >=3x | rvol_tier_max2>=3 + candle>3% + surge_break + not exaustao + kalman + ha + RSI<78(L)/>22(S) + fluxo |
| 8 | MOMENTUM | inst>=60 | >22 | v_forte | RSI_ant<65<=RSI<73(L)/RSI_ant>42>=RSI>30(S)+ha+dna_flow+not liq_topo/fundo+trendilo+mom_seguro |
| 9 | REBOUND | - | >20 | v_bom | rsi_spike+rebound+ha+dna_flow+trendilo+kalman+not lateral+seguro+nao_ext_tight |
| 10 | DIV | inst>=55 | >15 | v_bom | rsi_div+ha+RSI>25(L)/<70(S)+rsi_zona+not exaustao+not lateral+preço>e200(L)/<e200(S) |
| 11 | FLEX | inst>=50 | >=15 | >=1.2 | score>=40(L)/<=-40(S)+ha_bull2/bear2+macd_bull_r+not lateral+nao_ext_tight+seguro+flex_vol_ok+rsi_zona+rvol>=1.2+liq_ok+(trendilo/kalman/dna_flex) |
| 12 | SETUP | inst>=50 | >18 | v_bom | score>50(L)/<-50(S)+ha_bull2/bear2+macd_recuperando/esgotando+obv+acima/abaixo_vwap+not lateral+nao_ext_tight+seguro+liq+preço>e200(L)/<e200(S)+rsi_zona |
| 13 | SCOUT | - | >=15 | >=1.2 | score>=25-40 (FL)+ha_bull_1/bear_1+macd_bull_r+adx_subindo(FL>=2)+not lateral+nao_ext_tight+seguro(FL>=1)+vol_nao_fade+fluxo>=_fluxo_min+not liq_topo(FL>=3) |

---

## 3. CONFIG DO USUÁRIO (`config.py`)

| Variável | Valor | O que faz |
|----------|-------|-----------|
| `SCORE_MIN` | **72** | Score mínimo pra BRONZE |
| `ADX_MIN_GLOBAL` | **15** | ADX mínimo pra qualquer sinal |
| `RVOL_MIN` | **0.35** | RVOL mínimo global |
| `RVOL_MIN_EXEC` | **0.35** | RVOL mínimo pra executar |
| `RVOL_MIN_BY_TF` | 30m:0.35, 1h:0.35 | RVOL por timeframe |
| `RSI_LONG_MIN` | **38** | RSI mínimo pra LONG |
| `RSI_LONG_MAX` | **70** | RSI máximo pra LONG |
| `RSI_SHORT_MIN` | **30** | RSI mínimo pra SHORT |
| `RSI_SHORT_MAX` | **62** | RSI máximo pra SHORT |
| `FLEX_SCOUT_SEM_LIQ` | **True** | FLEX/SCOUT sem exigir liquidez |
| `MACD_R_OBRIGATORIO` | **False** | MACD não obrigatório |
| `CROSS_OBRIGATORIO` | **False** | CROSS não obrigatório |
| `PULLBACK_OBRIGATORIO` | **False** | PULLBACK não obrigatório |
| `MACD_REC_OBRIGATORIO` | **False** | MACD recuperando não obrigatório |
| `MACD_ESG_OBRIGATORIO` | **False** | MACD esgotando não obrigatório |
| `SEM_LIQ_BLOQUEAR` | **False** | Sem liquidez não bloqueia |
| `FLOW_CONFIRMADO` | **True** | Fluxo (dna_flow/trendilo) obrigatório nos sinais |
| `MM200_OBRIGATORIA` | **True** | MM200 obrigatória |
| `DIST_MM21_MAX` | **7%** | Distância máxima da MM21 |

---

## 4. BLOQUEADORES GLOBAIS EM `classificar_v2()` — os 3 que MATAM o sinal

```python
# analyze.py:626 — tendencia
if not (ind["tendencia_bull"] if eh_long else ind["tendencia_bear"]):
    return None
# O que precisa: e10>e21>e50>e200 AND preco > e200

# analyze.py:628 — heikin ashi vela 1
if not (ind["ha_bull_1"] if eh_long else ind["ha_bear_1"]):
    return None
# O que precisa: HA fechamento > abertura AND corpo > 0.2*ATR

# analyze.py:630 — macd ok
macd_ok = (...)
if not macd_ok:
    return None
# LONG: macd_bull_r (ml>sl_v OR hist>hist_p) OR macd_recuperando (hist>hist_p>hist_pp)
# SHORT: macd_bear_r (ml<sl_v OR hist<hist_p) OR macd_esgotando (hist<hist_p<hist_pp)
```

---

## 5. GATES NO cycles.py (depois do sinal já detectado)

| Gate | Threshold | O que bloqueia |
|------|-----------|----------------|
| Score inst | >=72 (BRONZE) / >=80 (PRATA) / >=90 (OURO) | Sinal não classificado |
| Sessão perigosa | 22h-08h UTC + 08h/13h UTC | Só OURO opera |
| PRATA sem H1 | H1 alinhado exigido | PRATA sem H1 = bloqueado |
| BRONZE sem H1 | H1 alinhado OU score_inst>=70 | BRONZE sem nenhum = bloqueado |
| ATR comprimido | ATR < 90% da média 14 | Bloqueia qualquer sinal |
| BTC H4 macro | BTC H4 bear bloqueia LONG, BTC H4 bull bloqueia SHORT | Sinal contra o BTC |
| RVOL por TF | 30m:0.35, 1h:0.35 | Sinal com pouco volume |
| ADX global | >=15 (ADX_MIN_GLOBAL) | Sinal sem tendência |
| Cooldown | mesma direção = tf_minutos (mín 2h), qualquer = 2h fixo | Mesma moeda/tf |

---

## 6. DIAGNÓSTICO — o que o log mostra

No log do Actions, cada candidato bloqueado aparece como:
```
LONG-BLOQ score=+XXX RSI=XX ADX=XX K:UP/DN motivo...
```

Motivos comuns:
- `ha1=F` — Heikin Ashi da última vela não é bullish/bearish
- `fluxo=N/4` — soma de dna_flow + f_bull + trendilo + kalman < mínimo
- `adx<15` — ADX abaixo do piso global
- `macd_r=F` — MACD não confirmando direção
- `seguro=F(...)` — um dos filtros de segurança (bb_topo, ext_e21, exaustao, vol_sec, stoch, rsi)
- `lateral` — BB squeeze + ADX < 15
- `rsi_zona=F` — RSI fora da janela 38-70 (LONG) / 30-62 (SHORT)
- `gatilho:pullback=F,cross=F,...` — nenhum dos 12 sinais detectou entrada
- `sem detalhe` — fallback, sinal passou nos checks genéricos mas nenhum gatilho específico bateu
- `V3=None` — passou na detecção mas `classificar_v2()` devolveu None
- `V3=None misses=[...]` — mostra quais fatores do _base falharam
- `prata sem H1` / `bronze sem H1` — gate de cycles.py

---

## 7. FLUXO COMPLETO DO SINAL

```
candles → calcular_indicadores() → detectar_sinais() [cascata 1-13]
    ↓ sinal encontrado?
    ↓ SIM → graduar_sinal() [grade S/A/B]
    ↓    → classificar_v2() [OURO/PRATA/BRONZE/None]
    ↓       ↓ OURO/PRATA/BRONZE?
    ↓       ↓ SIM → executar_ciclo() [cycles.py]
    ↓       ↓        → gates: score inst, sessão perigosa, PRATA H1, BRONZE H1,
    ↓       ↓                 ATR comprimido, BTC H4, RVOL tf, ADX global, cooldown
    ↓       ↓        → enviar_sinal() [notify.py]
    ↓       ↓        → backtest_sinal() [auto_backtest.py]
    ↓       ↓ NÃO (None) → log "V3=None" + sinal de teste se MAX_SINAIS_TESTE>0
    ↓ NÃO → log motivo de bloqueio
```

---

## 8. PONTOS DE ESTRANGULAMENTO ATUAIS

1. **GLOBAIS do classificar_v2** (tendencia + ha1 + macd_ok) — matam o sinal ANTES de qualquer tier. Se qualquer um dos 3 falhar, nem BRONZE salva.
2. **tendencia_bull/bear** exige e10>e21>e50>e200 — em mercado com ADX 15-20 as médias podem não estar alinhadas perfeitamente, bloqueando tudo.
3. **OURO/PRATA** exigem `fluxo + liq + not exaustao` — 3 condições extras que BRONZE não exige.
4. **BRONZE** usa SCORE_MIN=72, ADX_MIN_GLOBAL=15, RVOL_MIN_EXEC=0.35, RSI_LONG 38-70, RSI_SHORT 30-62 — já está alinhado com config.py desde a correção do commit `6ab56c7`.

---

## 9. O MERCADO ESTÁ DANDO MOVIMENTO

Run `28195843348` está rodando (~15min). Se não houver sinal quando terminar, os candidatos mais prováveis são os **3 GLOBAIS**:
- `tendencia_bull/bear` falhando (médias não alinhadas)
- `ha_bull_1/ha_bear_1` falhando (vela HA sem corpo suficiente)
- `macd_ok` falhando (MACD sem recuperação nem bull_r)
