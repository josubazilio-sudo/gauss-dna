# GAUSS+DNA — Condições de Compra (LONG) e Venda (SHORT)

> Extraído linha a linha de `analyze.py` e `cycles.py` em 21/06/2026 (commit `7a48644`).
> Pipeline: `calcular_indicadores()` → `detectar_sinais()` (gates abaixo) → `graduar_sinal()` → `cycles.py` (gates pós-sinal).

---

## 0. Filtros compostos reutilizados em vários sinais

```
seguro_long   = not perto_bb_topo AND not ext_acima_e21 AND not vol_secando
                AND not exaustao_topo AND rsi < 70 AND not stoch_esticado_up

seguro_short  = not vol_secando AND not exaustao_fund AND rsi > 27 AND not stoch_esticado_down

rsi_zona_long  = rsi < 75        (REGRA #1 — só bloqueia extremo sobrecomprado)
rsi_zona_short = rsi > 25        (REGRA #1 — só bloqueia extremo sobrevendido)

stoch_esticado_up   = stoch_rsi > 0.80 AND rsi > 58
stoch_esticado_down = stoch_rsi < 0.05 AND rsi < 35

lateralizado = bb_squeeze AND adx < 15

tendencia_bull = preco > e200 AND e10 > e21 AND e21 > e50 AND e50 > e200
tendencia_bear = preco < e200 AND e10 < e21 AND e21 < e50 AND e50 < e200

dna_flow_bull = macd_bull AND pressao_bull AND v_bom
dna_flow_bear = macd_bear AND pressao_bear AND v_bom
```

---

## Modo padrão FLEX — ordem de prioridade (primeiro que bater vence)

### 1. PULLBACK
```
LONG:  pullback_bull AND tbull_r AND preco < e21*1.03 AND dna_flow_bull
       AND adx > 18 AND pdi > mdi AND rsi_zona_long AND score_inst_long >= 50
       AND seguro_long AND trendilo_long AND NOT liq_topo

SHORT: pullback_bear AND tbear_r AND preco > e21*0.97 AND dna_flow_bear
       AND adx > 18 AND mdi > pdi AND rsi_zona_short AND score_inst_short >= 50
       AND seguro_short AND trendilo_short AND NOT liq_fundo
```

### 2. CROSS
```
LONG:  algum_cross_bull AND dna_flow_bull AND adx_long_ok AND preco > e200
       AND score_inst_long >= 50 AND rsi_zona_long AND seguro_long
       AND (trendilo_long OR kalman_subindo)

SHORT: algum_cross_bear AND dna_flow_bear AND adx_short_ok AND preco < e200
       AND score_inst_short >= 50 AND rsi_zona_short AND seguro_short
       AND (trendilo_short OR NOT kalman_subindo)
```

### 3. BB_BREAK
```
LONG:  bb_break_long AND bb_expand AND kalman_subindo AND k_short_subindo
       AND score > 40 AND adx >= 15 AND adx_subindo(FL>=2) AND NOT lateralizado
       AND NOT ext_acima_e21 AND obv_bull AND NOT liq_topo(FL>=3)
       AND preco > e200 AND preco > e50 AND NOT stoch_esticado_up
       AND rvol >= 0.50/0.65/0.80 (por nível de filtro) AND rsi_zona_long
       AND score_inst_long >= 50

SHORT: bb_break_short AND bb_expand AND kalman_descendo AND k_short_descendo
       AND score < -40 AND adx >= 15 AND adx_subindo(FL>=2) AND NOT lateralizado
       AND NOT ext_abaixo_e21 AND obv_bear AND NOT liq_fundo(FL>=3)
       AND preco < e200 AND preco < e50 AND NOT stoch_esticado_down
       AND rvol >= 0.50/0.65/0.80 (por nível de filtro) AND rsi_zona_short
       AND score_inst_short >= 50
```
NOT stoch_esticado_up/down adicionado 21/06 (ver CLAUDE.md "BB_BREAK — defesa de StochRSI esgotado").

### 4. SM_SWEEP (Smart Money)
```
LONG:  sm_bull AND rsi > 25 AND rsi_zona_long AND preco > e200 AND score_inst_long >= 60
SHORT: sm_bear AND rsi_zona_short AND rsi < 75 AND preco < e200 AND score_inst_short >= 60

  sm_bull = liq_fundo AND absorb_bull AND v_forte AND ha_bull AND (dna_flow_bull OR f_bull)
  sm_bear = liq_topo  AND absorb_bear AND v_forte AND ha_bear AND (dna_flow_bear OR f_bear)
```

### 5. REVERSAL (sem gate de score_inst)
```
LONG:  rsi < 30 AND ha_bull AND v_forte AND (liq_fundo OR absorb_bull)
       AND macd_recuperando AND adx > 12 AND preco > e200*0.96
       AND (dna_flow_bull OR obv_bull)

SHORT: rsi > 70 AND ha_bear AND v_forte AND (liq_topo OR absorb_bear)
       AND macd_esgotando AND adx > 12 AND preco < e200*1.04
       AND (dna_flow_bear OR obv_bear)
```

### 6. SURGE (não usa not liq_topo/fundo — contradição com surge_break)
```
LONG:  rvol_tier_max2 >= 3 (3x+) AND candle_bull_pct > 0.03 AND surge_break_h
       AND NOT exaustao_topo AND (kalman_subindo OR k_short_subindo) AND ha_bull
       AND rsi < 78 AND score_inst_long >= 50 AND (dna_flow_bull OR trendilo_long)

SHORT: rvol_tier_max2 >= 3 (3x+) AND candle_bear_pct > 0.03 AND surge_break_l
       AND NOT exaustao_fund AND (kalman_descendo OR k_short_descendo) AND ha_bear
       AND rsi > 22 AND score_inst_short >= 50 AND (dna_flow_bear OR trendilo_short)
```

### 7. MOMENTUM
```
LONG:  rsi_ant < 65 <= rsi < 73 AND ha_bull AND dna_flow_bull AND NOT liq_topo
       AND adx > 22 AND v_forte AND trendilo_long AND score_inst_long >= 60
       AND mom_seguro_long

SHORT: rsi_ant > 42 >= rsi > 30 AND ha_bear AND dna_flow_bear AND NOT liq_fundo
       AND adx > 22 AND v_forte AND trendilo_short AND score_inst_short >= 60
       AND mom_seguro_short

  mom_seguro_long  = NOT perto_bb_topo AND NOT ext_acima_e21 AND NOT vol_secando
                      AND NOT exaustao_topo AND NOT stoch_esticado_up
  mom_seguro_short = NOT perto_bb_fund AND NOT ext_abaixo_e21 AND NOT vol_secando
                      AND NOT exaustao_fund AND NOT stoch_esticado_down
```

### 8. REBOUND
```
LONG:  rsi_spike_long AND rsi_rebound_long AND ha_bull AND dna_flow_bull
       AND trendilo_long AND adx > 20 AND v_bom AND kalman_subindo
       AND NOT lateralizado AND seguro_long AND nao_ext_long_tight

SHORT: rsi_dip_short AND rsi_rebound_short AND ha_bear AND dna_flow_bear
       AND trendilo_short AND adx > 20 AND v_bom AND NOT kalman_subindo
       AND NOT lateralizado AND seguro_short AND (e21-preco)/atr < 2.5

  rsi_spike_long   = rsi_ant > 65 OR rsi_6 > 65 OR rsi_9 > 65
  rsi_rebound_long = 54 <= rsi <= 62 AND rsi < rsi_ant
  rsi_dip_short     = rsi_ant < 35 OR rsi_6 < 35 OR rsi_9 < 35
  rsi_rebound_short = 38 <= rsi <= 46 AND rsi > rsi_ant
```

### 9. DIV (divergência RSI)
```
LONG:  rsi_div_bull AND ha_bull AND v_bom AND rsi > 25 AND rsi_zona_long
       AND NOT exaustao_topo AND adx > 15 AND NOT lateralizado AND preco > e200
       AND score_inst_long >= 55

SHORT: rsi_div_bear AND ha_bear AND v_bom AND rsi_zona_short AND rsi < 70
       AND preco < e200 AND NOT exaustao_fund AND adx > 15 AND NOT lateralizado
       AND score_inst_short >= 55

  rsi_div_bull = fechamento[-1] < fechamento[-4] AND rsi > rsi_ant AND rsi < 45
  rsi_div_bear = fechamento[-1] > fechamento[-4] AND rsi < rsi_ant AND rsi > 55
```

### 10. FLEX
```
LONG:  score >= 40 AND ha_bull2 AND macd_bull_r AND adx >= 25 AND NOT lateralizado
       AND nao_ext_long_tight AND seguro_long AND flex_vol_ok AND rvol >= 1.2
       AND rsi_zona_long AND nao_overext_long AND rsi_nao_chasing_long
       AND score_inst_long >= 50
       AND (liq_long OR liq_fundo OR (trendilo_long AND kalman_subindo))
       AND (trendilo_long OR kalman_subindo OR dna_flex_bull)

SHORT: score <= -40 AND ha_bear2 AND macd_bear_r AND adx >= 25 AND NOT lateralizado
       AND nao_ext_short_tight AND seguro_short AND flex_vol_ok_s AND rvol >= 1.2
       AND rsi_zona_short AND nao_overext_short AND rsi_nao_chasing_short
       AND score_inst_short >= 50
       AND (liq_short OR liq_topo OR (trendilo_short AND NOT kalman_subindo))
       AND (trendilo_short OR NOT kalman_subindo OR dna_flex_bear)
```

### 11. SETUP (acumulação antecipada)
```
LONG:  score > 50 AND ha_bull2 AND macd_recuperando AND adx > 18 AND obv_bull
       AND v_bom AND acima_vwap AND NOT lateralizado AND nao_ext_long_tight
       AND seguro_long AND (liq_long OR liq_fundo) AND preco > e200
       AND score_inst_long >= 50 AND rsi_zona_long

SHORT: score < -50 AND ha_bear2 AND macd_esgotando AND adx > 18 AND obv_bear
       AND v_bom AND abaixo_vwap AND NOT lateralizado AND nao_ext_short_tight
       AND seguro_short AND (liq_short OR liq_topo) AND preco < e200
       AND score_inst_short >= 50 AND rsi_zona_short
```

### 12. SCOUT (sinal secundário, mais raro desde 20/06)
```
LONG:  score >= 25/40 (FL<=0/outros) AND ha_bull_1 AND macd_bull_r AND adx >= 25
       AND adx_subindo(FL>=2) AND NOT lateralizado AND nao_ext_long_tight
       AND seguro_long(FL>=1) AND vol_nao_fade AND rvol >= 1.2 AND nao_overext_long
       AND rsi_nao_chasing_long AND rsi_zona_long AND NOT liq_topo(FL>=3)
       AND soma(dna_flow_bull, f_bull, trendilo_long, kalman_subindo) >= fluxo_min(0/1/2)

SHORT: score <= -25/-40 (FL<=0/outros) AND ha_bear_1 AND macd_bear_r AND adx >= 25
       AND adx_subindo(FL>=2) AND NOT lateralizado AND nao_ext_short_tight
       AND seguro_short(FL>=1) AND vol_nao_fade AND rvol >= 1.2 AND nao_overext_short
       AND rsi_nao_chasing_short AND rsi_zona_short AND NOT liq_fundo(FL>=3)
       AND soma(dna_flow_bear, f_bear, trendilo_short, NOT kalman_subindo) >= fluxo_min(0/1/2)

  vol_nao_fade = max(volumes[-1], volumes[-2]) >= vol_ma * (0.20/0.50/0.65/0.80 por FL)
```

---

## Modo ELITE (`SIGNAL_MODE=ELITE`, substitui o modo FLEX)

```
LONG:  tendencia_forte AND tendencia_bull AND alinhado_bull AND e200_subindo
       AND macd_bull3 AND ha_bull3 AND f_bull AND f_forte AND adx_long_ok
       AND rsi_bull_elite AND (v_forte2 OR obv_bull) AND nao_ext_long
       AND kalman_accel_up AND acima_vwap AND tend_consistente_bull
       AND (impulso_bull OR liq_long) AND score > 65 AND seguro_long

SHORT: tendencia_forte AND tendencia_bear AND alinhado_bear AND e200_descendo
       AND macd_bear3 AND ha_bear3 AND f_bear AND f_forte AND adx_short_ok
       AND rsi_bear_elite AND (v_forte2 OR obv_bear) AND nao_ext_short
       AND kalman_accel_down AND abaixo_vwap AND tend_consistente_bear
       AND (impulso_bear OR liq_short) AND score < -65 AND seguro_short

EARLY (exaustão / entrada antecipada — mesma prioridade do ELITE):
LONG:  adx_long_ok AND (v_forte OR obv_bull) AND exaustao_venda AND liq_long
       AND absorb_bull AND f_bull AND tendencia_bull AND e200_subindo
       AND kalman_subindo AND acima_vwap AND macd_recuperando AND seguro_long

SHORT: adx_short_ok AND (v_forte OR obv_bear) AND exaustao_compra AND liq_short
       AND absorb_bear AND f_bear AND tendencia_bear AND e200_descendo
       AND kalman_descendo AND abaixo_vwap AND macd_esgotando AND seguro_short
```

---

## Modo INSTITUCIONAL (`SIGNAL_MODE=INSTITUCIONAL`, substitui o modo FLEX)

Reaproveita 6 sinais tipados (SM_SWEEP > MOMENTUM > SURGE > PULLBACK > SETUP > FLEX,
nessa ordem de prioridade), cada um exigindo a própria condição da cascata acima **E**
o piso comum abaixo (AJUSTE INSTITUCIONAL ELITE, 21/06):

```
PISO COMUM LONG:
  tendencia_bull AND adx > 25 AND adx_subindo AND rvol > 1.5
  AND dna_flow_bull AND trendilo_long AND liq_fundo_12
  AND 45 <= rsi <= 68 AND stoch_rsi < 0.85
  AND volume_real > vol_ma AND NOT vol_secando
  AND (1 - pos_bb) >= 0.01   (distância mínima do topo da BB)
  AND estrutura_alta (HH+HL nos pivôs)
  AND ha_bull
  AND score_inst_long >= 80

PISO COMUM SHORT:
  tendencia_bear AND adx > 25 AND adx_subindo AND rvol > 1.5
  AND dna_flow_bear AND trendilo_short AND liq_topo_12
  AND 32 <= rsi <= 50 AND stoch_rsi > 0.15
  AND volume_real > vol_ma AND NOT vol_secando
  AND pos_bb >= 0.01   (distância mínima do fundo da BB)
  AND estrutura_baixa (LH+LL nos pivôs)
  AND ha_bear
  AND score_inst_short >= 80
```

Grade só **S** (score_inst>=90) ou **A+** (score_inst>=80) — grade A é bloqueada neste modo.

---

## Gates pós-sinal (`cycles.py executar_ciclo()` — rodam DEPOIS que o sinal já foi decidido acima)

Aplicados a **todos** os sinais, independente do tipo:

```
1. ATR > 4% do preço                              → ignora (volátil demais)
2. |score| < 30 (REVERSAL/SM_SWEEP/DIV) ou < 40 (demais)  → bloqueia
3. Grade fora de {A, A+, S, S+}                    → bloqueia (B sempre bloqueado)
4. ADX < ADX_MIN_GLOBAL (20)                       → bloqueia
5. RVOL < RVOL_MIN_BY_TF[tf] (0.70 em 30m / 0.80 em 1h) → bloqueia
6. Score Inst < _inst_min:
     35 (SCOUT) | 40 (REVERSAL/SM_SWEEP/DIV) | 45 (demais)
     → max(., 60) em sessão perigosa (22h-08h UTC ou abertura 08h/13h UTC)
     → max(., 75) sempre — FILTRO DE EXECUÇÃO V2 (21/06, "confiança>=65%"), dominante na prática
   → bloqueia
6b. RVOL < max(RVOL_MIN_BY_TF[tf], 1.0)                → bloqueia (piso V2 sobe RVOL efetivo p/ 1.0)
7. H4 diverge da direção (1h/30m/15m)              → bloqueia
8. Cooldown: mesma direção = tf_minutos*60s (mín. 2h);
   qualquer direção mesma moeda/tf = 2h            → bloqueia
9. NOT dna_flow E NOT trendilo na direção do sinal → bloqueia (sem fluxo SMC)
10. Limites por ciclo: 3 sinais total, 2 SCOUT, 2 LONG, 2 SHORT,
    10% capital de risco acumulado                 → bloqueia
11. Filtro de regime BTC: BTC ADX < 20 E BTC RSI 45-55 → bloqueia LONG e SHORT
    em TODAS as moedas (falha aberta se BTC não buscar)
```

No modo INSTITUCIONAL, os itens 3 e 6 mudam para: grade só {S, A+}; H4 estrito
(`_h4_confirma_estrito` — exige confirmação ativa, bloqueia qualquer divergência);
cooldown próprio (3h mesma direção / 2h oposta); teto de ciclo 5%; máx. 3 posições
simultâneas; circuit breaker após 3 STOPs consecutivos (pausa até próximo TP1_BE/TP2).
