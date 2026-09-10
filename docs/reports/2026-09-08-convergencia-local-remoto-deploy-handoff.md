# Handoff operacional — convergência local, remoto e deploy

**Data da fotografia:** 2026-09-08 (America/Sao_Paulo)  
**Repositório:** `nelsonboulangerie/django-shopman`  
**Objetivo deste trabalho:** estabilizar e reconciliar todo o estado local, remoto, CI e deploy antes de uma futura revisão de prontidão para go-live.  
**Fora de escopo:** realizar agora uma nova revisão funcional, contratual, de segurança ou de UX do produto.

## Ordem explícita ao agente executor

Este documento é um **handoff para execução**, não apenas uma lista de observações.

O agente que receber este relatório deve:

1. **Refazer a auditoria a partir do estado atual**, após um novo `fetch --all --prune --tags`. Não assumir que esta fotografia ainda é verdadeira.
2. **Confrontar três fontes de evidência:**
   - suas medições novas;
   - sua própria análise imediatamente anterior;
   - os achados registrados neste relatório.
3. Para cada divergência relevante, registrar `CONFIRMADO`, `ALTERADO` ou `REFUTADO`, com comando, SHA, URL de run/PR/deployment ou outro artefato verificável.
4. **Executar a convergência**, incluindo correções, preservação, decisões sobre refs, limpeza segura, atualização local, resolução de PRs e validação do deploy. Não encerrar entregando somente outro diagnóstico.
5. Trabalhar em worktree/branch isolado. O checkout raiz é compartilhado e não deve ser alterado enquanto houver sessões ou worktrees que dependam dele.
6. Antes de excluir branch, worktree, objeto Git ou arquivo local, produzir e validar os artefatos de recuperação descritos neste relatório.
7. Não contornar proteção de branch, revisão obrigatória, merge queue, checks, bloqueios de worktree ou ownership de sessão.
8. Encerrar com um relatório final de execução contendo estado anterior, ações tomadas, refs removidas ou mantidas, commits/PRs, checks, SHA implantado e qualquer exceção residual com proprietário e prazo.

O mantra do projeto continua aplicável quando alguma divergência exigir interpretar comportamento funcional: **“Desconfie da implementação, confie no Core.”** Uma aparente necessidade de alterar o Core deve ser tratada primeiro como possível interpretação insuficiente de suas capacidades. Neste trabalho de convergência, porém, não ampliar o escopo para uma nova revisão de go-live.

## Critério de conclusão

O trabalho só pode ser declarado concluído quando todos os itens abaixo forem verdadeiros ou houver uma exceção explícita, justificada e aceita pelo proprietário:

- o `main` local canônico aponta para o mesmo SHA de `origin/main`;
- o checkout canônico está limpo;
- não há stash desconhecido;
- não há worktree dirty sem conteúdo preservado e decisão documentada;
- todo worktree remanescente está limpo, ativo e com proprietário conhecido;
- não há branch local-only sem classificação e destino documentados;
- não há commit ou objeto Git potencialmente útil sendo descartado sem backup recuperável;
- não há branch remota stale sem classificação e decisão documentadas;
- cada PR aberto tem uma ação deliberada: atualizado e mergeado, mantido com justificativa, ou fechado com justificativa;
- os checks obrigatórios do SHA final estão verdes;
- o Alpha Smoke disparado pelo `workflow_run` de Deploy Images conclui com sucesso e efetivamente executa as asserções;
- as tags mutáveis de imagens apontam para imagens imutáveis cuja proveniência é explicável por componente;
- o deployment ativo no DigitalOcean está saudável e consistente com as imagens esperadas;
- a verificação canônica de drift da App Platform conclui com sucesso;
- readiness, API de menu, SSR do storefront e contrato negativo mínimo do checkout passam no ambiente implantado;
- o relatório final contém timestamp, SHAs, URLs, inventário de backup e uma declaração inequívoca sobre pendências restantes.

“Tudo estabilizado” não significa necessariamente mergear todos os PRs ou manter todas as branches. Significa que cada item recebeu uma decisão tecnicamente sustentada e que nenhum estado relevante ficou oculto ou não preservado.

## Fotografia encontrada em 2026-09-08

Os dados abaixo são evidência histórica para comparação. Eles **não substituem a nova medição obrigatória**.

### Baseline Git

- `origin/main`: `47d0b854b1086c1d5a172333f22e5ae9fab4c531`
- commit: `Merge pull request #564 from nelsonboulangerie/claude/o-desfazer-da-unificacao-chega-ao-balcao`
- `main` local: `291e0e0638256dc7a56aaabd0046654fb3b6db09`
- relação do `main` local com `origin/main`: 0 à frente, 24 atrás;
- checkout raiz em `codex/pdp-bg`: `b589e22c5`, 0 à frente e 644 atrás de `origin/main`;
- tags locais e remotas sincronizadas;
- nenhum stash encontrado;
- nenhum submódulo;
- Git LFS não estava instalado e o repositório não aparentava usar LFS;
- 449 branches locais;
- 46 worktrees registrados, sendo 15 dirty e 2 locked.

### Branches locais com commits não alcançáveis por refs remotas

Foram encontradas 15 branches nessa categoria:

```text
claude/alerta-sem-rotulo-no-cracha
claude/critical-fixes-notifications-67d7b2
claude/focused-faraday-878c13
claude/mystifying-kirch-a27a94
claude/shopman-adversarial-analysis-1f3ed2
claude/whatsapp-templates-guia
codex/alpha-readiness-audit
fix/402-bool
merge/alpha-rev-2026-08-28
plano/packs-como-bundle
worktree-agent-a57a143b45603a49d
worktree-agent-a9dcb2429a9654551
worktree-agent-ab9f9a2b2db285241
worktree-pos-qa-round2
worktree-suite-roda-como-o-staging
```

A comparação por `git cherry`, conteúdo de blobs e histórico semântico não identificou candidato claro a merge: a maior parte parecia patch-equivalente, incorporada, supersedida ou criada como snapshot. Isso **não autoriza exclusão automática**. Refazer a comparação e preservar todas as refs local-only antes da limpeza.

### Worktrees dirty

| Worktree/branch | Fotografia do estado | Avaliação preliminar |
|---|---:|---|
| checkout raiz `codex/pdp-bg` | 0 tracked, 7 entradas untracked | artefatos e documentos locais; classificar antes de atualizar o checkout |
| `worktree-agent-ab9f9a2b2db285241` | 1 tracked | comparar com `origin/main` |
| `claude/revisao-alpha-storefront` | 1 tracked | comparar com `origin/main` |
| `claude/wp-rename-chaves-legadas` | 7 tracked, 1 untracked | majoritariamente supersedido; contém tentativa de editar migration aplicada |
| `claude/execute-report-safely-6fad7f` | 2 untracked | scripts locais de QA; decidir promoção ou arquivo |
| `claude/elated-bhabha-811091` | 1 tracked | comparar com `origin/main` |
| `claude/pensive-jennings-190aac` | 2 tracked | rascunho anterior a mudanças já mergeadas |
| `claude/login-preserva-destino` | 1 tracked | comparar com `origin/main` |
| `claude/loja-botao-entrar` | 1 tracked | comparar com `origin/main` |
| `claude/multiple-fixes-pdp-sms-pdv-4d5431` | 374 staged | nenhum blob novo identificado; snapshot de versões atuais/históricas |
| `claude/header-anchoring-feedback` | 1 tracked | comparar com `origin/main` |
| `claude/receitas-paes-producao-26a519` | 1 untracked | brief idêntico ao arquivo atual de `main` |
| `claude/storefront-env-ribbon` | 1 tracked | comparar com `origin/main` |
| `codex/manychat-availability-phrase` | 13 tracked, 1 untracked | blobs atuais ou históricos de `main`; nenhum blob único identificado |
| `codex/buyman-nuxt-interface` | 15 tracked, 6 untracked | protótipo antigo aparentemente supersedido por `purchase-nuxt`; preservar antes de remover |

Detalhes que devem ser explicitamente revalidados:

- Em `claude/multiple-fixes-pdp-sms-pdv-4d5431`, 319 dos 374 blobs staged eram idênticos ao `main` atual e os outros 55 existiam no histórico de `main`; nenhum blob único foi encontrado.
- Vários diffs de um único `.nuxtrc` eram idênticos ao arquivo atual de `main`, artefatos de branches antigas.
- Em `claude/wp-rename-chaves-legadas`, quatro patches correspondiam ao commit mergeado `fc19f2026`; mudanças restantes incluíam uma edição da migration aplicada `0033`, abordagem rejeitada pelo histórico mergeado em favor da migration nova `0035`.
- Em `claude/pensive-jennings-190aac`, os dois arquivos dirty eram rascunhos anteriores aos commits mergeados `ce6ec38d5` e `8f1de27c4`; o `main` estava mais completo.
- `codex/buyman-nuxt-interface` estava fora da árvore principal, em `/Users/pablovalentini/Documents/Codex/2026-08-25/revisar/work/django-shopman-buyman-nuxt`.
- `claude/execute-report-safely-6fad7f` continha dois scripts untracked que podem merecer formalização como teste/ferramenta ou arquivo local:
  - `surfaces/orders-nuxt/prova-clique.mjs`
  - `surfaces/orders-nuxt/prova-feeds.mjs`

### Worktrees locked

```text
/Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/agent-ab3dc373225cb0b4c
/Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/agent-ad44b5a41338740f7
```

Na fotografia, o lock tinha como proprietário o PID `7002`, um processo ativo do Claude Code com sessão retomada. **Não desbloquear, remover, matar o processo ou apagar esses diretórios sem confirmar que o proprietário encerrou o trabalho e que o conteúdo foi preservado.**

### Artefatos no checkout raiz

- `.alpha-tmp/`: cerca de 19 MB de screenshots, logs, scripts e relatórios de QA. Pode conter sessão, cliente ou dados de teste. Não commitar em massa. Revisar de forma segura e então arquivar localmente fora do repo ou excluir.
- `.worktrees/`: cerca de 105 MB e contém worktrees registrados. Nunca remover com `rm -rf`; usar a interface do Git após preservação e confirmação de ownership.
- `docs/plans/backstage-app-audits-2026-08-29/`: cerca de 208 KB; todos os arquivos encontrados eram idênticos a arquivos já rastreados em `origin/main`. Devem deixar de aparecer como untracked quando o checkout raiz for atualizado corretamente.
- quatro relatórios locais de 2026-08-28 aparentavam registrar tarefas já concluídas ou supersedidas. A recomendação preliminar é arquivo local fora do repositório, não commit, salvo se a nova revisão provar valor permanente:
  - `docs/reports/2026-08-28-prompt-claude-tudo.md`
  - `docs/reports/2026-08-28-prompt-correcoes-gestor-pedidos.md`
  - `docs/reports/2026-08-28-prompt-p1e-do.md`
  - `docs/reports/2026-08-28-revisao-alpha-gestor-pedidos.md`

### Objetos Git inalcançáveis

`git fsck` encontrou 801 commits inalcançáveis, 137 posteriores a 2026-08-28. Entre esses 137:

- 115 tinham subject exato já presente em `main`;
- 1 tinha subject exato em outra ref alcançável;
- 21 não tinham subject exato alcançável.

Os 21 restantes aparentavam conter tentativas antigas do Dependabot, WIP/stash/index, simulações de merge, um rescue desatualizado de `apply_catalog_taxonomy`, uma tentativa do componente de planilha de compras e prova temporária. Essa triagem não é prova suficiente para descarte.

**Não executar `git gc`, `git prune` ou manutenção que possa eliminar objetos até haver backup completo e validado do diretório `.git`.** Um `git bundle --all` preserva refs alcançáveis, mas não preserva sozinho objetos inalcançáveis nem arquivos não commitados.

### Pull requests abertos

Não havia PR humano aberto. Havia sete PRs do Dependabot, todos reportados como `MERGEABLE`, porém `BLOCKED`:

| PR | Escopo | Checks na fotografia | Ação exigida |
|---|---|---:|---|
| [#550](https://github.com/nelsonboulangerie/django-shopman/pull/550) | grupo de runtime Python | 11 success, 14 failure | atualizar/rebasear, diagnosticar em `main` atual, testar e decidir |
| [#428](https://github.com/nelsonboulangerie/django-shopman/pull/428) | grupo de build tooling | 15 success, 10 failure | atualizar/rebasear, diagnosticar em `main` atual, testar e decidir |
| [#427](https://github.com/nelsonboulangerie/django-shopman/pull/427) | Nuxt framework | 24 success, 1 failure | atualizar/rebasear, diagnosticar em `main` atual, testar e decidir |
| [#235](https://github.com/nelsonboulangerie/django-shopman/pull/235) | `webauthn` 3 | 19 success, 1 failure | atualizar/rebasear, diagnosticar em `main` atual, testar e decidir |
| [#234](https://github.com/nelsonboulangerie/django-shopman/pull/234) | `qrcode` 8.2 | 20 success, 0 failure | resolver policy/review e decidir merge ou fechamento justificado |
| [#233](https://github.com/nelsonboulangerie/django-shopman/pull/233) | `django-filter` 26.1 | 18 success, 0 failure | resolver policy/review e decidir merge ou fechamento justificado |
| [#232](https://github.com/nelsonboulangerie/django-shopman/pull/232) | `cbor2` 6.1.4 | 19 success, 1 failure | atualizar/rebasear, diagnosticar em `main` atual, testar e decidir |

Executar um PR por vez contra o `main` mais novo, rodar checks proporcionais e completos quando exigidos, e integrar somente pelo fluxo normal de proteção/merge queue. Se um PR estiver supersedido, incompatível ou inseguro, fechá-lo com justificativa verificável. Não silenciar falhas nem contornar proteção.

### Branches remotas apontadas como “unmerged”

Além das sete branches dos PRs do Dependabot, o script de auditoria apontou sete branches aparentemente stale/supersedidas:

| Branch | Evidência preliminar |
|---|---|
| `claude/ficha-de-produto-e-promessa` | patch-equivalente a `main` segundo `git cherry` |
| `claude/intelligent-chaum-8d76b5` | PR #368 fechado como supersedido por `main` |
| `claude/nervous-wilbur-14717c` | PR #563 fechado como supersedido pelo #559 mergeado |
| `docs/repo-hygiene-proposal` | PR #201 fechado; itens depois resolvidos pelo #366 |
| `feat/badge-issue-screen` | PR #135 foi mergeado; falso positivo do limite do script |
| `feat/pos-event-log` | PR #198 fechado por decisão do proprietário; partes sobreviventes migradas para Cashman |
| `safety/preserve-current-work-20260828-login-handoff` | snapshot explícito; código encontrado em `main` atual/histórico, divergindo apenas em artefatos antigos de teste/screenshot |

O script `scripts/audit-branches.sh` usava `MERGED_PR_LIMIT=300`, por isso o PR antigo #135 não entrou na janela e virou falso positivo. O executor deve corrigir a auditoria para paginação robusta ou limite suficiente, com uma proteção de regressão adequada, e então repetir a classificação antes de remover refs remotas.

### CI e deploy

No SHA `47d0b854b1086c1d5a172333f22e5ae9fab4c531`:

- Runtime Gate: success;
- Surfaces Gate: success;
- Omotenashi: success;
- Deploy Images: success;
- Alpha Smoke: cancelled.

O Deploy Images run `34246727705` construiu com sucesso a imagem de `pos-nuxt`.

O deployment ativo da DigitalOcean App Platform era:

```text
app id:      40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f
app name:    shopman-alpha
deployment:  31c462fc-35f7-45f1-8f57-7f6578a6506b
phase:       ACTIVE
progress:    47/47
```

A imagem ativa de POS tinha digest `sha256:33b33...` e correspondia à tag imutável `pos-47d0b854...`.

As tags mutáveis batiam com as tags imutáveis derivadas do último commit de primeira linha de `main` que tocou os filtros de deploy de cada componente:

| Componente | Commit de proveniência encontrado |
|---|---|
| `web` | `e9684d21974e...` |
| `storefront` | `c2aff1628998...` |
| `pos` | `47d0b854b108...` |
| `kds`, `hub`, `bi` | `0f55a6085066...` |
| `orders` | `b2ac4eebb2f3...` |
| `production` | `993c729abb14...` |
| `marketing` | `030c8799ef42...` |
| `purchase` | `8c16aca36c1e...` |

O script canônico `scripts/check_do_spec_drift.py` concluiu com exit code 0 contra o app ativo:

```text
app envs: live=88, versioned=90
domains:  live=12, versioned=12
diferenças versionadas esperadas: FOCUS_NFE_ENVIRONMENT, SENTRY_DSN
[OK] spec_drift
```

Smoke manual do ambiente implantado:

- `STOREFRONT_URL=https://menu.nelsonboulangerie.com.br` na variável do repositório;
- `MENU_MIN_SKUS=30`;
- readiness: HTTP 200;
- API de menu: HTTP 200;
- 44 SKUs, 18 vendáveis;
- checkout vazio: HTTP 400 esperado;
- storefront SSR: HTTP 200, 118337 bytes, contendo “Nelson”.

## Pendência crítica confirmada: Alpha Smoke se autocancela

No `origin/main` auditado, `.github/workflows/alpha-smoke.yml` configurava:

- `timeout-minutes: 5` no job;
- `sleep 420` antes das asserções.

O run `34246964010` foi cancelado exatamente após cinco minutos, antes de executar qualquer smoke. Isso é uma contradição determinística no próprio workflow, não evidência de aplicação saudável nem falha de concorrência.

### Correção obrigatória

O agente deve, em branch/worktree dedicado:

1. Reabrir o workflow atual e confirmar que a contradição ainda existe.
2. Preferir substituir a espera fixa por polling limitado de readiness/deployment, com timeout total explícito e margem para as asserções.
3. Se uma correção mínima for mais segura, aumentar o timeout do job para pelo menos 15 minutos e justificar a margem sobre a espera de 420 segundos.
4. Adicionar um guard/teste estático que impeça o timeout do job de ser menor ou igual à espera máxima somada à margem operacional.
5. Revisar o fallback de `STOREFRONT_URL`: na fotografia, a variável do repositório sobrepunha o fallback antigo para um domínio alpha inativo. Decidir entre usar o domínio canônico atual ou falhar de forma explícita quando a variável não existir; não manter fallback silenciosamente inválido.
6. Rodar lint/validação do YAML, testes do script/guard e checks aplicáveis.
7. Abrir PR, passar pelo fluxo protegido e mergear.
8. Aguardar o Deploy Images correspondente e comprovar que o Alpha Smoke disparado por `workflow_run` — não apenas `workflow_dispatch` — termina `success` e executa as asserções.

## Plano de execução obrigatório

### Fase 0 — congelar e identificar ownership

1. Registrar timestamp, hostname, checkout raiz, SHA e lista de processos/sessões que possuem worktrees.
2. Fazer novo `fetch --all --prune --tags`.
3. Não trocar branch, restaurar arquivos, resetar ou limpar o checkout raiz.
4. Identificar o proprietário dos dois worktrees locked e aguardar autorização/encerramento quando necessário.
5. Criar um worktree limpo a partir do `origin/main` mais novo para toda correção ou automação desta execução.

### Fase 1 — repetir a auditoria independente

No mínimo, repetir e guardar as saídas de:

```bash
git fetch --all --prune --tags
git status --short --branch
git rev-parse origin/main
git rev-list --left-right --count main...origin/main
git branch --format='%(refname:short) %(objectname)' 
git worktree list --porcelain
git stash list
git fsck --full --unreachable --no-reflogs
gh pr list --state open --limit 100 --json number,title,headRefName,baseRefName,isDraft,mergeStateStatus,statusCheckRollup,url
gh run list --branch main --limit 50
```

Também repetir a comparação de refs e conteúdo, sem confiar apenas em nomes de commit:

- `git cherry origin/main <branch>`;
- patch-id quando aplicável;
- comparação de blobs exatos com `origin/main` e seu histórico;
- PR associado, estado real e motivo de fechamento/merge;
- conteúdo untracked e possível sensibilidade de dados;
- última mudança de primeira linha que afeta cada componente implantável.

Produzir uma tabela de reconciliação entre a nova auditoria, a análise anterior do próprio agente e esta fotografia.

### Fase 2 — preservar antes de limpar

Escolher um diretório **durável, explícito e fora do repositório** para o backup. Não usar o próprio checkout, uma variável de caminho não resolvida ou um diretório temporário que será automaticamente apagado.

Criar e validar, no mínimo:

1. archive completo do diretório `.git`, preservando objetos inalcançáveis e reflogs;
2. `git bundle --all` para todas as refs alcançáveis;
3. manifesto de branches, tags, worktrees, locks, stashes, remotes e SHAs;
4. patch binário de tracked/staged para cada worktree dirty;
5. archive dos arquivos untracked de cada worktree dirty;
6. archive separado dos artefatos raiz que forem mantidos;
7. checksums dos arquivos de backup;
8. teste de leitura do tar, `git bundle verify` e, idealmente, restauração de amostra em diretório descartável.

Exemplo de sequência, que deve ser adaptada a caminhos explícitos e validados:

```bash
repo_root=/Users/pablovalentini/Dev/Claude/django-shopman
backup_root=/CAMINHO/DURAVEL/django-shopman-convergence-20260908-HHMMSS

test -d "$repo_root/.git"
test "$backup_root" != "$repo_root"
mkdir -p "$backup_root/worktrees"

tar -czf "$backup_root/git-metadata.tar.gz" -C "$repo_root" .git
tar -tzf "$backup_root/git-metadata.tar.gz" >/dev/null

git -C "$repo_root" bundle create "$backup_root/reachable-refs.bundle" --all
git -C "$repo_root" bundle verify "$backup_root/reachable-refs.bundle"

git -C "$repo_root" show-ref > "$backup_root/show-ref.txt"
git -C "$repo_root" worktree list --porcelain > "$backup_root/worktrees.txt"
git -C "$repo_root" stash list > "$backup_root/stashes.txt"
git -C "$repo_root" fsck --full --unreachable --no-reflogs > "$backup_root/fsck-unreachable.txt" 2>&1
```

Para cada worktree dirty, salvar `status`, `diff HEAD`, `diff --cached`, lista de untracked e o conteúdo untracked. Usar nomes de arquivo derivados de um identificador seguro, não do caminho bruto.

```bash
git -C "$worktree_path" status --porcelain=v1 > "$backup_root/worktrees/$safe_name.status.txt"
git -C "$worktree_path" diff --binary HEAD > "$backup_root/worktrees/$safe_name.tracked.patch"
git -C "$worktree_path" diff --binary --cached > "$backup_root/worktrees/$safe_name.staged.patch"
git -C "$worktree_path" ls-files --others --exclude-standard -z > "$backup_root/worktrees/$safe_name.untracked.zlist"
```

Não enviar esses backups para o GitHub. Logs, screenshots, bancos ou provas de QA podem conter informações de sessão, cliente ou ambiente.

### Fase 3 — corrigir bloqueios de estabilidade

1. Corrigir e integrar o Alpha Smoke conforme a seção crítica.
2. Corrigir `scripts/audit-branches.sh` para não produzir falsos positivos por uma janela fixa de apenas 300 PRs mergeados.
3. Adicionar validação/regressão proporcional às duas correções.
4. Rebasear a branch de trabalho se `origin/main` avançar.
5. Não misturar a correção de CI com limpeza destrutiva ou com alterações funcionais do produto no mesmo commit.

### Fase 4 — resolver PRs remotos

1. Atualizar a fotografia de todos os PRs abertos.
2. Tratar os sete Dependabot PRs um por vez, do menor risco/escopo para o maior, sempre contra o `main` mais recente.
3. Investigar cada check falho; não aceitar “mergeable” como sinônimo de “pronto”.
4. Mergear somente com checks e política satisfeitos.
5. Fechar PR supersedido/inseguro com comentário explícito e link para a evidência substituta.
6. Após cada merge, atualizar os PRs restantes e reexecutar o conjunto relevante de testes.

### Fase 5 — reconciliar branches, worktrees e arquivos locais

Para cada branch local-only e cada worktree dirty:

1. confirmar que o backup existe e é legível;
2. comparar commits e blobs com o `origin/main` atualizado;
3. classificar como `PROMOVER`, `JÁ INCORPORADO`, `SUPERSEDIDO`, `ARQUIVAR` ou `MANTER ATIVO`;
4. promover somente conteúdo que tenha valor atual comprovado, em branch/PR focado e com testes;
5. remover worktree apenas com `git worktree remove <caminho>` depois que estiver limpo ou preservado;
6. executar `git worktree prune` somente após remover corretamente as entradas e confirmar ausência de sessões ativas;
7. excluir branch local preferencialmente com `git branch -d`; usar `-D` somente quando a prova de preservação e a classificação estiverem registradas;
8. excluir branch remota apenas depois de confirmar PR/integração, backup e autorização adequada;
9. nunca executar `rm -rf .worktrees`, desbloquear worktree ativo ou matar sessão para forçar limpeza.

Decisões esperadas para artefatos raiz, sujeitas à revalidação:

- `.alpha-tmp/`: inspecionar sensibilidade; arquivar localmente fora do repo ou excluir; não commitar em massa;
- `.worktrees/`: gerir exclusivamente via Git;
- `docs/plans/backstage-app-audits-2026-08-29/`: deixar o update do checkout reconciliar com os arquivos já rastreados;
- quatro relatórios de 2026-08-28: arquivar fora do repo, salvo valor histórico permanente comprovado;
- scripts `prova-*.mjs`: promover a teste/ferramenta com contrato claro ou arquivar; não deixá-los órfãos;
- protótipo `buyman-nuxt-interface`: preservar patch e untracked, confirmar supersessão por `purchase-nuxt`, então remover o worktree se não houver conteúdo único útil.

Somente após fechar as decisões locais e coordenar sessões ativas, atualizar o checkout canônico para o `origin/main` final por fast-forward. Não usar reset destrutivo para encobrir divergência.

### Fase 6 — verificar remoto, CI e deploy final

Após o último merge:

1. registrar o SHA final de `origin/main`;
2. confirmar todos os checks obrigatórios do SHA;
3. confirmar o Deploy Images correspondente e as imagens que ele deveria reconstruir;
4. verificar digest das tags mutáveis contra as tags imutáveis esperadas por componente;
5. verificar deployment ativo, fase, progresso e causa;
6. rodar `scripts/check_do_spec_drift.py` contra o app vivo;
7. comprovar Alpha Smoke `workflow_run` em `success` e anexar URL/log das asserções;
8. repetir smoke manual mínimo: readiness, menu, contagem mínima, checkout negativo e SSR;
9. fazer um último `fetch --all --prune --tags` e repetir a auditoria de branches/worktrees/PRs para detectar corrida com mudanças paralelas.

### Fase 7 — entregar evidência final

O relatório final do executor deve conter:

- período exato da execução e identidade do host;
- SHA inicial e SHA final de `origin/main`;
- SHA final do `main` local e confirmação de igualdade;
- commits e PRs criados/mergeados/fechados, com links;
- checks e runs finais, com links;
- deployment ID, fase e proveniência das imagens;
- resumo do spec drift e do smoke;
- inventário de worktrees antes/depois;
- branches locais/remotas removidas ou mantidas e motivo;
- lista de arquivos locais promovidos, arquivados ou excluídos;
- localização do backup, checksums e verificação de restauração;
- tabela `CONFIRMADO`/`ALTERADO`/`REFUTADO` desta fotografia e da análise anterior do executor;
- seção “Pendências restantes”. Se não houver nenhuma, escrever explicitamente: **“Nenhuma pendência conhecida após a verificação final.”**

## Condições de parada

Interromper a ação destrutiva específica, preservar evidência e escalar ao proprietário quando ocorrer qualquer uma destas condições:

- worktree locked ainda possui processo/sessão ativa;
- conteúdo dirty ou objeto inalcançável é único e seu valor não pode ser decidido com segurança;
- `origin/main` avança durante uma decisão de merge/limpeza e invalida a comparação;
- check obrigatório falha sem causa compreendida;
- Alpha Smoke continua sem executar as asserções;
- digest/tag/deployment não corresponde à proveniência esperada;
- spec drift deixa de ser o conjunto explicitamente esperado;
- um comando destrutivo aponta para caminho amplo, não resolvido ou ambíguo;
- a correção exigiria alterar comportamento de Core/produto sem uma revisão funcional autorizada.

Uma condição de parada bloqueia a ação afetada, não autoriza encerrar silenciosamente o trabalho inteiro. Continuar nas frentes independentes seguras e registrar o bloqueio com evidência.

## Resultado esperado do agente externo

O resultado não deve ser “revisei e concordo”. O resultado esperado é:

1. uma auditoria independente reconciliada com sua análise anterior e com este documento;
2. commits/PRs focados para os defeitos de estabilidade confirmados;
3. decisões executadas sobre PRs, branches, worktrees e artefatos;
4. backups recuperáveis antes de qualquer descarte;
5. `main` local e remoto convergentes;
6. CI e deploy comprovadamente estáveis no SHA final;
7. relatório final que permita ao proprietário iniciar, em um segundo momento, uma nova revisão de prontidão para go-live sem herdar ambiguidade operacional.
