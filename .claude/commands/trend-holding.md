Implementa ou melhora o motor de manutenção de tendência no GAUSS+DNA.

## O que é Trend Holding

Evita saídas prematuras. Só sair quando a estrutura de fato quebrou:

| Critério de saída | O que significa |
|-------------------|----------------|
| MM10 cruzou MM21 | Momentum de curto prazo virou |
| Fluxo ficou negativo | DNA Flow, Trendilo e Kalman todos contra |
| Volume secou | RVOL caiu abaixo de 0.5x — sem força |
| Estrutura rompeu | Preço fechou abaixo da MM21 (LONG) ou acima (SHORT) |

**Todos os 4 precisam confirmar** (ou 3 dos 4 com força) antes de sair.

## Aplicação no GAUSS+DNA

O bot atualmente usa:
- TP1 (1R) / TP2 (2R) fixos
- Stop de 1.5 ATR fixo

A Trend Holding melhora isso com **trailing dinâmico**:
```
LONG aberto:
  - Stop inicial: entrada - 1.5 ATR
  - Após TP1: mover stop para entrada (breakeven)
  - Trailing: acompanhar MM21 (stop = MM21 - 0.5 ATR)
  - Saída forçada quando: MM10 < MM21 E (fluxo_negativo OU volume_secou)

SHORT aberto:
  - Stop inicial: entrada + 1.5 ATR
  - Após TP1: mover stop para entrada
  - Trailing: acompanhar MM21 (stop = MM21 + 0.5 ATR)
  - Saída forçada quando: MM10 > MM21 E (fluxo_negativo OU volume_secou)
```

## Como usar esta skill

Descreva o comportamento de saída que quer melhorar (ex: "o bot vende cedo demais" ou "quero trailing após TP1").

Com base no pedido:

1. **Verificar** se o bot já tem lógica de trailing ou gerenciamento pós-entrada
2. **Implementar** os critérios de saída baseados em estrutura (não só ATR fixo)
3. **Adicionar ao notify.py** instruções de trailing para o operador:
   ```
   📌 GESTÃO APÓS ENTRADA:
   TP1 atingido → mova stop para entrada
   Trailing: siga a MM21 (-0.5 ATR)
   Só saia se: MM10 cruzar MM21 + volume secar
   ```
4. **Fazer commit + push + disparar novo run** se aprovado.

## Impacto esperado
- Captura moves de 3R-5R em tendências fortes
- Elimina saídas em correções normais (bear trap, bull trap de curto prazo)
- Melhora ratio médio de gain por operação
