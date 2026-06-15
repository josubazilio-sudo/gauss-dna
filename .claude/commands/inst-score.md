Analisa e evolui o Institutional Score (0-100) do GAUSS+DNA.

## O que é Institutional Score AI

Score de 0-100 que mede o alinhamento institucional de uma operação. Quanto maior, mais fundos/whales estão do mesmo lado:

| Componente | Peso | O que avalia |
|-----------|------|-------------|
| Tendência macro | 20 pts | Preço acima EMA200 + EMAs alinhadas |
| ADX + direção | 15 pts | ADX > 22 + PDI/MDI dominante + ADX subindo |
| Fluxo institucional | 15 pts | DNA Flow ou f_bull/bear + pressão |
| Heikin-Ashi | 10 pts | 2 velas HA confirmadas |
| Trendilo | 10 pts | Kalman + momentum direcional |
| RSI momentum | 10 pts | RSI subindo (LONG) ou caindo (SHORT) |
| Volume forte | 10 pts | RVOL ≥ 1.5x |
| Divergência RSI | 5 pts | RSI divergindo do preço |
| Smart Money | 5 pts | Liquidez + absorção + HA |
| **TOTAL** | **100 pts** | |

**Classificação atual:**
- 85+ = ELITE
- 70+ = FORTE → PREMIUM
- 55+ = MÉDIO → SCOUT_FLEX
- <55 = FRACO → bloqueado

## Evoluções possíveis

### 1. Adicionar componentes ao score
```python
# Funding rate alinhado: -5 pts exigência (já implementado)
# OI crescente na direção: +5 pts bônus
# MTF alinhado (4H+1H): +10 pts bônus
# Liquidez limpa recente (post-sweep): +5 pts bônus
# Volume anomalia (OBV explodindo): +5 pts bônus
```

### 2. Volume Anomaly como componente
RVOL 2x com OBV neutro ≠ RVOL 2x com OBV explodindo:
```python
vol_anomalia = v_forte and (obv_bull or obv_bear) and volumes[-1] > vol_ma * 2.0
# vol_anomalia = True → +5 pts bônus no score_inst
```

### 3. Refinar ADX component
```python
# Atual: adx > 22 AND pdi/mdi dominante AND adx_subindo
# Evolução: adicionar inclinação da MM21 e MM50
e21_slope = (e21 - e21_arr[-6]) / e21_arr[-6]   # slope 6 períodos
e50_slope = (e50 - e50_arr[-6]) / e50_arr[-6]
tend_forte = e21_slope > 0.001 and e50_slope > 0.001  # inclinação positiva
# tend_forte → +5 pts extra no score_inst
```

## Como usar esta skill

Descreva o que quer melhorar no score institucional (ex: "quero que funding rate pese mais" ou "OBV explodindo deveria dar bônus").

Com base no pedido:

1. **Checar implementação atual** de `_score_inst()` em `analyze.py` (linhas ~426-440)
2. **Propor componente novo** ou ajuste de peso
3. **Verificar impacto**: quantos candidatos passariam/bloqueariam com o novo threshold
4. **Implementar, testar** (`python3 -c "import analyze; print('OK')"`) **e fazer commit + push**

## Impacto esperado
- Score mais preciso = menos falsos positivos
- Bônus para setups pós-sweep aumenta taxa de acerto
- Penalidade para funding contrário reduz losses em reversões
