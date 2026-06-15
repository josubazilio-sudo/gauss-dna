Analisa e melhora a detecção de varreduras de liquidez (Smart Money) no GAUSS+DNA.

## O que é Liquidity Sweep Detector

Instituições varreram liquidez antes de entrar. Entrar DEPOIS do sweep é muito mais seguro:

| Padrão | O que é | Ação |
|--------|---------|------|
| Varredura de topo | Preço rompeu máxima recente e voltou (wick) | Sinal SHORT após retorno |
| Varredura de fundo | Preço rompeu mínima recente e voltou (wick) | Sinal LONG após retorno |
| Falso rompimento | Rompeu nível + voltou em 1-2 velas | LONG/SHORT na direção oposta |
| Retorno à estrutura | Preço voltou para dentro do range após sweep | Entrada confirmada |

**Regra de ouro:** ❌ Nunca comprar no rompimento. ✅ Comprar após limpar liquidez e recuperar estrutura.

## O que o código já tem

- `liq_topo` / `liq_fundo` — detecta varredura recente (5 velas)
- `liq_topo_hist10` / `liq_fundo_hist10` — histórico de 10 velas
- `absorb_bull` / `absorb_bear` — absorção institucional após sweep
- `sm_bull` / `sm_bear` — confirmação Smart Money

## Como usar esta skill

Descreva o comportamento que quer melhorar ou cole o diagnóstico.

Com base no pedido:

1. **Checar implementação atual** em `analyze.py`:
   - `liq_topo`, `liq_fundo` (definição, threshold de wick)
   - `absorb_bull`, `absorb_bear` (como detectam absorção)
   - Como `sm_bull`/`sm_bear` usa esses dados

2. **Evoluções possíveis:**
   ```python
   # Retorno à estrutura após sweep (2-3 velas de recuperação)
   retorno_bull = liq_fundo and preco > swing_low * 1.005 and ha_bull_1
   retorno_bear = liq_topo  and preco < swing_high * 0.995 and ha_bear_1
   
   # Falso rompimento: preço cruzou nível mas voltou rápido
   fakeout_bull = (min(lows[-3:]) < swing_low) and (preco > swing_low) and ha_bull
   fakeout_bear = (max(highs[-3:]) > swing_high) and (preco < swing_high) and ha_bear
   ```

3. **Ajustar PREMIUM** para favorecer entradas pós-sweep:
   - Adicionar bônus de confiança quando `liq_fundo_hist10` (LONG) ou `liq_topo_hist10` (SHORT) detectado
   - SCOUT_FLEX pode incluir `retorno_bull`/`retorno_bear` no `scout_score`

4. **Fazer commit + push + disparar novo run** se aprovado.

## Impacto esperado
- Elimina entradas em rompimentos falsos
- Concentra LONGs em zonas pós-limpeza de fundo
- Concentra SHORTs em zonas pós-limpeza de topo
- Aumenta taxa de acerto em 15-25% típico
