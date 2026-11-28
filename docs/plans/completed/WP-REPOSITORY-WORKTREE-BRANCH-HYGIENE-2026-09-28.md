# WP — Higiene segura de worktrees, branches, locks e temporários

- **Data:** 2026-09-28
- **Status:** pronto para execução após o WP de recuperação do checkout raiz e snapshots críticos
- **Natureza:** redução de dívida operacional Git; sem mudança de produto
- **Branch do programa:** `codex/go-live-recovery-program-20260928`
- **Pré-requisito:** todos os gates de `WP-GO-LIVE-RECOVERY-ROOT-AND-CRITICAL-WIP-2026-09-28.md` concluídos

## 1. Resultado esperado

Reduzir o inventário operacional do repositório a um conjunto pequeno, compreensível e recuperável, sem apagar trabalho legítimo:

- cada worktree tem dono, finalidade, estado e decisão;
- worktrees integradas e limpas são arquivadas por mecanismo recuperável;
- worktrees sujas nunca são arquivadas sem snapshot e classificação explícita;
- locks órfãos são tratados pelo comando suportado, nunca pela remoção de arquivos internos;
- branches integradas/supersedidas são colocadas em quarentena antes de qualquer remoção;
- branches com patch único, PR aberto ou origem desconhecida permanecem preservadas;
- temporários/caches são inventariados e só então descartados de forma restrita;
- `git worktree list`, `make inflight` e GitHub voltam a representar o trabalho real.

## 2. Baseline auditada em 2026-09-28

| Métrica | Valor |
|---|---:|
| Worktrees registradas | 55 |
| Worktrees limpas | 39 |
| Worktrees sujas | 16 |
| Worktrees detached | 6 |
| Worktrees com lock | 6 |
| Locks apontando para PID 1304, inexistente na auditoria | 6 |
| Worktrees limpas com HEAD ancestral do `main` remoto | 36 |
| Branches locais | 853 |
| Branches remotas vivas | 651 |
| Branches locais sem upstream | 223 |
| Heads locais ancestrais diretos do `main` remoto | 747 |
| Branches divergentes com todos os patches equivalentes ao `main` | 38 |
| Branches com pelo menos um patch não equivalente | 68 |
| Dessas 68, atualizadas desde 2026-09-24 | 9 |
| `.codex-worktrees/` não rastreado dentro da raiz | aproximadamente 1,9 GB |

Esses números são uma fotografia. O executor deve recapturá-los, porque sessões paralelas podem alterar o estado.

## 3. Decisões já suportadas pela evidência

### 3.1 Não arquivar

Até conclusão do WP de recuperação:

- `django-shopman-marketing-v2-offers-coupons-20260928`;
- `agent-aaaf287fc9868f404` (`claude/encomendas-tela-unica`);
- `agent-af0ab6e8342120587` (`claude/detalhe-do-pedido-compartilhado`);
- checkout raiz;
- qualquer worktree que ganhar nova modificação após o inventário.

### 3.2 Locks fortes candidatos a arquivamento

Estas quatro worktrees estavam limpas, integradas e presas a PID morto:

- `agent-a13c4a6418b1ebe1c`;
- `agent-a8c6e4d8c812a16ba`;
- `agent-aa2d7da821cc219fb`;
- `agent-acfffc43aa36a3d72`.

Ainda assim, arquivamento só ocorre após os gates deste WP.

### 3.3 Sujeira que aparenta ser artefato

Oito worktrees sujas continham apenas diretórios como:

- `output/`;
- `.local-tests/`;
- `.orders-lab/`;
- `.artifacts/`.

“Parece artefato” não significa “pode apagar”. Primeiro produzir manifest, tamanho, dono e decisão.

### 3.4 Trabalho antigo já supersedido ou preservado

- `agent-a43d025be47c5b570`: duas pequenas alterações de 10/09 (`bg-none` e documentação do chevron) já aparecem semanticamente no `main` atual;
- `receitas-paes-producao-26a519`: `RECIPE-MODELING-BRIEF.md` local é mais antigo que a versão atualizada já presente no `main`;
- `django-shopman-print-layouts-20260912`: o relatório untracked é idêntico ao salvo em `origin/rescue/print-layouts-20260912-uncommitted`;
- `django-shopman-legal-cancellation-20260912`: alteração isolada em `.nuxtrc`, de `4.1.0` para `4.3.2`, ainda requer decisão; não presumir descarte.

### 3.5 Branches/PRs que exigem decisão, não limpeza automática

| Item | Estado | Direção |
|---|---|---|
| PR #1148 | aberto, clean, mergeable | revisão/merge prioritário se a voz já foi aprovada |
| PR #722 | aberto, clean, mergeable | revisão técnica e merge ou fechamento justificado |
| PR #1116 | aberto/conflitante; único patch equivalente ao `main` | fechar como supersedido após registrar evidência |
| PR #1119 | aberto/conflitante; quatro patches de UI ainda únicos | rebase/salvamento ou decisão explícita de abandono |
| PR #1120 | draft/conflitante; nove commits de impressão | decisão visual; atualizar ou arquivar como projeto pausado |
| Dependabot | dez PRs abertos; nove bloqueados/falhando | triagem por família, sem merge em lote |
| Benchmark iFood | um commit docs-only fora do `main` | atualizar addenda e integrar |
| WPs de mapa/endereço | dois commits docs-only fora do `main` | rebase e integrar |
| Storefront focus ruler | dois commits de código fora do `main` | rebase, testes e PR próprio |

## 4. Invariantes e proibições

1. **Nunca usar `git clean`, `git reset --hard`, `rm -rf`, `git checkout --`, `git restore .`, `git branch -D` ou `git stash`.**
2. **Nunca usar `git add .`, `git add -A`, `git add -u` ou adicionar diretório inteiro.**
3. **Nunca remover worktree pelo shell.** Para worktree gerenciada pelo Codex, usar o arquivamento do aplicativo; para worktree Git comum, seguir o fluxo aprovado e recuperável.
4. **Nunca executar `git worktree prune` sem `--dry-run` anterior, relatório revisado e prova de que nenhum caminho contém trabalho.**
5. **Nunca apagar arquivo `.git/worktrees/*/locked` manualmente.** Usar `git worktree unlock <caminho>` somente após comprovar PID morto, quiescência e preservação.
6. **Nunca concluir que branch divergente é trabalho pendente apenas por SHA.** Squash/rebase altera identidade; usar ancestralidade, `git cherry`, PRs e comparação funcional.
7. **Nunca concluir que branch pode ser apagada apenas porque o PR foi fechado.** PR fechado pode conter trabalho abandonado ainda desejado.
8. **Nunca excluir branch remota neste WP sem aprovação explícita para a matriz de remoção.** A primeira passagem é arquivamento e quarentena.
9. **Nunca limpar temporários por nome genérico.** Resolver caminho absoluto, dono, tamanho, manifest e vínculo com worktree.
10. **Nunca arquivar worktree usada por sessão/processo vivo, mesmo que limpa.**
11. **Nunca arquivar worktree suja antes de snapshot remoto verificado.**
12. **Nunca executar comandos destrutivos a partir de `$HOME`, `~`, `/` ou raiz do workspace.**

## 5. Modelo de classificação

Cada worktree deve receber uma e apenas uma classe:

| Classe | Definição | Ação |
|---|---|---|
| A — ativa | sessão/processo vivo ou modificação recente com dono | manter; registrar dono e prazo |
| B — preservação pendente | dirty com código/docs úteis sem snapshot | bloquear arquivamento; executar WP de recuperação |
| C — limpa e integrada | status limpo, HEAD ancestral do `main`, sem processo | arquivar de modo recuperável |
| D — limpa, patch equivalente | status limpo, não ancestral por squash/rebase, mas `git cherry` só mostra `-` | arquivar após anexar prova |
| E — artefato local | dirty apenas por outputs/caches, sem conteúdo autoral | preservar evidência necessária; descartar nominalmente em fase posterior |
| F — divergente útil | possui patch `+`, PR aberto, decisão ou documentação ainda válida | manter/rebasear/abrir PR |
| G — desconhecida | origem ou conteúdo não compreendido | manter; exige investigação |
| H — path ausente | registro Git aponta para diretório inexistente | revisar dry-run; prune somente após prova |

Branches recebem classificação análoga:

- `integrada-ancestral`;
- `integrada-equivalente`;
- `PR-aberto`;
- `PR-mergeado`;
- `PR-fechado-com-trabalho-único`;
- `local-sem-upstream-com-trabalho-único`;
- `backup/rescue`;
- `desconhecida`.

## 6. Fase 0 — Preflight reproduzível

Executar a partir do checkout canônico limpo criado pelo WP anterior:

```bash
git status --short --branch
git fetch --prune origin
git worktree list --porcelain
git worktree prune --dry-run --verbose
git for-each-ref refs/heads --format='%(refname:short)%09%(objectname)%09%(upstream:short)%09%(upstream:track)%09%(committerdate:iso8601)'
git ls-remote --heads origin
gh pr list --state open --limit 200
make inflight
```

`fetch --prune` atualiza referências; não remove branches locais nem worktrees. Sua saída deve ser anexada ao relatório.

Para cada worktree:

```bash
git -C <caminho> status --porcelain=v2 --branch
git -C <caminho> rev-parse HEAD
git -C <caminho> symbolic-ref --short -q HEAD
git -C <caminho> diff --name-status
git -C <caminho> diff --cached --name-status
```

Para cada lock:

```bash
git worktree list --porcelain
ps -p <pid> -o pid=,ppid=,lstart=,stat=,command=
```

Também verificar processos por caminho com ferramenta adequada ao host. Ausência no `ps` não basta se arquivos foram modificados recentemente.

### Gate H0 — inventário congelado

- [ ] HEAD canônico coincide com `origin/main`;
- [ ] todas as worktrees têm classe, dono e última atividade;
- [ ] todas as branches associadas têm PR/status conhecido;
- [ ] todos os locks têm PID, idade e quiescência avaliados;
- [ ] nenhuma worktree crítica permanece sem snapshot;
- [ ] `worktree prune --dry-run` foi registrado, mas nada foi podado.

## 7. Fase 1 — Arquivar worktrees limpas e integradas

### 7.1 Gate individual de arquivamento

Uma worktree só passa se todos forem verdadeiros:

```bash
test -z "$(git -C <caminho> status --porcelain)"
git merge-base --is-ancestor "$(git -C <caminho> rev-parse HEAD)" origin/main
```

Além disso:

- nenhum processo/sessão usa o caminho;
- nenhum lock vivo existe;
- nenhum terminal tem comando em execução naquele diretório;
- branch/PR está integrada ou formalmente supersedida;
- não há submódulo ou repositório Git embutido;
- a ferramenta de arquivamento consegue produzir snapshot recuperável.

### 7.2 Mecanismo

- worktree gerenciada pelo Codex: identificar com `list_artifacts` e usar `archive_worktree`;
- worktree de outra ferramenta: usar seu mecanismo nativo de encerramento quando disponível;
- worktree Git comum: registrar branch/HEAD/path e usar somente o procedimento aprovado pelo coordenador;
- nunca substituir arquivamento por exclusão direta do diretório.

Depois de cada lote pequeno, no máximo cinco worktrees:

```bash
git worktree list --porcelain
git worktree prune --dry-run --verbose
git fsck --no-dangling
```

### Gate H1 — lote recuperável

- [ ] cada item arquivado possui identidade, HEAD e branch registrados;
- [ ] mecanismo declarou snapshot recuperável;
- [ ] `main` e worktrees ativas permanecem intactos;
- [ ] contagem antes/depois foi registrada;
- [ ] nenhum branch foi removido;
- [ ] nenhuma worktree dirty entrou no lote.

## 8. Fase 2 — Locks órfãos

Ordem por lock:

1. recapturar status e mtime dos arquivos alterados;
2. confirmar que o PID não existe;
3. confirmar com coordenação que a sessão dona terminou;
4. se dirty, preservar antes de qualquer unlock;
5. se limpa e integrada, arquivar diretamente pelo mecanismo suportado quando ele souber lidar com o lock;
6. apenas se necessário, executar:

```bash
git worktree unlock <caminho-exato>
```

7. recapturar `git worktree list --porcelain`.

Não editar `.git/worktrees/<id>/locked`.

### Gate H2 — locks coerentes

- [ ] nenhum lock referencia PID inexistente sem justificativa documentada;
- [ ] locks de worktrees dirty só foram removidos após snapshot;
- [ ] nenhuma worktree ativa perdeu seu lock;
- [ ] a lista de worktrees continua consistente.

## 9. Fase 3 — Worktrees sujas por artefatos e temporários

Para cada diretório:

```bash
du -sh <caminho-exato>
find <caminho-exato> -maxdepth 2 -type f -print
```

Classificar conteúdo como:

- evidência necessária;
- baseline/retrato que precisa ser versionado;
- log reproduzível;
- dependência/cache reinstalável;
- arquivo desconhecido.

Se houver qualquer arquivo desconhecido, parar. Se só houver cache reproduzível, registrar a receita de regeneração e a decisão de descarte. O descarte deve mirar caminhos nominais e validados, nunca glob amplo.

O diretório `.codex-worktrees/` de aproximadamente 1,9 GB dentro da raiz merece tratamento próprio:

1. enumerar quais subdiretórios são worktrees registradas;
2. arquivar cada worktree individualmente;
3. verificar que não há arquivo não rastreado dentro delas;
4. somente depois considerar remover o contêiner vazio;
5. preferir mover futuras worktrees para fora da raiz compartilhada.

### Gate H3 — temporários decididos

- [ ] cada arquivo/diretório tem classe e dono;
- [ ] evidências foram preservadas com hash;
- [ ] caches têm receita de regeneração;
- [ ] nenhum path desconhecido foi apagado;
- [ ] `git status` melhorou sem perda de conteúdo autoral.

## 10. Fase 4 — Quarentena de branches

### 10.1 Não confiar apenas em `--merged`

Para cada branch candidata:

```bash
git merge-base --is-ancestor <branch> origin/main
git cherry origin/main <branch>
gh pr list --state all --head <branch>
git log --oneline --decorate origin/main..<branch>
```

Interpretação:

- ancestral: integrada por histórico;
- somente linhas `-` em `git cherry`: patches equivalentes integrados;
- qualquer `+`: existe patch não equivalente; manter até revisão;
- PR aberto: manter;
- PR fechado com `+`: decisão de produto/escopo necessária;
- branch `backup/` ou `rescue/`: manter até confirmar que a recuperação correspondente terminou.

### 10.2 Quarentena

Na primeira passagem:

- produzir CSV/Markdown com branch, HEAD, data, upstream, PR, ancestralidade e contagem `+/-`;
- marcar candidatas, sem remover;
- aguardar janela mínima de sete dias e revisão do coordenador;
- reconsultar GitHub e worktrees antes de qualquer remoção.

Branches remotas exigem aprovação explícita da matriz final. Branch local também não deve ser removida se for o último nome de um commit único.

### Gate H4 — matriz decidível

- [ ] 100% das 853 branches locais possuem classificação ou exceção registrada;
- [ ] as 68 com patch `+` foram revisadas individualmente ou mantidas;
- [ ] branches com PR aberto foram preservadas;
- [ ] branches `backup/`/`rescue/` foram preservadas salvo conclusão comprovada;
- [ ] nenhuma branch foi removida na fase de quarentena;
- [ ] a matriz final de remoção tem aprovação explícita antes da execução.

## 11. Fase 5 — PRs e trabalho dormente

Ordem proposta:

1. revisar #1148 e #722, hoje limpos/mergeáveis;
2. fechar #1116 como supersedido somente após anexar prova de equivalência;
3. decidir #1119: salvar os quatro patches únicos em branch atualizada ou encerrar conscientemente;
4. decidir #1120: obter aprovação visual e rebasear, ou mantê-lo draft com condição de retomada e dono;
5. atualizar/integrar benchmark iFood e WPs de mapa/endereço;
6. validar e publicar `storefront-focus-ruler` em PR próprio;
7. agrupar Dependabot por ecossistema e causa de falha; nunca empilhar updates vermelhos sem diagnóstico.

Todo trabalho parcial publicado fica em PR draft com pergunta/impedimento explícito. Nenhuma branch útil deve voltar a existir apenas localmente.

## 12. Rollback

| Operação | Rollback |
|---|---|
| Arquivamento Codex | usar `restore_worktree` com a identidade retornada por `list_artifacts` |
| Unlock incorreto | relockar pelo mecanismo suportado somente se a sessão dona ainda existir; registrar incidente |
| Classificação errada de branch | retirar da matriz antes da remoção; branches não são apagadas durante quarentena |
| Artefato descartado após aprovação | recuperar do pacote de evidência com SHA ou regenerar pela receita documentada |
| `worktree prune` propõe item inesperado | não executar; restaurar/inspecionar o path e atualizar inventário |
| PR fechado por engano | reabrir se permitido e registrar decisão; branch permanece preservada |

Se uma branch/worktree já tiver sido removida na fase final autorizada, recuperação depende do SHA registrado, reflog e snapshot de arquivamento. Por isso nenhuma remoção pode ocorrer sem os três.

## 13. Critérios de aceite

- [ ] Checkout canônico de `main` existe, está limpo e coincide com o remoto.
- [ ] Checkout raiz não possui operação Git interrompida.
- [ ] Todos os working trees críticos foram preservados e possuem dono.
- [ ] 100% das worktrees registradas foram classificadas.
- [ ] Nenhuma worktree limpa/integrada e sem uso permanece aberta sem justificativa.
- [ ] Nenhuma worktree dirty foi arquivada sem snapshot remoto verificado.
- [ ] Nenhum lock aponta silenciosamente para PID morto.
- [ ] Temporários/caches remanescentes têm dono, justificativa e prazo.
- [ ] `.codex-worktrees/` dentro da raiz não abriga trabalho invisível.
- [ ] 100% das branches locais estão classificadas ou em quarentena explícita.
- [ ] Branches com patches únicos continuam recuperáveis.
- [ ] PRs #1116, #1119, #1120, #1148 e #722 têm decisão/estado atualizado.
- [ ] Dependabot possui fila priorizada por causa, não apenas uma coleção de PRs vermelhos.
- [ ] `make inflight` não aponta trabalho local sem branch/PR/dono.
- [ ] Relatório final contém inventário antes/depois, comandos, SHAs, identidades de arquivo e exceções.
- [ ] Nenhum deploy, alteração de banco ou mudança de produto ocorreu como efeito da higiene.

## 14. Evidências obrigatórias

1. `git worktree list --porcelain` antes e depois de cada lote;
2. saída de `git worktree prune --dry-run --verbose` antes e depois;
3. matriz completa de worktrees com classe, dono, HEAD, status, lock e decisão;
4. matriz completa de branches com upstream, PR, ancestralidade e `git cherry`;
5. identidades de arquivamento recuperável;
6. SHAs e PRs dos snapshots;
7. manifests/hashes de evidências e artefatos preservados;
8. tabela de locks com PID, idade, comprovação e ação;
9. inventário de temporários com tamanho e receita de regeneração;
10. lista de branches efetivamente removidas, caso uma fase posterior seja autorizada;
11. contagens antes/depois e explicação para cada item remanescente;
12. saída final de `make inflight`, `git status` do checkout canônico e `gh pr list`.

## 15. Fora de escopo

- implementar funcionalidades dormentes;
- decidir produto em nome do dono;
- apagar branch remota sem aprovação explícita;
- limpar banco, volumes Docker, credenciais ou ambientes;
- modificar CI para “passar” branches antigas;
- reescrever história de branches compartilhadas;
- arquivar a raiz compartilhada;
- declarar Go-live pronto sem os gates funcionais e operacionais do projeto.
