# Triagem remota e recuperação GeoLite2 em 29/10/2026

Base congelada da análise: `7288b44624d195d5cbf37431184fe49ee71a43e0`. [Inventário com heads, arquivos e classificação](../EVIDENCE/20261029-remote-dormant.json). A consulta incluiu 3.000 PRs de todos os estados, branches remotos fora da ancestralidade de main, árvores de merge e comentários de fechamento.

## Trabalho útil recuperado

`chore/geolite2-snapshot` tem dois commits posteriores à antiga PR #1356 já mergeada. O Dockerfile do main continuava em `2026-09-29`; o bot havia publicado `2026-10-20` e depois `2026-10-27`, sem nova PR. A atualização de uma linha para `2026-10-27` foi recuperada na #2046. Ela invalida o cache do build que baixa a base de cidade; não muda credenciais nem executa reseed ou gravação de dados vivos. O download existente continua verificando SHA-256.

O [run de 28/10](https://github.com/nelsonboulangerie/django-shopman/actions/runs/40685998358) terminou após o push com: `GitHub Actions is not permitted to create or approve pull requests (createPullRequest)`. O branch existia, mas a criação de PR estava bloqueada pela decisão D38. Nenhuma permissão foi alterada nem a decisão reaberta.

**Fluxo humano vigente:** a coordenação consulta `chore/geolite2-snapshot` após o workflow, compara o ARG com main e publica uma PR humana quando houver atualização. Ter uma PR antiga mergeada no mesmo branch não conta como entrega dos commits novos. Se o run estiver vermelho, conferir o log e o branch mesmo que `gh pr list --state open` esteja vazio. Esta coordenação realizou essa recuperação na #2046.

## Relatório DSH

`origin/dsh/avaliacao-repositorio-20261022` já é ancestral de main e o arquivo `docs/reports/2026-10-22-avaliacao-repositorio-shopman.md` está rastreado em main (blob `ccb45cb917d651ebe722bf6122b1f3ffe0d0ae10`). Não há relatório perdido a reaplicar. Suas alegações têm ressalvas factuais, tratadas pela revisão adversarial e correção de cobertura #2039. O relatório histórico não autoriza formatação em massa, redesenho ou refatoração indiscriminada.

## PRs fechados sem merge

Foram encontrados 45 branches não ancestrais com PR fechado nesta amostra. Fechado não significa abandonado: os comentários registram substituição, rejeição ou adiamento. A tabela distingue decisões explícitas e aponta a evidência original; **não** declara equivalência semântica integral de todos os diffs só por haver sucessor.

| Branch | Evidência de fechamento | Destino documentado |
|---|---|---|
| `claude/clientes-no-gestor-api` | [#1116](https://github.com/nelsonboulangerie/django-shopman/pull/1116#issuecomment-5881395928) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/clientes-no-gestor-tela` | [#1119](https://github.com/nelsonboulangerie/django-shopman/pull/1119#issuecomment-5881447100) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/detalhe-do-pedido-compartilhado` | [#1222](https://github.com/nelsonboulangerie/django-shopman/pull/1222#issuecomment-5942882652) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/drain-privacy-r10-r12` | [#742](https://github.com/nelsonboulangerie/django-shopman/pull/742#issuecomment-5729529926) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/encomendas-tela-unica` | [#1221](https://github.com/nelsonboulangerie/django-shopman/pull/1221#issuecomment-5942882132) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/fase2-bi-favoritos-fixados` | [#1657](https://github.com/nelsonboulangerie/django-shopman/pull/1657#issuecomment-6176468202) | Adiado explicitamente para pós-go-live (B.I.). |
| `claude/fase2-laudo-proposta` | [#1565](https://github.com/nelsonboulangerie/django-shopman/pull/1565#issuecomment-6176469155) | Proposta superada por V4/V5/V6. |
| `claude/fr3b-pdv-faixa-sem-conexao-tema` | [#1938](https://github.com/nelsonboulangerie/django-shopman/pull/1938#issuecomment-6286467688) | Rejeitado pelo dono: manter alto contraste. |
| `claude/guarda-do-registry-diz-o-que-leu` | [#869](https://github.com/nelsonboulangerie/django-shopman/pull/869#issuecomment-5740261132) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/intelligent-chaum-8d76b5` | [#368](https://github.com/nelsonboulangerie/django-shopman/pull/368#issuecomment-5450622575) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/kds-pickup-atualiza-sozinho` | [#1684](https://github.com/nelsonboulangerie/django-shopman/pull/1684#issuecomment-6146811998) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/kit-desfazer-no-mesmo-botao` | [#1601](https://github.com/nelsonboulangerie/django-shopman/pull/1601#issuecomment-6090957179) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/kitchensink-proposta-minimalismo` | [#1539](https://github.com/nelsonboulangerie/django-shopman/pull/1539#issuecomment-6176469819) | Material superado pela canonização do kit. |
| `claude/layout-order-fixes-e348b0` | [#2022](https://github.com/nelsonboulangerie/django-shopman/pull/2022#issuecomment-6503332963) | Recuperado na #2041 nesta coordenação. |
| `claude/loja-aviso-e-observacao-por-item` | [#1354](https://github.com/nelsonboulangerie/django-shopman/pull/1354#issuecomment-5943645232) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/mkt-retratos-do-visto` | [#864](https://github.com/nelsonboulangerie/django-shopman/pull/864#issuecomment-5736703517) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/mkt-visual-baselines-fila` | [#1424](https://github.com/nelsonboulangerie/django-shopman/pull/1424#issuecomment-6115019342) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/nervous-wilbur-14717c` | [#563](https://github.com/nelsonboulangerie/django-shopman/pull/563#issuecomment-5587070866) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/proposta-desfazer-no-botao` | [#1575](https://github.com/nelsonboulangerie/django-shopman/pull/1575#issuecomment-6083858131) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/teste-nao-pede-deploy` | [#870](https://github.com/nelsonboulangerie/django-shopman/pull/870#issuecomment-5740261288) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `claude/tres-perfis-fiscais` | [#1108](https://github.com/nelsonboulangerie/django-shopman/pull/1108#issuecomment-5824601513) | Rejeitado: parametrização do contador prevalece. |
| `codex/address-map-live-activation-20260929` | [#1272](https://github.com/nelsonboulangerie/django-shopman/pull/1272#issuecomment-5897704784) | Desnecessário: configuração aplicada pelo Admin; migração reativaria após rollback. |
| `codex/admin-ingress-staging-probe-20260914` | [#671](https://github.com/nelsonboulangerie/django-shopman/pull/671#issuecomment-5805878684) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `codex/core-sovereignty-wp7` | [#1854](https://github.com/nelsonboulangerie/django-shopman/pull/1854#issuecomment-6232522202) | Não conclui WP7; sequência vinculante e FOLLOW-UP B prevalecem. |
| `codex/go-live-admin-login-rate-limit-20260913` | [#828](https://github.com/nelsonboulangerie/django-shopman/pull/828#issuecomment-5729211614) | Rejeitado tecnicamente: confiança em XFF sem contrato. |
| `codex/go-live-certificate-validity-20260913` | [#657](https://github.com/nelsonboulangerie/django-shopman/pull/657#issuecomment-5682191277) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `codex/go-live-critical-alerts-20260913` | [#653](https://github.com/nelsonboulangerie/django-shopman/pull/653#issuecomment-5682188461) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `codex/go-live-fiscal-retries-20260913` | [#651](https://github.com/nelsonboulangerie/django-shopman/pull/651#issuecomment-5682186567) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `codex/go-live-notification-errors-20260913` | [#652](https://github.com/nelsonboulangerie/django-shopman/pull/652#issuecomment-5682187465) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `codex/go-live-phone-input-20260913` | [#650](https://github.com/nelsonboulangerie/django-shopman/pull/650#issuecomment-5685517239) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `codex/go-live-production-gates-20260913` | [#656](https://github.com/nelsonboulangerie/django-shopman/pull/656#issuecomment-5682190053) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `codex/go-live-worker-health-20260913` | [#654](https://github.com/nelsonboulangerie/django-shopman/pull/654#issuecomment-5682189305) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `codex/google-maps-credential-split-20260911` | [#613](https://github.com/nelsonboulangerie/django-shopman/pull/613#issuecomment-5682185806) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `codex/marketing-v2-offers-coupons-20260928` | [#1220](https://github.com/nelsonboulangerie/django-shopman/pull/1220#issuecomment-5942881656) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `codex/marketing-visual-readiness-20260914` | [#665](https://github.com/nelsonboulangerie/django-shopman/pull/665#issuecomment-5662783020) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `codex/marketing-whatsapp-deploy-gate` | [#602](https://github.com/nelsonboulangerie/django-shopman/pull/602#issuecomment-5629251943) | Rejeitado: reduziria gate humano G-H03. |
| `codex/orders-canonical-shell` | [#1516](https://github.com/nelsonboulangerie/django-shopman/pull/1516#issuecomment-6042163726) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `codex/print-layouts-20260912` | [#1120](https://github.com/nelsonboulangerie/django-shopman/pull/1120#issuecomment-5881558884) | DANFE útil recuperado #1227; redesign permanece BLOCKED_HUMAN. |
| `codex/root-local-docs-recovery-20260928` | [#1223](https://github.com/nelsonboulangerie/django-shopman/pull/1223#issuecomment-5942884601) | Proposta de login contraria decisão WhatsApp primário; não reaplicar. |
| `codex/shopman-legal-google-oauth-20260911` | [#614](https://github.com/nelsonboulangerie/django-shopman/pull/614#issuecomment-5811138735) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `docs/repo-hygiene-proposal` | [#201](https://github.com/nelsonboulangerie/django-shopman/pull/201#issuecomment-5443114700) | Proposta encerrada após #366 e decisões posteriores. |
| `feat/pos-event-log` | [#198](https://github.com/nelsonboulangerie/django-shopman/pull/198#issuecomment-5333977233) | Desenho substituído por cashman/ADR-022. |
| `whatsapp-cascata-voz-final` | [#1148](https://github.com/nelsonboulangerie/django-shopman/pull/1148#issuecomment-5881595643) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `whatsapp-confirmacao-voz-do-dono` | [#1137](https://github.com/nelsonboulangerie/django-shopman/pull/1137#issuecomment-5830851364) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |
| `whatsapp-corpo-com-ref-curta` | [#1136](https://github.com/nelsonboulangerie/django-shopman/pull/1136#issuecomment-5830847022) | Fechamento documenta sucessor, absorção ou duplicação; consultar comentário vinculado. |

## Quinze rescues e quatro snapshots não ancestrais

Todos foram preservados no remoto, com os heads e arquivos no inventário. `merge-tree` apontou conflito em 14 dos 15 rescues; o único sem conflito, `orders-audit-base-5a3383c9-uncommitted`, contém apenas um runner local de sete linhas. Merge limpo não torna esse runner necessário ao produto.

- Probes de Admin/IP: ligados às propostas rejeitadas #655/#828 e à sonda obsoleta #671. Não reativar confiança antiga em XFF.
- Google Maps e stacks operacionais: os fechamentos #613/#651–#657 registram absorção no bundle #686. Comparação integral das stacks rescue ainda não concluída; não cherry-pickar a stack antiga.
- Privacidade/Marketing: os sucessores #830 e demais integrações atuais prevalecem. As stacks antigas conflitam e não devem substituir as proteções recentes.
- Impressão: #1120 registra a recuperação funcional DANFE/XML na #1227 e mantém redesign visual aguardando decisão. Os dois rescues de impressão permanecem evidência.
- Teste `go-live-638-baseline-uncommitted`: o arquivo `test_pos_gateway_handoff_boundary.py` já existe no main; a versão antiga usa contratos anteriores. Não foi promovido como teste novo sem análise individual das diferenças.
- PDV e `OperatorKbd`: o componente existe no kit atual. As stacks contêm também propostas de desenho de setembro; não foram reaplicadas.

Os quatro snapshots de 11/10 são `operador-nuxtui-onda0-conjunto-minimo`, `operator-kitchen-sink`, `orders-canonical-recovery` e `select-chevron-and-controls-audit`. Os quatro conflitam com main. O último corrige um `select` nativo e comentário do CSS antigo; main já adotou controles canônicos. O de kitchen sink contém um script local `.look.cjs` apontando para porta fixa e alterações antigas de tema. O da onda zero inclui adaptadores posteriormente aposentados. O do Gestor tem 110 arquivos no diff desde a base e não pode ser tratado como ajuste de três commits isolados. Nenhum foi aplicado à frente nova de UX.

**Limite e próximo responsável:** a coordenação de go-live mantém a triagem semântica residual de rescues/snapshots; as decisões de produto já rejeitadas não são reabertas. Esta entrega conclui o inventário e recupera GeoLite2, mas não afirma que cada linha dos 19 backups antigos foi auditada ou que não haja qualquer ideia útil neles. Eles estão publicados, nomeados e preservados, sem trabalho novo oculto em worktree.

## Verificação

Mudança funcional limitada ao ARG de cache no Dockerfile. Foram conferidos o diff de uma linha, a data ISO e a origem dos commits do bot. Sem download real ou teste repetido de localização: o mecanismo de leitura/download não foi alterado. Governança documental e `git diff --check` executados antes do push. Nenhum branch ou dado foi apagado.
