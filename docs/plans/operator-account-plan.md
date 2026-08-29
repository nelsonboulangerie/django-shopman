# Plano — Conta do operador

Data: 2026-08-29
Status: **futuro.** Backend pronto; a tela não existe e não foi autorizada.

## O problema

O operador não tem onde cuidar da própria conta. Cada coisa mora num lugar diferente:
trocar PIN só na tela de destravar, ver acessos só no Admin (outro domínio), invalidar
crachá só por API. Quem precisa de qualquer uma delas depende de lembrar o caminho, ou
do gerente.

## O que reúne

| Item | Backend | Falta |
|---|---|---|
| Meus acessos | `GET /api/v1/backstage/sign-ins/` | ✅ já tem lista no sino |
| Perdi meu crachá | `POST /api/v1/backstage/operator/badge/lost/` | ✅ já tem botão na trava |
| Trocar PIN | `POST /api/v1/backstage/operator/pin/change/` | já tem tela na trava; mudaria de casa |
| Meus dispositivos | — | fora de escopo por ora |

Tudo é sobre a **própria** conta. Nenhuma tela aqui lê a conta alheia.

## Onde mora

Rota `/account` em cada app de operador, servida pela layer `operator-kit` — que já é a
casa do `OperatorLock` e da troca de PIN. Uma implementação, sete apps.

O sino já subiu para a layer (`NotificationBell`), e com ele o log da própria conta. O que
a página acrescentaria é espaço: a lista cabe num painel, mas filtro e histórico longo não.

## Tamanho

Uma composable de notificação na layer + uma página com três blocos. Sem model novo, sem
migração, sem endpoint novo.

## Enquanto não existe

- **Meus acessos**: no sino, em qualquer app de operador. O Admin (Auditoria → Acessos de
  operador) segue sendo o único lugar que mostra a trilha de TODOS — só gerente.
- **Perdi meu crachá**: já resolvido na trava do operador. A página de conta só mudaria
  a casa, não o comportamento.
