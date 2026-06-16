Verifica o status atual do GAUSS+DNA bot no GitHub Actions.

Passos:
1. Listar últimos 3 runs com `mcp__github__actions_list` (list_workflow_runs, repo: gauss-dna, owner: josubazilio-sudo, per_page: 3, resource_id: bot.yml).
2. Para o run mais recente, obter os jobs com `mcp__github__actions_list` (list_workflow_jobs).
3. Para o job em andamento ou mais recente, tentar obter logs com `mcp__github__get_job_logs` (tail_lines: 80, return_content: true). Se retornar 404 (job ainda rodando), informar que os logs ainda não estão disponíveis.
4. Reportar ao usuário:
   - Status do run (in_progress / completed / cancelled / failed)
   - Branch e commit SHA (7 chars)
   - Há quanto tempo está rodando
   - Etapa atual (qual step está in_progress)
   - Se tiver logs: últimas linhas relevantes (sinais encontrados, bloqueadores, diagnóstico)
