Cria ou melhora o score Multi-Timeframe Bias no GAUSS+DNA.

## O que é MTF Bias

Score ponderado que combina múltiplos timeframes para definir o viés direcional:

| Timeframe | Peso | Contribuição |
|-----------|------|-------------|
| 4H | 40 pts | Tendência macro — define o viés principal |
| 1H | 35 pts | Tendência intermediária — confirma ou enfraquece |
| 15M | 25 pts | Entrada — timing fino |

**Exemplos de combinação:**
- 4H bull + 1H bull + 15M pullback → **A+ LONG** (entrada ideal)
- 4H bull + 1H neutro + 15M bull → **A LONG**
- 4H bear + 15M long → **SCOUT apenas** (contra-tendência — risco alto)
- 4H bear + 1H bear + 15M bear → **A+ SHORT**

## O que o código já tem

- `_h4_confirma()` em `cycles.py` — bloqueia H4 forte oposto
- `score_inst_long/short` — inclui `tendencia_bull/bear` (EMA 200 + alinhamento)
- `tbull_r` / `tbear_r` — estrutura de MAs no TF atual

## Como usar esta skill

Descreva o comportamento que quer (ex: "quero que o bot só abra LONG quando 4H também é bull") ou cole diagnóstico.

Com base no pedido:

1. **Checar implementação atual** em `cycles.py`:
   - Como `_h4_confirma()` está configurado
   - Se existe score MTF acumulado

2. **Implementar MTF Score** em `cycles.py`:
   ```python
   def _mtf_score(h4_result, h1_result, tf_result):
       score = 0
       direcao = tf_result["sinal"]
       
       # 4H: 40 pts
       if h4_result:
           h4_bull = h4_result.get("tbull_r") and h4_result.get("score", 0) > 20
           h4_bear = h4_result.get("tbear_r") and h4_result.get("score", 0) < -20
           if direcao == "LONG"  and h4_bull: score += 40
           if direcao == "SHORT" and h4_bear: score += 40
       
       # 1H: 35 pts  
       if h1_result:
           h1_bull = h1_result.get("score", 0) > 15
           h1_bear = h1_result.get("score", 0) < -15
           if direcao == "LONG"  and h1_bull: score += 35
           if direcao == "SHORT" and h1_bear: score += 35
       
       # 15M (TF atual): 25 pts (já confirmado pelo sinal)
       score += 25
       
       return score  # 0-100
   
   # Usar no ciclo:
   # mtf >= 75 → PREMIUM tier (4H+1H+15M alinhados)
   # mtf >= 40 → SCOUT_FLEX (pelo menos 4H ou 1H alinhado)
   # mtf < 40  → contra-tendência — bloquear
   ```

3. **Integrar com o sistema atual:**
   - MTF score alto → bônus na confiança do sinal
   - MTF score baixo → rebaixar PREMIUM para SCOUT_FLEX automaticamente
   - 4H oposto forte → manter bloqueio existente

4. **Fazer commit + push + disparar novo run** se aprovado.

## Impacto esperado
- Elimina sinais contra-tendência 4H (maior fonte de losses)
- Concentra operações de maior tamanho quando 3 TFs alinhados
- Reduz tamanho em operações contra 4H
