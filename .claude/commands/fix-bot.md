Faz um ajuste cirúrgico no código do bot para desbloquear sinais, commit e push automático.

O usuário descreve o problema ou passa o diagnóstico. Com base nisso:

1. **Identificar o arquivo e linha exata** a modificar (analyze.py, cycles.py ou notify.py).
2. **Fazer o ajuste mínimo** necessário sem quebrar outras regras (consultar CLAUDE.md para restrições permanentes).
3. **Verificar** com `python3 -c "import analyze; import cycles; import notify; print('OK')"`.
4. **Commit** na branch `main` com mensagem descritiva do fix.
5. **Push** para origin main.
6. **Cancelar run atual** se houver (mcp__github__actions_list → mcp__github__actions_run_trigger cancel).
7. **Disparar novo run** (mcp__github__actions_run_trigger run_workflow, ref: main, filter_level: 3, timeframes: 15m).

Regras que NUNCA podem ser violadas (CLAUDE.md):
- RSI LONG < 55 (rsi_zona_long) — não relaxar sem autorização explícita
- RSI SHORT > 40 (rsi_zona_short) — não relaxar sem autorização explícita
- Defesas SMC: not liq_topo para LONG, not liq_fundo para SHORT (exceto SURGE)
