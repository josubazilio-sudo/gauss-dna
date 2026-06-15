Analisa o diagnóstico do GAUSS+DNA e identifica o que está bloqueando os sinais.

O usuário vai colar o texto do diagnóstico do Telegram (começa com "DIAGNOSTICO GAUSS+DNA").

Com base no diagnóstico recebido:

1. **Identificar o contexto de mercado**: RSI médio, quantos LONG vs SHORT candidatos.

2. **Analisar os bloqueadores mais frequentes** (lista numerada do diagnóstico):
   - `inst=X<60/70` → score institucional insuficiente (qual dos 9 fatores falta: tendência, ADX, DNA Flow, HA, Trendilo, RSI subindo, volume, divergência, SM)
   - `rsi=X(fora 40-75)` → RSI fora da janela LONG (aguardar RSI entrar em 40-75)
   - `rsi=X(fora 25-60)` → RSI fora da janela SHORT (aguardar RSI entrar em 25-60)
   - `rvol=X<1.2` → volume insuficiente (mercado sem momentum)
   - `adx=X<=15` → mercado lateral (aguardar ADX > 15)
   - `scout=X/8<5` → scout_score insuficiente (quais dos 8 critérios estão faltando: DNA Flow, OBV, MM10>MM21, MM21>MM50, volume, tbull_r, rompimento, HA)
   - `3velas_exp` → 3 velas explosivas consecutivas (anti-FOMO ativo — aguardar pullback)
   - `ext_e21>5%` → preço >5% acima da EMA21 (sobreextendido)
   - `H4 forte oposto` → H4 contradiz o sinal
   - `lateral` → BB squeeze
   - `liq_topo/fundo` → Smart Money liquidity sweep recente

3. **Analisar os candidatos mais próximos** e dizer qual filtro específico está bloqueando cada um.

4. **Propor ação**: 
   - Se bloqueador é de mercado (RSI médio, ADX < 15, lateral) → aguardar
   - Se bloqueador é de filtro (scout_score, inst, rvol) → ajuste cirúrgico possível
   - Se bloqueador é anti-FOMO → sinal chega no próximo pullback

5. **Perguntar ao usuário** se quer aplicar o ajuste proposto.
