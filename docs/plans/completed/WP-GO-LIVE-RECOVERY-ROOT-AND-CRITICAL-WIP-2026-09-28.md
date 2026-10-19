# WP — Recuperação do checkout raiz e preservação dos working trees críticos

- **Data:** 2026-09-28
- **Status:** pronto para execução controlada; nenhuma ação de recuperação foi executada por este WP
- **Natureza:** operação Git e preservação de trabalho; sem mudança de produto
- **Branch do programa:** `codex/go-live-recovery-program-20260928`
- **Dependência:** executar antes do WP de higiene ampla do repositório

## 1. Resultado esperado

Recuperar um ponto de trabalho confiável para o Go-live sem perder nenhuma mudança local:

1. preservar, de forma verificável, os três working trees críticos que hoje existem apenas em disco;
2. provar e registrar o conteúdo do cherry-pick interrompido no checkout raiz;
3. sanear o checkout raiz sem usá-lo como área de integração;
4. criar um checkout canônico, limpo e atualizado de `main`, fora da árvore do checkout raiz;
5. deixar cada frente preservada em branch própria e PR draft, pronta para integração serial;
6. impedir que duas frentes continuem alterando os mesmos arquivos de Encomendas.

Este WP não integra funcionalidades, não resolve os conflitos de produto entre as frentes e não faz deploy.

## 2. Evidência de partida

O inventário de 2026-09-28 encontrou:

| Área | Evidência observada | Risco |
|---|---|---|
| Checkout raiz | `/Users/pablovalentini/Dev/Claude/django-shopman`, branch `codex/shopman-backstage-marketing-hardening`, HEAD `b589e22c5c69` de 2026-08-28 | Base extremamente antiga e imprópria para integração |
| Operação interrompida | cherry-pick de `ff658a43a` aberto desde 2026-09-15 | Estado Git bloqueado e fácil de sobrescrever por engano |
| Conflitos | `shopman/storefront/api/views.py` (`UU`) e `shopman/storefront/tests/api/test_operational_intentions.py` (`DU`) | Qualquer add amplo pode gravar uma resolução acidental |
| Patch interrompido | `git cherry <main-live> golive-rebase/checkout-fix` marcou `- ff658a43a` | O patch já possui equivalente no `main`; terminar o cherry-pick seria retrabalho |
| Sujeira adicional na raiz | `.codex/config.toml` modificado; documentos, `output/`, `tmp/`, `.alpha-tmp/` e `.codex-worktrees/` não rastreados | Mistura de configuração, evidência e diretórios operacionais |
| Checkout canônico | nenhum worktree está em `main`; branch local `main` estava 55 commits atrás do remoto | Não há chão limpo e explícito para coordenação |

Os três working trees críticos são:

| Frente | Caminho | Branch | Estado em 28/09 | Observação |
|---|---|---|---:|---|
| Marketing — ofertas/cupons | `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-marketing-v2-offers-coupons-20260928` | `codex/marketing-v2-offers-coupons-20260928` | 20 entradas dirty; 16 arquivos rastreados com cerca de 792 inserções/104 remoções; migration e componentes novos | Todo o trabalho útil está sem commit |
| Encomendas — tela única | `/Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/agent-aaaf287fc9868f404` | `claude/encomendas-tela-unica` | 26 entradas dirty; cerca de 1.698 inserções/1.148 remoções, além de 476 remoções staged | Lock aponta para PID morto; arquivos alterados até aproximadamente 19:50 |
| Encomendas — detalhe compartilhado | `/Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/agent-af0ab6e8342120587` | `claude/detalhe-do-pedido-compartilhado` | 22 entradas dirty; cerca de 655 inserções/1.074 remoções | Lock aponta para PID morto; arquivos alterados até aproximadamente 19:49 |

As duas frentes de Encomendas sobrepõem estes sete arquivos:

- `shopman/backstage/api/operations.py`
- `shopman/backstage/projections/preorders.py`
- `shopman/backstage/tests/test_pos_preorders.py`
- `surfaces/pos-nuxt/app/composables/usePosPreorders.ts`
- `surfaces/pos-nuxt/app/pages/preorders/[ref].vue`
- `surfaces/pos-nuxt/app/types/preorders.ts`
- `surfaces/pos-nuxt/tests/pages/preorders.test.ts`

## 3. Invariantes e proibições

Estas regras são gates, não recomendações:

1. **Não tocar no checkout raiz antes de concluir e verificar os snapshots.**
2. **Nunca executar `git add .`, `git add -A`, `git add -u` ou `git add <diretório>`.** Só adicionar arquivos explicitamente enumerados.
3. **Nunca executar `git reset --hard`, `git clean`, `git checkout --`, `git restore`, `git stash`, `rm -rf` ou apagar manualmente arquivos de lock.**
4. **Nunca arquivar/remover uma worktree suja antes de existir snapshot verificado e recuperável fora dela.**
5. **Nunca misturar arquivos de duas worktrees no mesmo commit de preservação.**
6. **Nunca resolver os sete arquivos sobrepostos em paralelo.** Depois do snapshot, haverá um único integrador e uma ordem serial.
7. **Nunca incluir `surfaces/node_modules`, `output/`, `tmp/`, `.alpha-tmp/`, `.local-tests/`, `.orders-lab/` ou `.artifacts/` em commit.**
8. **Nunca interpretar lock com PID morto como autorização para limpeza.** Primeiro comprovar quiescência e preservar o conteúdo.
9. **Nunca usar a raiz compartilhada para `switch`, `merge`, `rebase`, `cherry-pick` ou integração.**
10. **Nenhuma branch de snapshot será mergeada diretamente.** Snapshot preserva; uma branch posterior integra e testa.
11. **Nenhuma ação destrutiva é autorizada por este documento.** Abort, unlock, archive e remoção só ocorrem nos gates explicitamente descritos e sob operador designado.

## 4. Papéis

| Papel | Responsabilidade |
|---|---|
| Coordenador | declara freeze, resolve propriedade das frentes e autoriza transições entre gates |
| Operador de preservação | coleta evidências e cria um snapshot por worktree, sem editar o conteúdo |
| Integrador de Encomendas | compõe serialmente as duas frentes após os snapshots |
| Revisor | confirma manifests, hashes, branches remotas e PRs draft antes de qualquer saneamento |

Uma mesma pessoa pode acumular papéis, mas a revisão dos snapshots deve ser feita por uma segunda leitura independente.

## 5. Ordem obrigatória

```text
freeze de escrita
  → inventário/preflight imutável
    → snapshot Marketing
      → snapshot Encomendas/tela única
        → snapshot Encomendas/detalhe
          → verificar recuperação dos 3 snapshots
            → preservar evidências da raiz
              → provar redundância do cherry-pick
                → sanear a raiz
                  → criar checkout canônico limpo de main
                    → liberar integração serial
```

Se qualquer gate falhar, parar no ponto atual. Não “compensar” com limpeza.

## 6. Fase 0 — Freeze e preflight

### 6.1 Declarar freeze

- identificar sessões/processos que usam cada um dos três caminhos;
- interromper novas edições, sem matar processo à força;
- pedir ao dono de cada frente confirmação de que chegou a uma fronteira de escrita;
- registrar data/hora, operador, worktree, branch e último arquivo modificado;
- não prosseguir enquanto uma ferramenta ainda estiver escrevendo.

### 6.2 Captura mínima por worktree

Executar em cada caminho, redirecionando a saída para arquivos de evidência com nome único fora do repositório, por exemplo `/tmp/shopman-recovery-20260928/<slug>/`:

```bash
git rev-parse --show-toplevel
git status --porcelain=v2 --branch
git rev-parse HEAD
git symbolic-ref --short -q HEAD
git diff --name-status
git diff --cached --name-status
git diff --stat
git diff --cached --stat
git ls-files --others --exclude-standard
git diff --check
```

Também capturar:

```bash
git diff --binary > /tmp/shopman-recovery-20260928/<slug>/unstaged.patch
git diff --cached --binary > /tmp/shopman-recovery-20260928/<slug>/staged.patch
shasum -a 256 /tmp/shopman-recovery-20260928/<slug>/*.patch
```

Para arquivos não rastreados úteis, criar manifest explícito e arquivá-los nominalmente. Não usar glob amplo nem incluir dependências/saídas geradas.

### Gate G0 — quiescência e evidência

- [ ] nenhum processo está escrevendo nos três caminhos;
- [ ] status, HEAD, branch e manifests foram capturados;
- [ ] patches binary foram gerados e possuem SHA-256;
- [ ] lista de untracked úteis foi revisada linha a linha;
- [ ] diretórios proibidos estão fora de todos os manifests.

## 7. Fase 1 — Snapshots dos três working trees críticos

### 7.1 Regra comum

O snapshot preferencial é um commit WIP na própria branch, seguido de push e PR draft. Isso preserva autoria, index, renames e arquivos binários melhor que um patch isolado.

Antes de adicionar qualquer arquivo:

```bash
git status --short
git diff --check
git diff --cached --check
```

Adicionar somente paths explicitamente aprovados:

```bash
git add -- caminho/exato/arquivo-a caminho/exato/arquivo-b
git diff --cached --name-status
git diff --cached --stat
```

Se a lista staged não coincidir exatamente com o manifest aprovado, executar `git restore --staged -- <arquivo-específico>` somente sobre o arquivo adicionado por engano nessa própria etapa, registrar o evento e revisar novamente. Não usar restauração ampla.

Commit de preservação sugerido:

```text
wip(<domínio>): preservar frente antes da recuperação do go-live
```

Em seguida:

```bash
git push -u origin <branch-exata>
gh pr create --draft --base main --head <branch-exata> --title "WIP: ..." --body-file <arquivo-exclusivo-da-frente>
```

O corpo do PR deve conter:

- finalidade de snapshot, não de merge;
- manifest de arquivos;
- testes executados e não executados;
- conflitos conhecidos;
- base/HEAD no momento da captura;
- link para este WP;
- próximo passo e integrador responsável.

### 7.2 Snapshot Marketing

Incluir código, testes, documentação, migration `0083_producao_concluida_no_marketing.py`, `MarketingOfferForm.vue` e `useMarketingOffers.ts`, após revisar o manifest.

Excluir expressamente `surfaces/node_modules`.

Antes do commit, verificar colisão de migration contra o `main` remoto:

```bash
git fetch origin main
find shopman/shop/migrations -maxdepth 1 -type f -name '0083_*' -print
git ls-tree -r --name-only origin/main -- shopman/shop/migrations | grep '/0083_'
```

Colisão não impede o snapshot, mas deve bloquear a integração e constar no PR draft.

### 7.3 Snapshot Encomendas — tela única

- preservar estado staged e unstaged no mesmo commit WIP, mantendo o manifest explícito;
- confirmar que as quatro remoções staged são intencionais e documentá-las;
- não remover o lock antes do snapshot;
- não atualizar a base durante a captura.

### 7.4 Snapshot Encomendas — detalhe compartilhado

- preservar todos os arquivos úteis e os quatro arquivos novos do `operator-kit`/apresentação;
- registrar a grande remoção em `surfaces/pos-nuxt/tests/pages/preorders.test.ts` como decisão ainda não validada;
- não atualizar a base durante a captura.

### Gate G1 — snapshots recuperáveis

Para cada frente:

- [ ] commit WIP existe na branch correta;
- [ ] commit contém exatamente o manifest aprovado;
- [ ] branch foi empurrada e possui upstream próprio;
- [ ] PR draft existe e está marcado “snapshot; não mergear”;
- [ ] `git show --stat <sha>` foi anexado à evidência;
- [ ] patches externos e hashes continuam disponíveis;
- [ ] um segundo checkout temporário consegue buscar o commit remoto e listar os arquivos;
- [ ] nenhum diretório proibido entrou no commit.

## 8. Fase 2 — Preservação e saneamento do checkout raiz

### 8.1 Evidência adicional da raiz

Além do preflight comum, capturar:

```bash
git status
git rev-parse CHERRY_PICK_HEAD
stat .git/CHERRY_PICK_HEAD .git/index .git/MERGE_MSG
git diff --cc
git diff --cached --binary
git diff -- .codex/config.toml
git ls-files --others --exclude-standard
```

Salvar cópia explícita de:

- patch de `.codex/config.toml`;
- cada documento não rastreado que tenha dono/valor confirmado;
- manifest e tamanho de `.alpha-tmp/`, `.codex-worktrees/`, `output/` e `tmp/`, sem copiá-los indiscriminadamente.

### 8.2 Prova de redundância

O operador deve atualizar a referência remota sem mudar o working tree e comparar contra o `main` remoto atual:

```bash
git fetch origin main
git cherry origin/main golive-rebase/checkout-fix
git show --stat ff658a43a
```

Gate obrigatório: `ff658a43a` deve aparecer com `-`, ou a equivalência deve ser demonstrada por outro método reproduzível. Se aparecer com `+`, parar: o cherry-pick pode conter trabalho ainda ausente.

### 8.3 Classificar os untracked da raiz

Cada item recebe exatamente uma classe:

- `preservar-em-branch`: documento/código útil que deve ir para branch/PR própria;
- `evidência-local`: saída necessária para auditoria, preservada fora do repo com hash;
- `infraestrutura-worktree`: checkout registrado; será tratado pelo WP de higiene;
- `gerado-descartável`: candidato futuro a descarte, sem descarte nesta fase;
- `desconhecido`: bloqueia o saneamento até existir dono.

### 8.4 Abortar somente após G1 e prova de redundância

Com snapshots verificados, manifest da raiz classificado e segunda revisão:

```bash
git cherry-pick --abort
```

Esse é o único comando de mutação autorizado nesta fase, e apenas ao operador designado. Depois:

```bash
git status --short --branch
git rev-parse -q --verify CHERRY_PICK_HEAD
```

Resultado esperado: nenhum `CHERRY_PICK_HEAD` e nenhum path `UU`/`DU`. Arquivos não rastreados continuam presentes; eles não são limpos neste WP.

### Gate G2 — raiz destravada sem perda

- [ ] `CHERRY_PICK_HEAD` deixou de existir;
- [ ] nenhum conflito permanece;
- [ ] patches/hashes anteriores continuam legíveis;
- [ ] `.codex/config.toml` e documentos úteis têm cópia/snapshot verificado;
- [ ] nenhum arquivo não rastreado foi apagado;
- [ ] `git reflog` e HEAD antes/depois foram registrados;
- [ ] nenhuma integração nova foi feita na raiz.

## 9. Fase 3 — Checkout canônico limpo de `main`

O checkout canônico deve ficar **fora** de `/Users/pablovalentini/Dev/Claude/django-shopman`, para não aparecer como untracked da raiz. Caminho recomendado:

```text
/Users/pablovalentini/Dev/Claude/.canonical-worktrees/django-shopman-main
```

Preflight:

```bash
git worktree list --porcelain
git show-ref --verify refs/heads/main
git ls-remote origin refs/heads/main
```

Como nenhuma worktree deve estar usando `main`:

```bash
git worktree add /Users/pablovalentini/Dev/Claude/.canonical-worktrees/django-shopman-main main
cd /Users/pablovalentini/Dev/Claude/.canonical-worktrees/django-shopman-main
git fetch origin main
git merge --ff-only origin/main
```

Não usar `pull` sem `--ff-only`, merge commit, rebase ou reset.

Verificação:

```bash
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
git fsck --no-dangling
```

### Gate G3 — chão canônico

- [ ] caminho canônico existe fora do checkout raiz;
- [ ] branch é exatamente `main`;
- [ ] working tree e index estão limpos;
- [ ] HEAD é idêntico a `origin/main`;
- [ ] `main` não está simultaneamente checkout em outro caminho;
- [ ] o caminho foi documentado para todas as sessões;
- [ ] nenhuma sessão de implementação usará o checkout canônico para escrever código; novas frentes continuam ganhando worktree própria.

## 10. Fase 4 — Ordem posterior de integração

Somente após G3:

1. atualizar e validar a frente de Marketing, que não colide com as sete rotas críticas de Encomendas;
2. escolher uma das frentes de Encomendas como base canônica;
3. rebasear/transportar essa frente para branch nova baseada no `main` canônico;
4. rodar testes e abrir PR real;
5. só depois do merge, reaplicar seletivamente a segunda frente;
6. resolver os sete arquivos sobrepostos por intenção, nunca escolhendo “ours/theirs” em bloco;
7. manter os PRs de snapshot abertos até o merge das branches reais e a verificação de equivalência.

Este WP não decide qual frente de Encomendas vem primeiro. Essa escolha exige revisão funcional dos dois diffs.

## 11. Rollback e recuperação

| Falha | Recuperação segura |
|---|---|
| Commit WIP incorreto, ainda não enviado | não resetar; criar commit corretivo explícito ou branch nova a partir do estado anterior |
| Branch WIP enviada com arquivo indevido | remover em commit corretivo nomeado; não reescrever história sem coordenação |
| PR draft criado com base errada | corrigir base/metadados; snapshot continua válido pelo SHA |
| `cherry-pick --abort` remove alteração local relevante | reaplicar somente o arquivo necessário a partir do patch externo com SHA verificado |
| Checkout canônico não faz fast-forward | parar; comparar refs; não forçar nem resetar |
| Processo volta a escrever após freeze | parar a fase, recapturar manifest/patch/hash e reiniciar o gate daquela worktree |
| Conflito durante integração posterior | abandonar a tentativa na branch de integração, não nos snapshots; snapshots permanecem imutáveis |

## 12. Critérios de aceite

- [ ] Os três working trees críticos estão preservados em commits remotos distintos.
- [ ] Cada snapshot possui PR draft, manifest, evidência e aviso de não merge.
- [ ] Nenhum snapshot contém dependências, caches, outputs ou temporários.
- [ ] Os sete arquivos sobrepostos têm um único integrador e ordem serial registrada.
- [ ] O cherry-pick raiz foi provado redundante antes de qualquer abort.
- [ ] O checkout raiz não possui operação Git em andamento nem conflitos.
- [ ] Nenhum arquivo não rastreado foi removido durante o saneamento.
- [ ] Configuração e documentos locais úteis possuem cópia recuperável e hash.
- [ ] Existe checkout canônico limpo em `main`, fora da raiz compartilhada.
- [ ] O checkout canônico coincide byte a byte no SHA com `origin/main`.
- [ ] O relatório final inclui comandos, saídas relevantes, SHAs, PRs e exceções.
- [ ] Nenhum merge, deploy, limpeza ampla ou remoção de branch ocorreu como efeito deste WP.

## 13. Evidências obrigatórias do relatório final

1. tabela `worktree → branch → HEAD antes → snapshot SHA → PR`;
2. manifests staged de cada snapshot;
3. SHA-256 dos patches externos;
4. saída de `git cherry origin/main golive-rebase/checkout-fix`;
5. status da raiz antes e depois;
6. reflog da raiz no intervalo da recuperação;
7. saída que prova ausência de `CHERRY_PICK_HEAD`;
8. caminho, status e SHA do checkout canônico;
9. inventário dos sete arquivos sobrepostos e integrador designado;
10. lista nominal de itens da raiz ainda pendentes de classificação.

## 14. Fora de escopo

- resolver funcionalmente Marketing, Encomendas ou Storefront;
- atualizar os WPs do benchmark iFood;
- fechar ou mergear PRs existentes;
- excluir branches locais/remotas;
- apagar outputs, caches, locks ou worktrees;
- alterar deploy, banco, credenciais ou produção;
- declarar Go-live pronto apenas porque o Git foi saneado.
