# UX-H1: a Central vira a fila das filas

**Estado:** pronto (03/10/2026), PR #1421
**Branch:** `claude/ux-h1-central-fila`
**Plano:** `docs/plans/SUITE-UX-FUNCTION-PLAN.md` §4.1 (FILA), §6 (navegação e Central), §9 (postos), §16 (nome);
fichas H01 a H04 em `docs/plans/suite-ux-v2/funcoes/kds-hub.md`; prévia `docs/plans/suite-ux-v2/v4/hub.jpg`.

## Objetivo

Decisão do dono: a Central (`surfaces/hub-nuxt`) passa a ser "a fila das filas". No topo,
"Precisa de você": a soma das filas dos papéis deste operador, o item exato primeiro, ordenado por
urgência entre apps, com o essencial da decisão, o tempo esperando (âmbar quando estoura) e um
gesto que abre o lugar exato no app certo. Embaixo, os blocos dos apps, calmos, cada um com uma
linha de estado que concorda com a fila.

## O que foi feito

**Backend (backstage, Core intocado).** Nasce `shopman/backstage/projections/hub_queue.py`, chamado
por `projections/hub.py`. O `GET /api/v1/backstage/hub/` passa a trazer `hub.queue` (`items` em foco,
no máximo 6; `total_count`; `more_count`, o "+N"; `server_now`) e, em cada tile, `status_attention`
e `status_summary`. Cada item: `app`, `kind`, `title`, `detail`, `waiting_since`, `due_at`,
`due_label`/`due_style`/`due_clock`, `time_mode`, `attention`, `action_label`, `url`.

Fontes (todas já existiam; nenhuma regra nova):

| app | item exato | fonte | gesto (URL) |
|---|---|---|---|
| Gestor | "Pedido K7Q2 para aceitar" · canal · cliente · total · "aceita sozinho em 2:40" | pedido `new` do dia, sem Balcão e sem encomenda futura (régua do quadro); prazo do `confirmation.timeout` ou `data.ifood.confirm_by` | `gestor./<ref>` (detalhe do pedido) |
| Cozinha | "Pedido F15 atrasado: 2x Croissant" · estação · meta | ticket ativo de estação (sem Saída) além de `target_time_minutes`, data de hoje (régua do quadro) | `kds./<estação>` |
| PDV | "Encomenda de Ana para retirar" · itens · saldo · "retira às 10:30" | `build_preorder_list` de hoje, retirada aberta com janela na próxima hora | `pdv./preorders/<ref>` |
| Produção | "Lote de Croissant passou do tempo" · ref · início · meta | lote `started` além de `max_started_minutes` (`_is_late_started`) | `prod./expedite?q=<ref>&date=<dia>` |
| Marketing | "Anúncio para decidir: <regra>" · plataformas · alcance · "decide até 10:15" | anúncio `pending_review` não caducado | `mkt./announcements/<id>` |
| Avisos | o tipo do alerta · a mensagem | `OperatorAlert` não visto, `error`/`critical`, com contexto num app (`_alert_actions`) | o mesmo link do sino do Gestor ou do contexto da Produção |

- **Urgência entre apps:** folga em segundos até estourar a meta ou o prazo (negativa = estourou);
  crítico no topo. Meta do aceite = 4 min (o "urgente" do card do Gestor). Âmbar quando estourou
  ou quando o prazo está a menos de 15 min.
- **Permissão por item:** cada fonte só roda para quem passa no MESMO predicado da porta do app
  (`can_manage_orders`, `can_operate_kds`, `can_operate_pos`, `can_operate_production`,
  `can_manage_campaigns`), e o anúncio exige também `shop.approve_marketing_announcements`.
  App sem URL configurada não gera item. Alerta de produção (que guarda o ref do LOTE em
  `order_ref`) nunca vira "Abrir o pedido" no Gestor.
- **Falha isolada:** fonte que quebra sai do resultado com `hub_queue.source_failed` no log; a
  Central continua de pé.

**Nuxt (`surfaces/hub-nuxt`).** Seção "Precisa de você" no topo (lista ordenada, ícone e nome do
app, título, detalhe com o prazo na frase, tempo à direita em âmbar quando pede, gesto de 48 px
com nome acessível "Abrir pedido: Pedido K7Q2 para aceitar", "+N" como frase, estado vazio calmo).
Os blocos dos apps ficaram mais compactos (ícone ao lado do nome, linha de estado com ponto âmbar
na parte que pede alguém), em grade de altura única (`auto-rows-fr`). A linha de estado é aviso e
não se corta (regra do `guardrails.copyNeverTruncates`). O relógio anda a cada segundo e conta pela
hora do servidor (`server_now`). Tempo real: sem canal SSE próprio, poll calmo de 30 s com a tela
visível e releitura ao voltar a tela ou a rede (ADR-016). Lógica pura em `presentation/hub.ts`.

## Evidência

```
pytest shopman/backstage/tests/test_hub_queue.py test_api_hub_surface.py test_hub_projection_identity.py
       test_unauthenticated_error_code.py                         → 54 passed
pytest test_surface_registry_gate.py test_new_surface_generator.py test_vocabulario_de_tela.py → 2258 passed
pytest shopman/backstage/tests -n 8 (suíte inteira do backstage)  → 7500 passed, 59 skipped
  (a 1ª rodada pegou o gate Unfold: `hub_queue.py` precisava entrar na superfície
   `runtime-central-hub` de scripts/check_unfold_canonical.py; corrigido)
ruff check shopman/backstage                                      → All checks passed!
scripts/check_surface_registry.py                                 → todos os lugares concordam
hub-nuxt: vitest run                                              → 4 files, 42 tests passed
hub-nuxt: nuxi typecheck                                          → sem erro
hub-nuxt: eslint .                                                → sem erro
hub-nuxt: nuxt build + SSR com o mock dos e2e (curl)              → renderiza "Precisa de você",
                                                                     "Pedido K7Q2 para aceitar", "há 2 min",
                                                                     "Mais 2 esperando nos apps abaixo."
operator-kit: vitest run (inclui guardrails.vocabulary e copyNeverTruncates) → 99 files, 1051 passed
```

## O que ficou de fora, e por quê

- **Compras e B.I. sem linha de estado nem item.** Compras não tem "chegou na doca" modelado (o
  recebimento é uma sessão aberta pelo operador, sem aviso de chegada), e a sugestão de reposição
  só sai de `build_purchase`, que lê o ledger de todos os insumos: pesado para uma home relida a
  cada 30 s. Faltaria: um evento de chegada (NF-e recebida pelo leitor de Compras) ou uma leitura
  barata de "insumos abaixo do ponto de reposição". B.I.: os alarmes (`bi_*`) são de público
  `finance`/`operations` sem tela de destino num app; ficam no Admin e no e-mail.
- **"Plano de amanhã pede sua aprovação" (Produção) não existe:** não há conceito de aprovação do
  plano. Entra quando o Planejamento ganhar o gesto (frentes #1406 a #1409, #1419).
- **Quem tem um app só entrar direto na fila do app:** não é simples. Redirecionar a Central
  tornaria a volta do rail ("à Central") um laço, sobretudo com a Central instalada como app.
  Faltaria: o rail marcar a volta (parâmetro ou estado de sessão) e a Central pular só na entrada.
- **Deep link exato na Cozinha:** o KDS não abre um ticket pelo endereço; o gesto abre a estação,
  onde o pedido atrasado já vem primeiro. Negociação do iFood (`handshake_pending`) também não
  entrou como item.
- **SSE da Central:** precisaria de um canal que some os canais dos cinco apps com as permissões de
  cada um. Por ora, poll calmo.
- **Custo da fonte da Cozinha:** resolve a venda de cada ticket ativo (uma consulta por ticket, a
  mesma régua do quadro da estação). Com dezenas de tickets é barato; se crescer, vale um lote.
- **E2E (Playwright):** o spec e o mock foram atualizados, mas o Chromium não instala neste
  ambiente; não rodei.
