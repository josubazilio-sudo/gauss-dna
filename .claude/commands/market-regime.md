Detecta o regime atual de mercado e ajusta os filtros do GAUSS+DNA automaticamente.

## O que é Market Regime

O bot identifica em qual regime o mercado está operando antes de liberar sinais:

| Regime | Condição | Sinais liberados |
|--------|----------|-----------------|
| TENDÊNCIA FORTE | ADX > 25 + tbull_r/tbear_r + EMA alinhada | PREMIUM + SCOUT_FLEX |
| TENDÊNCIA FRACA | ADX 15-25 + direção parcial | Apenas SCOUT_FLEX |
| LATERALIZAÇÃO | ADX < 15 + BB squeeze | Nenhum sinal |
| EUFORIA | RSI médio > 68 + RVOL coletivo > 2x | Apenas SCOUT SHORT |
| PÂNICO | RSI médio < 32 + dump coordenado | Apenas SCOUT LONG (reversão) |

## Como usar esta skill

Cole o diagnóstico atual do Telegram ou descreva o que o mercado está fazendo.

Com base no contexto:

1. **Identificar o regime atual** usando os candidatos do diagnóstico:
   - RSI médio (`_rsi_med` do `_enviar_diagnostico`)
   - Proporção LONG vs SHORT candidatos
   - ADX médio dos candidatos
   - Quantidade de moedas com `tbull_r` vs `tbear_r`

2. **Verificar se o código atual implementa** detecção de regime:
   - Checar `cycles.py` por variáveis `_regime`, `_market_regime` ou similar
   - Checar se `_diag_buffer` calcula RSI médio do mercado

3. **Propor ou aplicar a implementação** em `cycles.py`:
   ```python
   # No início de executar_ciclo, após acumular candidatos:
   _rsi_med_global = media dos RSI de todas moedas analisadas
   _adx_med_global = media dos ADX
   _n_bull = contagem de score > 0
   _n_bear = contagem de score < 0
   
   if _adx_med_global < 15:
       _regime = "LATERAL"    # bloqueia tudo
   elif _rsi_med_global > 68 and _n_bull > _n_bear * 2:
       _regime = "EUFORIA"    # só SCOUT SHORT
   elif _rsi_med_global < 32 and _n_bear > _n_bull * 2:
       _regime = "PANICO"     # só SCOUT LONG
   elif _adx_med_global > 25:
       _regime = "TENDENCIA_FORTE"   # PREMIUM + SCOUT_FLEX
   else:
       _regime = "TENDENCIA_FRACA"   # só SCOUT_FLEX
   ```

4. **Fazer commit + push + disparar novo run** se aprovado pelo usuário.

## Impacto esperado
- Elimina sinais LONG em mercado eufórico (RSI > 68)
- Elimina sinais SHORT em mercado em pânico (RSI < 32)
- Bloqueia tudo em mercado lateral (ADX < 15)
- Melhora Profit Factor ao concentrar operações no regime certo
