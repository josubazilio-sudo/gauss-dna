Loop completo de resolução do GAUSS+DNA: resume o estado, diagnostica, corrige e dispara — tudo em uma única chamada.

Use este comando quando quiser o ciclo inteiro da REGRA #0 (CLAUDE.md) executado de forma autônoma, sem precisar pedir confirmação a cada etapa.

## Passos

1. **Resumir estado atual**
   - `git log --oneline -10` para ver os últimos commits e identificar o ponto de referência funcional mais recente.
   - `git status` para confirmar que não há mudanças pendentes não commitadas.
   - `mcp__github__actions_list` (list_workflow_runs, repo: gauss-dna, owner: josubazilio-sudo, per_page: 3, resource_id: bot.yml) para ver o status do(s) último(s) run(s).
   - Se houver run `in_progress`, obter logs com `mcp__github__get_job_logs` (tail_lines: 150). Se 404 (job ainda rodando), aguardar antes de tentar de novo — nunca usar `sleep` longo, usar `run_in_background` + Monitor.

2. **Diagnosticar**
   - Procurar no log/diagnóstico (texto `[DIAG]` ou mensagem "DIAGNOSTICO GAUSS+DNA") os bloqueadores mais frequentes por moeda (ver tabela "BLOQUEADORES MAIS COMUNS" em CLAUDE.md).
   - Identificar o candidato mais próximo de disparar e qual condição específica (RSI, ADX, RVOL, inst, fluxo, grade) está impedindo.
   - Verificar contradições lógicas entre filtros (ex.: filtro de tendência bloqueando um sinal de reversão).

3. **Resolver com eficiência**
   - Aplicar o ajuste mais cirúrgico possível em `analyze.py`, `cycles.py` ou `notify.py` — mudar o mínimo de linhas necessárias.
   - **Nunca violar**: RSI zona LONG `< 75` / SHORT `> 25` (REGRA #1, FLEX PRO 15/06), defesas SMC (`not liq_topo` LONG / `not liq_fundo` SHORT, exceto SURGE/REVERSAL/SM_SWEEP/EXTREME/CORE/DIV/REBOUND/PUMP/DUMP que são contra-tendência por desenho).
   - Verificar sintaxe: `python3 -c "import analyze; import cycles; import notify; print('OK')"`.

4. **Commit, push e disparar**
   - Commit na branch atual (`git rev-parse --abbrev-ref HEAD` — NUNCA assumir `main`; respeitar a branch designada da sessão) com mensagem descritiva do que foi corrigido e por quê.
   - Push: `git push -u origin <branch-atual>`.
   - Cancelar run anterior se ainda `in_progress` (`mcp__github__actions_run_trigger` cancel_workflow_run).
   - Disparar novo run (`mcp__github__actions_run_trigger` run_workflow, ref: branch atual, workflow_id: bot.yml, inputs: `{"filter_level": "3", "test_mode": "false", "timeframes": "1h"}`).

5. **Organizar**
   - Atualizar mentalmente (e reportar ao usuário em poucas linhas) o que mudou desde o último ciclo: o que foi corrigido, o que ainda está pendente, e qual é o próximo bloqueador esperado.
   - Se notar dívida técnica recorrente (código morto, função nunca chamada, lógica duplicada), apontar — mas só refatorar se isso for o ajuste cirúrgico necessário, não como tarefa extra.

6. **Repetir**
   - Por REGRA #0, não parar em estado de "sem sinal". Se o novo run também não disparar sinal, voltar ao passo 2 com o diagnóstico mais recente.
   - Parar apenas quando: sinal disparar, usuário confirmar recebimento, ou usuário pedir para parar.

Reporte sempre em formato curto: estado anterior → o que foi corrigido → ação disparada → o que esperar do próximo ciclo.
