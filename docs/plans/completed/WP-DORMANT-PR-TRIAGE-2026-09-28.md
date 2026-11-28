# WP-DORMANT-PR-TRIAGE — triagem e encerramento de PRs dormentes

- **Data:** 2026-09-28
- **Estado:** pronto para execução autônoma, com um gate humano explícito para design de impressão
- **Prioridade:** P0 de coordenação; libera arquivos disputados por outros WPs

## 1. Objetivo

Dar destino inequívoco aos PRs `#1148`, `#1116`, `#1119`, `#1120` e `#722`: fechar o que foi superado, retomar o que ainda entrega valor, separar conteúdo independente de decisão visual e impedir que branches antigas continuem disputando arquivos centrais.

## 2. Snapshot comprovado

| PR | Estado em 2026-09-28 | Divergência local observada | Veredito inicial |
|---|---|---:|---|
| `#1148` | aberto, mergeable/clean, checks verdes | `main` 233 à frente; branch 6 commits; diff líquido contra `main` restrito a `docs/reference/whatsapp-templates-meta.md` | fechar como superado após reconciliar a documentação útil |
| `#1116` | aberto, conflicting/dirty; dois checks antigos falhos | `main` 328 à frente; o único patch aparece como equivalente (`-`) em `git cherry main branch` | fechar como superado, anexando a prova de equivalência |
| `#1119` | aberto, conflicting/dirty; dois checks antigos falhos | `main` 328 à frente; o commit herdado de `#1116` é equivalente e há 4 commits adicionais únicos | retomar somente os quatro commits de UI sobre o `main` atual |
| `#1120` | draft, conflicting/dirty, sem checks | `main` 1691 à frente; branch 10 commits; 36 arquivos | extrair DANFE funcional; manter design de impressão bloqueado por aprovação visual ou fechar o draft após o resgate |
| `#722` | aberto, mergeable/clean, checks verdes | `main` 89 à frente; branch 1 commit | atualizar e integrar primeiro se continuar sendo diff mínimo |

O `main` ainda usa `@nuxt/kit` `3.21.8` em `surfaces/operator-kit`; o `#722` propõe `3.21.11`.

## 3. Dependências e ordem

1. Congelar os cinco heads e registrar SHA/checks antes de qualquer mudança.
2. Tratar `#722` e `#1148` primeiro, pois são decisões rápidas.
3. Fechar `#1116` como superado após a prova e então retomar os quatro commits únicos de `#1119` diretamente sobre o `main`.
4. Triar e fatiar `#1120` antes do WP de Encomendas, porque ambos tocam `operations.py`, ticket e POS.
5. Só liberar os leases compartilhados quando os PRs estiverem mergeados ou formalmente fechados.

## 4. Ownership exclusivo

Um coordenador de PRs é o único autorizado a atualizar base, rebasear, fazer force-push com lease, alterar draft/base e fechar os cinco PRs.

Leases por frente:

- `#722`: manifests de `surfaces/operator-kit`;
- `#1148`: `docs/reference/whatsapp-templates-meta.md`;
- `#1116`: Guestman merge, API/projeções/serviços/testes de Clientes, `api/urls.py`, exportador de schema e contrato gerado;
- `#1119`: arquivos anteriores mais UI de Clientes e `api/operations.py`;
- `#1120`: impressão, branding, DANFE, fontes/assets, fiscal recovery, `api/operations.py`, ticket, POS index e documentação de impressão.

Enquanto este WP estiver ativo, Encomendas e Marketing não integram `api/operations.py`, `api/urls.py`, exportador/contrato, ticket ou POS index.

## 5. Escopo

- Atualizar cada PR com evidência atual.
- Fechar PR superado com comentário que aponta onde o código efetivo entrou.
- Recuperar mudança documental ainda útil em branch limpa.
- Retomar a stack de Clientes sem misturar backend e UI.
- Separar DANFE baseada em XML autorizado do redesign visual de impressão.
- Atualizar checks, descrição, dependências e status de draft.
- Fazer merge/deploy somente quando os gates do PR específico passarem.

## 6. Não escopo

- Redesenhar Clientes, impressão, WhatsApp ou operator-kit além do necessário para compatibilidade com o `main`.
- Aprovar visualmente tickets/recibos em nome do dono.
- Misturar os cinco PRs em uma mega-branch.
- Usar checks antigos como autorização de merge.
- Fazer force-push sem `--force-with-lease`.

## 7. Execução por PR

### 7.1 PR #722 — dependência operator-kit

1. Atualizar a branch com o `main` e regenerar o lockfile com a ferramenta e versão canônicas do repositório.
2. Confirmar que o diff final contém apenas `@nuxt/kit 3.21.8 → 3.21.11` e as alterações inevitáveis do lockfile.
3. Rodar testes do `operator-kit` e gates de dependências/supply chain.
4. Se o diff continuar mínimo e CI novo ficar verde, merge queue.
5. Se o `main` passar a conter versão igual ou superior antes do merge, fechar como superado.

Não exige deploy isolado; segue na próxima imagem.

### 7.2 PR #1148 — cascata WhatsApp

1. Comparar os seis commits com o `main` e listar os PRs/commits que já absorveram o código.
2. Revisar o único diff líquido restante, `docs/reference/whatsapp-templates-meta.md`, contra o estado real de templates aprovados.
3. Se houver informação válida ausente, portar somente essa documentação para um PR novo e pequeno.
4. Fechar `#1148` como superado, com links para entregas sucessoras e para o eventual PR documental.
5. Não mergear a branch antiga apenas porque está “clean”: título e corpo prometem código que já não corresponde ao diff.

Sem deploy.

### 7.3 PR #1116 — Clientes no Gestor, backend

1. Repetir a comparação contra o `main` atual e anexar `git cherry` e a correspondência dos arquivos/contratos absorvidos.
2. Confirmar que autorização `shop.manage_customers`, preview transacional, merge, undo, auditoria e contrato já existem no baseline atual.
3. Se a equivalência continuar completa, fechar `#1116` como superado, apontando os commits/PRs sucessores.
4. Se surgir diferença funcional real, parar e registrá-la como delta novo; não reaplicar cegamente o commit antigo.
5. Liberar os leases de backend assim que a supersessão estiver documentada.

### 7.4 PR #1119 — Clientes no Gestor, UI

1. Depois do fechamento documentado de `#1116`, criar branch limpa no `main` atual e reaplicar semanticamente apenas os quatro commits adicionais de UI.
2. Preservar busca/filtros na URL, ficha 360, comparação lado a lado, sugestão de sobrevivente, preview obrigatório e histórico/undo.
3. Resolver `api/operations.py` e contrato contra o `main` pós-`#1116`.
4. Testar permissão na navegação e no servidor; esconder aba não substitui autorização.
5. Fazer smoke completo de listar, buscar, abrir, pré-visualizar, unificar e desfazer.
6. Só mergear depois de `#1116` e CI atual verde.

### 7.5 PR #1120 — impressão e DANFE

1. Inventariar os 10 commits e classificar cada arquivo como:
   - DANFE funcional baseada em XML autorizado;
   - infraestrutura neutra de impressão;
   - decisão visual pendente;
   - obsoleto diante das vias atuais do pedido.
2. Criar um PR limpo e independente para DANFE/XML e seus testes, se a funcionalidade ainda não existir no `main`.
3. Não levar fontes, branding, layout ESC/POS ou mudança visual para esse PR funcional salvo dependência comprovada.
4. Atualizar o draft visual sobre o `main` apenas se ainda houver intenção de revisão. Anexar previews comparáveis e checklist de impressoras/papéis.
5. Pausar no gate humano de aprovação visual. O executor não pode aprovar esse gate.
6. Depois de extrair todo conteúdo útil, fechar `#1120` e, se necessário, abrir um novo draft visual pequeno e honesto. Se o dono rejeitar o redesign, fechar como superado sem merge.

## 8. Gates e testes

### Gates comuns

- branch baseada no `main` atual;
- `git diff --check` limpo;
- zero conflito ou arquivo gerado manualmente;
- CI completo no novo HEAD;
- descrição do PR corresponde ao diff real;
- nenhuma aprovação/check anterior ao rebase usado como prova.

### #722

- testes do `operator-kit`;
- validação do lockfile;
- build/gate que consome o kit.

### #1148

- gate de documentação e verificação manual do catálogo Meta atual;
- se não houver código líquido, nenhum deploy/teste de runtime é necessário.

### #1116

- suíte Guestman de merge;
- testes de API de Clientes;
- testes de permissões;
- preview sem efeito persistente;
- merge e undo, inclusive doador inativo, conflito e auditoria;
- suíte backstage completa;
- exportação determinística do contrato.

### #1119

- testes de Orders Nuxt, lint, typecheck e build;
- testes de CustomerMergeDialog, busca/lista, ficha, histórico e navegação;
- E2E de permissão negada, sucesso e erro concorrente;
- smoke integrado com backend já mergeado.

### #1120

- para DANFE: fixtures de XML autorizado, casos inválidos, autorização, render e regressão fiscal;
- para impressão: testes de layout/branding/ESC-POS, preview em larguras suportadas e impressão física aprovada;
- suíte do POS e backstage onde houver integração;
- nenhum merge visual antes do aceite humano documentado.

## 9. PR, merge e deploy

- Usar merge queue e preservar rastreabilidade entre PR antigo e sucessor.
- `#722` segue na próxima release, sem deploy próprio.
- `#1148` é encerramento documental, sem deploy.
- `#1116` é encerrado por supersessão; `#1119` é entregue sobre o backend já canônico do `main` e liberado em staging para smoke de Clientes.
- O PR funcional de DANFE pode ir a staging independentemente do redesign visual.
- Mudanças visuais de impressão exigem aprovação humana, teste físico e rollout operacional controlado.

## 10. Rollback

- Dependência: revert do commit/lockfile e rebuild.
- Clientes: reverter UI primeiro e backend depois; não desfazer merges de clientes já executados em produção sem usar a operação de undo/auditoria do domínio.
- DANFE: reverter endpoint/render novo e restaurar caminho anterior; XML e dados fiscais persistidos não são apagados.
- Impressão: manter layout anterior selecionável durante o rollout ou promover imagem anterior.
- Fechamento de PR é reversível por reabertura, mas conteúdo resgatado deve apontar para o sucessor.

## 11. Definition of Done

- Cada um dos cinco PRs tem destino explícito, comentário final e referência ao sucessor quando houver.
- `#722` foi mergeado com CI atual ou fechado por supersessão.
- `#1148` foi fechado sem levar uma branch semanticamente obsoleta ao `main`.
- `#1116` foi fechado com prova de supersessão; os quatro commits únicos de `#1119` foram retomados, testados e mergeados, ou receberam bloqueio factual documentado.
- DANFE funcional do `#1120` foi resgatada ou descartada com prova de equivalência; design visual não foi aprovado automaticamente.
- Leases de `operations.py`, `urls.py`, exportador/contrato, ticket e POS index foram liberados.
- Nenhum PR dormente permanece aberto sem owner, próximo passo e gate.
