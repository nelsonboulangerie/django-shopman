# UX-G3: Expedição única no Gestor

- **id:** UX-G3
- **branch:** claude/ux-g3-expedicao-unica
- **PR:** #1431
- **estado:** pronto (pergunta de produto aberta, abaixo)
- **início (UTC):** 2026-10-03

## Objetivo
SUITE-UX-FUNCTION-PLAN §9 (linha "Saída do pedido"), §15 e §16: uma Saída só, no Gestor.
Paridade da Saída da Cozinha levada à coluna Saída do Gestor, aposentar a Saída da Cozinha
com redirecionamento para o Gestor na visão Saída, e permissão mínima para quem hoje expede
com `backstage.operate_kds`. O POSTO se chama "Expedição" (UX-POSTO1); a COLUNA segue "Saída".

## Paridade: o que a Saída da Cozinha fazia e o Gestor não fazia
| Saída da Cozinha | Agora no Gestor | Como (sem regra nova) |
|---|---|---|
| Coluna "Em preparo" com um chip por estação | cartão do Preparo: "Faltam Cafés e Lanches" + chip por estação (papel, cancelados) | `projections.kds.exit_station_chips` (extraída de `_build_exit_preparing_card`), lida em lote por `kitchen_station_chips` → `OrderCardProjection.kitchen` |
| "Pronto" da estação sem tela | botão "Pronto de Lanches" no chip | mesmo endpoint `kds/expedition/<pk>/printed-stations/<ref>/done/`, agora também com `shop.manage_orders` |
| Recall de ticket concluído (era só nas estações) | "Voltar para Cafés" no menu ⋯ do cartão | mesmo `kds/tickets/<pk>/recall/` e `kds.recall_block_reason`; aceita também `shop.manage_orders`; some com saída na janela de desfazer |
| Entregar/Despachar + desfazer de 5 s | já existia (#1423) | `advance_order(undo_window=True)` |
| Cartões grandes de toque | posto de saída (só a Saída aberta): todo alvo do cartão em 48 px (`min-h-action`) | `useBoardLayout.exitPost` |
| Troco/maquininha recusados ("abra no Gestor") | quem gerencia resolve como antes; quem só expede vê "chame quem gerencia" | `operator_orders.dispatch_custody_question` (uma pergunta, usada pelos dois lados) |
| Operada com `operate_kds` | quem só expede entra no Gestor, opera a Saída, e só ela | abaixo |

## Permissão (a opção mais restrita)
- Nenhuma permissão nova, nenhum grupo mudado: quem expede é quem tem `backstage.operate_kds`,
  exatamente o conjunto que operava a Saída da Cozinha.
- Superfície com alternativa: o Gestor pede `shop.manage_orders|backstage.operate_kds`
  (`permissions.surface_perm_codes`); a trava continua a do Gestor (`shop.manage_orders`).
  Antessala, lista de quem destrava, PIN, crachá e travar aceitam a forma `a|b`.
- `HasOrderBoardAccess` no quadro, no layout, no avançar e nos dois desfazer.
- Régua de quem só expede, sob o lock: `operator_orders.expedite_refusal` (só o pedido pronto
  saindo: Despachar/Entregar/Retirado; sem troco, maquininha ou juntar saída). A pergunta no
  view é a negativa (`not has_perm("shop.manage_orders")`), para nenhuma outra porta pular a régua.
- Quem só expede não abre o detalhe (403), não aceita, não recusa, não cancela, não mexe em
  iFood; a barra do Gestor fica só com "Pedidos"; o cartão não tem link nem "Atender".

## Aposentar a Saída da Cozinha
- `kds-nuxt/app/pages/[ref].vue`: estação `expedition` → `navigateTo(<Gestor>/?columns=expedition,
  external)`, e a tela diz "A Saída agora fica no Gestor" com o link enquanto troca de página.
  Os endereços antigos (`/expedicao`, `/estacao/expedicao`) já caem em `/saida` pelo routeRules.
- Índice das estações leva a Saída direto ao Gestor. Estações de preparo e `/pickup` ficam.
- Gestor: `?columns=expedition` abre só com a Saída (guardado no posto) e o parâmetro sai da URL.
- `KDS__NUXT_PUBLIC_ORDERS_URL` nos dois specs de `.do/`.
- Removido por estar sem uso: `KdsExpeditionCard.vue`, `KdsExitPreparingCard.vue` (e testes),
  write-side da Saída no `useKdsBoard` (expedir, desfazer, pronto da estação, SSE geral da Saída),
  `exitChipView`/`handoff*` da apresentação do KDS.
- Fica no backend (morto para a tela da Cozinha, mas com dependentes): `KDSExpeditionActionView`,
  `KDSExpeditionUndoView`, `_build_expedition_board`/`preparing` da projeção do KDS (contrato,
  testes de paridade, `kds_core.expedition_*`). Remover depois de o dono confirmar a aposentadoria.

## Evidência
- `pytest shopman/backstage/tests/test_expedicao_unica_no_gestor.py` → 13 passed.
- Conjunto KDS/Saída/undo/antessala/esquemas (18 arquivos) → 255 passed.
- `test_vocabulario_de_tela`, `test_copy_sem_travessao`, `test_api_perimeter`, `test_group_permission_parity` → passed.
- orders-nuxt: vitest 53 arquivos, 551 passed; `nuxi typecheck` 0; eslint 0 erros.
- kds-nuxt: vitest 7 arquivos, 101 passed; typecheck 0; eslint limpo.
- operator-kit: vitest 104 arquivos, 1120 passed (inclui `guardrails.vocabulary` e `guardrails.noEmDash`).
- `scripts/check_surface_registry.py` e `check_surface_versions.py` → ok. `ruff` limpo.
- Suítes inteiras backstage + shop: ver PR (rodada local abaixo).

## Fora
- E2E Playwright (`kds-nuxt/tests/e2e/exitMoved.spec.ts`, novo) não rodou: sem Chromium aqui.
- O "Visão: Saída" ainda é lembrado por posto (`Terminal.metadata.gestor_board`); o vínculo do
  posto "Expedição" é da UX-POSTO1.
- Quem só expede ainda recebe 403 silencioso de `channels/attention` (sinal de Canais) no
  quadro; não aparece na tela.
- Tile do Gestor na Central continua só para `shop.manage_orders`.

## Pergunta ao dono
Quem expede hoje é quem tem `backstage.operate_kds`, e isso inclui todo cozinheiro de estação.
Manter assim (cozinheiro pode expedir pelo Gestor, como podia pela Saída da Cozinha), ou criar
uma permissão "Expedir" e um grupo "Expedição" separados de `operate_kds` (muda `setup_groups`)?
