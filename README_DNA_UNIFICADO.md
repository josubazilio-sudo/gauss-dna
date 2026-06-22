# DNA INSTITUCIONAL UNIFICADO [GAUSS+DNA]

Indicador Pine Script v6 que combina os dois códigos originais com as configurações do bot GAUSS+DNA.

## Arquivo
- `dna_institucional_unificado.pine` — Copie e cole no TradingView

## O que foi unificado

### Do DNA MACD HA v4:
- ✅ MACD com Heikin Ashi suavizado
- ✅ EMA 10/21/50/200
- ✅ ADX com filtros
- ✅ Fluxo institucional
- ✅ Impulso e sweep de liquidez
- ✅ Stop ATR com TP1 e alvo final
- ✅ Break Even e Trailing

### Do DNA ELITE KALMAN:
- ✅ Kalman Filter (rápido/lento)
- ✅ RSI com zonas e divergência
- ✅ Absorção de preço
- ✅ Exaustão MACD
- ✅ Cooldown dinâmico
- ✅ Reversão precoce
- ✅ Tabela R/R visual

### Das configurações GAUSS+DNA:
- ✅ **REGRA #1**: RSI LONG < 75, SHORT > 25
- ✅ **REGRA #2**: vol_nao_fade com 0.80
- ✅ **CORE**: 11 critérios do operador
- ✅ **Alavancagem**: 3x-20x dinâmica
- ✅ **Stop CORE**: 1.5 ATR
- ✅ **Score inst mínimo**: 25 (CORE)
- ✅ **Sessão perigosa**: +10 inst_min

## Configurações dos Inputs

### TENDÊNCIA
| Input | Default | Descrição |
|-------|---------|-----------|
| EMA10 | 10 | EMA rápida |
| EMA21 | 21 | EMA curto prazo |
| EMA50 | 50 | EMA médio prazo |
| EMA200 | 200 | EMA longo prazo |

### MACD
| Input | Default | Descrição |
|-------|---------|-----------|
| Fast | 12 | EMA rápida MACD |
| Slow | 26 | EMA lenta MACD |
| Signal | 9 | Sinal MACD |

### RSI (REGRA #1)
| Input | Default | Descrição |
|-------|---------|-----------|
| RSI Período | 14 | Período do RSI |
| Sobrecomprado | 75 | Bloqueia LONG se > 75 |
| Sobrevendido | 25 | Bloqueia SHORT se < 25 |
| Zona Média LONG | 55 | Acima disso, degrada score |
| Zona Média SHORT | 40 | Abaixo disso, degrada score |

### KALMAN
| Input | Default | Descrição |
|-------|---------|-----------|
| Rápido | 50 | Kalman curto prazo |
| Lento | 150 | Kalman longo prazo |
| Usar no Filtro | true | Incluir Kalman nas condições |

### FILTROS
| Input | Default | Descrição |
|-------|---------|-----------|
| ADX Período | 14 | Período ADX |
| ADX Mín LONG | 18 | CORE: adx >= 18 |
| ADX Mín SHORT | 18 | CORE: adx >= 18 |
| ADX Forte | 28 | Tendência forte |
| Volume Fade | 0.80 | REGRA #2: vol_nao_fade |
| Volume Forte | 1.5 | RVOL >= 1.5x |

### GESTÃO DE RISCO
| Input | Default | Descrição |
|-------|---------|-----------|
| Risco/Trade | 2% | 1-3% institucional |
| Alavancagem Base | 10x | 3x-20x dinâmica |
| STOP ATR | 1.5 | CORE: 1.5 ATR |
| TP1 R:R | 1.5 | Take profit 1 |
| Alvo Final | 3.5 | Take profit final |
| Fechar TP1 | 35% | % posição em TP1 |

## Sinais

### LONG CORE (11 critérios)
1. RSI 45-58 com momentum ascendente
2. ADX >= 18
3. Volume não fade
4. Volume não secando
5. Kalman bullish
6. Fluxo bullish
7. Preço > EMA21 e EMA10 > EMA21
8. HA bullish
9. Sem sweep de liquidez
10. Preço > EMA200
11. Preço ≤ EMA21 * 1.02

### SHORT CORE (11 critérios)
1. RSI 42-55 com momentum descendente
2. ADX >= 18
3. Volume não fade
4. Volume não secando
5. Kalman bearish
6. Fluxo bearish
7. Preço < EMA21 e EMA10 < EMA21
8. HA bearish
9. Sem sweep de liquidez
10. Preço < EMA200
11. Preço ≥ EMA21 * 0.98

## Tabela Institutional

Mostra no canto superior direito:
- Score Institucional (0-100)
- Score LONG (direcional)
- Alavancagem dinâmica
- Risco efetivo
- R:R TP1 e Final
- RSI atual
- ADX atual
- Kalman (BULL/BEAR)
- Fluxo (BULL/BEAR)
- Volume (FORTE/OK/FRACO)
- Sessão (PERIGOSA/SEGURA)

## Alertas

- `LONG` — Sinal de compra
- `SHORT` — Sinal de venda
- `EXIT` — Saida estrutural

## Como usar

1. Abra TradingView
2. Vá em Pine Editor
3. Cole o código de `dna_institucional_unificado.pine`
4. Clique em "Adicionar ao gráfico"
5. Configure os inputs conforme sua estratégia
6. Ative os alertas para notificações

## Notas

- O indicador é `indicator()`, não `strategy()` — não executa trades
- Use os alertas para integrar com bots de trading
- Kalman Filter suaviza o preço e identifica mudanças de tendência
- RSI segue estritamente a REGRA #1 do GAUSS+DNA
- Alavancagem calculada automaticamente conforme score e volume
