# Evidência R7 — higiene segura do repositório

- **Janela:** 2026-09-29 00:55–01:25 UTC
- **Executor:** R7, após o gate R0
- **Checkout canônico:** `/Users/pablovalentini/Dev/Claude/.canonical-worktrees/django-shopman-main`
- **HEAD canônico recapturado:** `cf48a229d5a82790e0fa1a643d78aa8c4aa5ebfd`, idêntico a `origin/main`
- **Pacote externo de evidência:** `/Users/pablovalentini/Dev/Claude/.codex-evidence/go-live-r7-20260928.eZav3z`
- **Escopo executado:** inventário, quarentena não destrutiva, manifests de artefatos e um lote recuperável de quatro worktrees nominalmente autorizado pelo WP

Nenhuma branch foi removida. Nenhum temporário foi apagado. Nenhum lock interno foi editado. Nenhuma worktree suja foi arquivada. Os drafts #1220–#1223 e suas fontes foram preservados.

## Baseline recapturado

| Métrica | Antes do lote | Depois do lote |
|---|---:|---:|
| Worktrees registradas | 60 | 56 |
| Worktrees detached | 7 | 7 |
| Locks registrados | 0 | 0 |
| Branches locais | 861 | 861 |
| Heads remotos | 664 | 664 |
| Candidatas propostas por `worktree prune --dry-run --verbose` | 0 | 0 |

O checkout canônico estava limpo, porém um fetch mostrou que `origin/main` havia avançado de `e3880d89d` para `cf48a229d`. Foi aplicado apenas fast-forward no checkout canônico antes da auditoria. `git fsck --no-dangling` terminou sem achados depois do lote.

## Lote recuperável 1

As quatro worktrees abaixo eram as candidatas fortes explicitamente nomeadas no WP. Para cada uma, o gate confirmou status limpo, HEAD ancestral de `origin/main`, PR mergeado, ausência de processo com cwd no path, ausência de submódulo/repositório embutido e branch local preservada.

| Worktree arquivada | Branch preservada | HEAD preservado | PR integrado |
|---|---|---|---:|
| `agent-a13c4a6418b1ebe1c` | `claude/encomenda-nota-na-saida` | `577ad651283ea3f487e1c39722f8a11c445d4387` | #1173 |
| `agent-a8c6e4d8c812a16ba` | `claude/encomendas-reagendar` | `6f3ffc9f20634af91f667d949a777106d796f36e` | #1168 |
| `agent-aa2d7da821cc219fb` | `claude/encomendas-pdv-receber-cancelar` | `a99805cdb699e4963c233c1636b37abf8c60d09e` | #1174 |
| `agent-acfffc43aa36a3d72` | `claude/encomendas-pdv-leitura-e-telas` | `0dded27c6428cabf970e537d2e4ed513b64e6c40` | #1167 |

O arquivamento usou `git worktree remove <path-exato>`, nunca remoção manual de diretório. A recuperação continua possível recriando uma worktree a partir da branch/HEAD registrado. Depois do lote: 56 worktrees, zero locks, dry-run de prune vazio e as quatro refs locais ainda resolvendo para os SHAs acima.

## Matriz de worktrees

A matriz integral está em `worktree-matrix.csv` no pacote de evidência, SHA-256 `07559fc69457c42dfed6dd0b7482ff9c99a702ff6e1a841342585f472b16898a`.

| Classe | Quantidade | Decisão |
|---|---:|---|
| A — ativa | 8 | manter; processo/sessão ou frente coordenada |
| B — preservação pendente | 4 | manter; conteúdo autoral ou decisão ainda pendente |
| C — limpa e integrada | 30 | candidatas futuras; sem autorização nominal neste lote |
| E — artefato local | 8 | manifestadas; descarte não autorizado |
| F — divergente útil | 6 | preservar; patch único, PR ou dependência |

As quatro worktrees B são `legal-cancellation` (`.nuxtrc` ainda sem decisão), `print-layouts` (relatório/output e fonte do resgate), `select-chevron-and-controls-audit` e `receitas-paes-producao`. O checkout raiz foi classificado A porque há processos vivos e documentos/configuração preservados; ele não é candidato a arquivamento.

Os drafts críticos permanecem abertos e imutáveis nesta fase:

- #1220 em `084b1fa6e687dd952362532bca1033647553514b`;
- #1221 em `f0d7e699d02da2d564c8634be476e2ca054d861d`;
- #1222 em `5c37b5812ec490ba99915db3fa14bd8d059f5e6e`;
- #1223 em `87a1df2ce85e9197e6ef0dfe56ac64c9bb2ad50d`.

## Quarentena de branches

A matriz integral das 861 branches locais está em `branch-quarantine-matrix.csv`, SHA-256 `44c22d327162f356571b6ad745da9f4127ec451bbe0777e7ca5cb055bde2ba0f`.

| Classificação | Quantidade |
|---|---:|
| integrada-ancestral | 745 |
| integrada-equivalente | 38 |
| PR-aberto | 10 |
| PR-mergeado, mas ainda divergente do HEAD atual | 3 |
| PR-fechado-com-trabalho-único | 18 |
| local-sem-upstream-com-trabalho-único | 27 |
| divergente-com-trabalho-único | 18 |
| backup/rescue | 1 |
| desconhecida | 1 |

Das 783 branches integradas por ancestralidade ou equivalência, 745 não estavam checked out e entraram apenas em quarentena documental. A janela começou em `2026-09-29T01:25:23Z`; a primeira revisão possível é `2026-10-06T01:25:23Z`, sempre condicionada ao gate humano H4 e a uma nova consulta de PRs/worktrees. As branches checked out e todas as 78 classes com trabalho único, PR ou origem especial foram preservadas. Nenhuma ref local ou remota foi apagada.

## Locks e temporários

A recaptura encontrou zero linhas `locked` em `git worktree list --porcelain` e zero arquivos `locked` no common Git dir. Portanto, nenhum `unlock` foi executado.

Foram produzidos 13 manifests de artefatos, com 366 entradas e 40.046.497 bytes efetivamente hasheados. Eles cobrem `output/`, `.local-tests/`, `.orders-lab/`, `.artifacts/`, o link `surfaces/node_modules`, `.alpha-tmp/`, `tmp/` e os outputs da raiz/print. Os manifests e seus hashes estão listados em `artifact-manifest-sha256.txt`.

O contêiner `.codex-worktrees/` de aproximadamente 1,9 GB dentro da raiz possui sete subdiretórios imediatos, todos correspondentes a worktrees ainda registradas. A prova está em `root-codex-worktrees-container.tsv`. O contêiner e seus filhos foram preservados; remover o diretório violaria o gate enquanto essas worktrees existirem.

## Bloqueios restantes

1. As 30 worktrees classe C não têm autorização nominal equivalente às quatro deste lote; algumas ainda dependem de merge/smoke ou confirmação de sessão. Permanecem registradas.
2. Os oito conjuntos classe E têm manifest e hash, mas a receita exata de regeneração e a aprovação do dono ainda não foram comprovadas. Nada foi descartado.
3. As branches em quarentena exigem sete dias e aprovação humana H4. A matriz não autoriza pruning.
4. As fontes #1220–#1223 permanecem protegidas até merges e smokes consumidores. Em especial, nenhuma limpeza atingiu Marketing ou as duas doadoras de Encomendas.
5. `make inflight` continua mostrando frentes reais em execução; isso é consistente com as classes A/F e impede declarar o R7 globalmente concluído nesta onda.

## Arquivos do pacote externo

O pacote contém, entre outros:

- `worktrees-after-batch1.porcelain` e `worktrees-final.porcelain`;
- `worktree-prune-dry-run-after-batch1.txt`;
- `worktree-matrix.csv` e `worktree-class-summary.json`;
- `branch-quarantine-matrix.csv` e `branch-class-summary.json`;
- `all-prs.json`, `open-prs.json`, `local-branches.tsv` e `remote-heads.tsv`;
- `process-cwds.tsv` e `make-inflight.txt`;
- `artifact-summary.csv`, manifests individuais e `artifact-manifest-sha256.txt`.

Este relatório registra uma fase intermediária segura. Não representa autorização para remoção de branches, descarte de artefatos ou arquivamento das fontes ainda consumidas por outros WPs.

## Continuação final segura — 2026-09-29 04:39 UTC

Após os merges consumidores e os gates pós-merge verdes informados pela coordenação, a fase final recapturou `origin/main` em `ab148fbd85d50865bf107e95298b712decd9d7f4`. O checkout canônico foi atualizado apenas por fast-forward de `44b4cba81d5e036c25669411a2743e5e31753674` para esse SHA e terminou limpo, idêntico ao remoto.

### Prova de absorção

| Fonte preservada | Consumidor integrado | Prova | Decisão da worktree |
|---|---|---|---|
| #1221 `claude/encomendas-tela-unica` em `f0d7e699d02da2d564c8634be476e2ca054d861d` | #1231, merge `a05f82af9bb577d0b331aa224018d87b8ed70312` | corpo do PR consumidor identifica nominalmente #1221 e registra a composição semântica das duas capacidades | arquivada; branch local e remota preservadas |
| #1222 `claude/detalhe-do-pedido-compartilhado` em `5c37b5812ec490ba99915db3fa14bd8d059f5e6e` | #1231, merge `a05f82af9bb577d0b331aa224018d87b8ed70312` | corpo do PR consumidor identifica nominalmente #1222 e registra o contrato final compartilhado | arquivada; branch local e remota preservadas |
| `codex/storefront-focus-ruler-20260928` em `c28c98bd3fd41d23146f7cc322c61c207519bc0d` | #1224, merge `ae52ef768e053959ff9abd82f9b968d2ee8e3900` | `git cherry origin/main <branch>` retornou somente `-` para `d055d522d` e `c28c98bd3` | arquivada; branch local preservada |
| `codex/ifood-single-tenant-benchmark-20260928` em `e385ef1cfe159c1f08850fa0b7e0dd91f6470ec0` | #1226, merge `1f497db90f150b0a497cd7001d11df19fc7491b0` | `git cherry origin/main <branch>` retornou somente `-` para `e385ef1cf` | arquivada; branch local preservada |
| `codex/wp-checkout-map-confirmation-20260928` em `ddd26e3ae98fcbbe62c35bea8cfae479c3f08fc1` | #1226, merge `1f497db90f150b0a497cd7001d11df19fc7491b0` | `git cherry origin/main <branch>` retornou somente `-` para `34f962ae5` e `ddd26e3ae` | arquivada; branch local preservada |
| #1220 `codex/marketing-v2-offers-coupons-20260928` em `084b1fa6e687dd952362532bca1033647553514b` | #1233, merge `85bde2190d1e9ae45f10ca4f5b4bf9a70de70df1` | corpo do PR consumidor identifica nominalmente #1220 e explica o porte semântico e a renumeração da migration para `0084` | **preservada**: ainda contém o artefato não rastreado descrito abaixo |

Os três doadores R4 são equivalentes por patch ao `main`. Os snapshots de Encomendas e Marketing continuam aparecendo com `+` em `git cherry` porque foram integrados semanticamente, não por reaplicação textual; por isso a prova adicional é a matriz explícita dos PRs #1231 e #1233 e seus gates. Nenhum draft foi fechado e nenhuma branch foi removida.

### Lote recuperável 2

Antes da operação, as cinco worktrees removidas estavam limpas, sem submódulo, repositório Git embutido, arquivo não rastreado ou processo com `cwd` no caminho. O arquivamento usou somente `git worktree remove <caminho-exato>`, sem `--force`, e preservou todos os refs locais. A receita de recuperação é `git worktree add <novo-caminho> <branch>`, usando o branch/HEAD registrado na tabela acima.

O inventário tinha 59 worktrees imediatamente antes do lote. Cinco fontes foram arquivadas e uma nova worktree ativa de preflight R8 foi registrada concorrentemente; por isso a recaptura final mostra 55, redução líquida de quatro. A nova worktree não sobrepôs os caminhos removidos. Depois do lote:

- `git worktree prune --dry-run --verbose`: vazio;
- `git fsck --no-dangling`: sem achados;
- 55 worktrees registradas, oito detached e zero locks;
- os cinco branches locais ainda resolvem exatamente para os SHAs registrados;
- nenhuma branch local ou remota foi removida.

### Exceções preservadas

- A worktree fonte de #1220 continua registrada porque `surfaces/node_modules` é um symlink não rastreado para `/Users/pablovalentini/Dev/Claude/django-shopman/surfaces/marketing-nuxt/node_modules`. O artefato já tem manifest em `artifact-marketing-node-modules-link.csv`, mas `artifact-summary.csv` ainda declara receita exata e aprovação do dono não comprovadas. Remover a worktree com `--force` violaria H3; nenhuma alteração foi feita no symlink.
- #1223 e `codex/root-local-docs-recovery-20260928` em `87a1df2ce85e9197e6ef0dfe56ac64c9bb2ad50d` permanecem integralmente preservados, conforme a ordem de coordenação.
- A quarentena H4 iniciada em `2026-09-29T01:25:23Z` continua vigente até pelo menos `2026-10-06T01:25:23Z` e ainda exige aprovação humana. Nenhuma matriz de remoção foi executada.
- Os demais artefatos sem receita/dono comprovados continuam intactos; não houve limpeza ampla, prune efetivo nem descarte de temporários.

Assim, a fase final autorizada concluiu o arquivamento recuperável das cinco fontes sem artefatos pendentes. O R7 global permanece deliberadamente aberto para o artefato de #1220 e para o gate temporal/humano H4; isso não autoriza contornar nenhum dos dois.
