# Coordenação: onde está a verdade

> Esta página existe porque "ler os docs" deixou de ser um plano viável. São
> dezenas de planos, decisões e worktrees. O estado não se descobre por leitura;
> descobre-se por comando.

## As quatro perguntas

| Pergunta | Fonte | Comando |
|---|---|---|
| O que está em voo agora? | worktrees, branches e PRs | `make inflight` |
| O que o repo deve, e o que venceu? | [COMMITMENTS.md](COMMITMENTS.md) | `make commitments issues=1` |
| O que o dono decidiu? | [DECISIONS.md](DECISIONS.md), histórico até a migração | leitura |
| O produto está pronto para o go-live? | [GO-LIVE-READINESS-PLAN.md](../plans/GO-LIVE-READINESS-PLAN.md) | `make production-readiness` |

Tudo o mais em `docs/coordination/` é história: `ROUNDS/`, `EVIDENCE/`, `ORDERS/`,
`GO-LIVE-HANDOFF-*`. História não é estado. Se um doc antigo contradiz um comando,
o comando vence.

## O ciclo semanal (10 minutos)

1. `make commitments issues=1` lista o que venceu no ledger, as decisões legadas de
   `DECISIONS.md` e as issues abertas com label que nenhuma linha cita. O comando
   não falha por vencido; o job semanal é quem cobra.
2. Para cada vencido: fazer, reagendar com motivo, ou descartar com quem decidiu.
3. `make inflight` mostra o que ficou em worktree, branch ou PR vermelho.
4. Nenhum item sai da lista por silêncio: ou vira `FEITO` com prova, ou
   `DESCARTADO` com motivo. Item que ninguém toca continua vencido, e o job
   semanal o traz de volta.

## O detalhe pode ser uma issue

O ledger é o índice; o detalhe pode viver numa issue do GitHub. Uma linha cita a
issue na `origem` (`#2298 / #2300`), e o `make commitments issues=1` aponta a issue
com label `ficou-de-fora`, `helpdesk`, `dev`, `decisao` ou `achado` que **nenhuma**
linha cita. Assim o gesto de abrir issue não vira um segundo backlog invisível.

## O que o CI cobra

- PR declara o que ficou de fora na seção `## Ficou de fora`; cada item é uma
  issue aberta com label `ficou-de-fora` (check "Ficou de fora declarado"). O
  ledger indexa a issue com dono, prazo e prova.
- PR novo (a partir de 13/11/2026) precisa da linha `Compromisso: DEV-AAAA-NNN`, ou
  `Compromisso: nenhum` com o motivo.
- O ledger reprova: ID duplicado, estado fora do vocabulário, item aberto sem
  `revisar_em`, dono vazio, `FEITO` sem prova, `SUPERSEDIDO` sem sucessor.
- O job semanal abre uma issue com os vencidos; quando a lista zera, fecha.

## Por que isto existe

A queixa de 12/11/2026: adiamento nascia como prosa no corpo do PR e morria no
merge. O #2298 deixou dois itens reais sem ID, dono ou data; o #2292 deixou mais
dois. O ledger é a trava; esta página é o mapa.
