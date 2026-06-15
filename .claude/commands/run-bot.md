Dispara o GAUSS+DNA bot via GitHub Actions na branch `main`.

Passos:
1. Verificar se já existe run `in_progress` usando `mcp__github__actions_list` (list_workflow_runs, repo: gauss-dna, owner: josubazilio-sudo, per_page: 2). Se houver, cancelar com `mcp__github__actions_run_trigger` (cancel_workflow_run) antes de disparar novo.
2. Disparar novo run com `mcp__github__actions_run_trigger` (run_workflow, ref: main, workflow_id: bot.yml, owner: josubazilio-sudo, repo: gauss-dna) com inputs: `{"filter_level": "3", "test_mode": "false", "timeframes": "15m"}`.
3. Confirmar ao usuário que o run foi disparado.

Se o usuário passar argumento (ex: `/run-bot test`), usar `test_mode: "true"`. Se passar timeframe (ex: `/run-bot 1h`), usar esse timeframe.
