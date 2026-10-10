# BOARD — o que está em voo, e de quem é

> **Rode `make coordination` (`python3 scripts/coordination_status.py`) e leia este arquivo ANTES
> de pegar qualquer frente.** Se a frente já está `EM_EXECUCAO` por outra sessão nas últimas
> 12 horas, **não toque**: pegue a próxima. Duas sessões já abriram PR para a mesma coisa na noite
> de 01/10 (#1354 às 23:46 UTC e #1357 às 00:04 UTC de 02/10: 18 minutos, nenhuma sabia da outra).
>
> **A reivindicação que vale é o PR draft, não esta linha.** O BOARD só chega ao `main` pela fila
> (minutos), e uma linha `EM_EXECUCAO` num branch seu ninguém vê. Ao pegar uma frente: empurre o
> branch e abra PR draft `WIP: <id> …` **antes** do primeiro edit de código; o `make coordination`
> mostra PR aberto na hora, para todas as sessões. No mesmo PR, a linha vai para `EM_EXECUCAO` (hora
> UTC `AAAA-MM-DD HH:MM`). Antes de enfileirar: a linha **sai** e o registro entra em
> `docs/coordination/ROUNDS/<id>-<slug>.md` com "na fila #N" (a fila mergeia sem você voltar; linha
> `EM_PR` de PR que já saiu, o comando acusa).

Estados: `LIVRE` · `EM_EXECUCAO` · `EM_PR` · `AGUARDA_DONO` · `ADIADO`.

`FEITO` não fica aqui: o histórico é do HANDOFF e o detalhe é de
`docs/coordination/ROUNDS/<id>-<slug>.md`.

Linhas do turno conferidas em 2026-10-02 17:05 UTC (fila de merge e `gh pr view`). Quadro conferido contra o remoto em 2026-10-02 15:55 UTC (`origin/main` = `bddd02693`, #1375). Registros:
`ROUNDS/R0-reconciliar-handoff.md` (a conferência do HANDOFF) e `ROUNDS/R2-relatorio-da-reconciliacao.md`
(o que o R0 e este quadro ainda erravam). O `make coordination` acusa linha `EM_PR` cujo PR já saiu:
ao mergear, **tire a linha no mesmo PR** (escreva o registro com "na fila #N").

## Em execução agora

| id | frente | estado | sessão | branch / PR | desde (UTC) |
|---|---|---|---|---|---|
| UX-P2 | Planejamento: o número na linha e o "Por quê" por cima (SUITE-UX §15) | EM_PR | suite-ux (session_01UcT9P3) | #1419 | 2026-10-03 14:00 |
| UX-M1 | Marketing: fila de decisões por prazo (SUITE-UX §9) | EM_EXECUCAO | suite-ux (session_01UcT9P3) | #1420 | 2026-10-03 14:00 |
| UX-H1 | Central como fila das filas (SUITE-UX §6) | EM_EXECUCAO | suite-ux (session_01UcT9P3) | `claude/ux-h1-central-fila` | 2026-10-03 14:08 |
| UX-G2 | Gestor: "pronto" automático e desfazer de 5 s em Entregar/Despachar (SUITE-UX §5.1, §15) | EM_EXECUCAO | suite-ux (session_01UcT9P3) | `claude/ux-g2-pronto-automatico-desfazer` | 2026-10-03 14:47 |

**SUITE-UX (03/10, sessão suite-ux):** mergeados #1398 (plano), #1404 (UX-R2), #1405 (UX-N1), #1406 (UX-G1), #1407 (UX-V1), #1408 (UX-P1), #1409 (UX-C1). Registros em `ROUNDS/UX-*.md`.

**Turno das observações do dono (02/10, sessão coordenacao-pedidos-4f89d4).** Mergeados: #1367 (R1,
desencalhado), #1380 (T1), #1381 (T2). Na fila: #1379 (T0 + brief T6), #1382 (T5), #1383 (T3),
#1384 (T4) e #1385 (T1b). Registros em `ROUNDS/R1-*.md` e `ROUNDS/T0-*.md` a `T6-*.md`, `T1b-*.md`. Fatias do redesenho mergeadas: S3 #1388, S4 #1391, S7 #1390, S7b #1392, S8 #1387, S9 #1393, S2 #1394, S5 #1396, S6 #1397; D42 #1389. O brief das Encomendas (T6) está entregue inteiro. Registros em `ROUNDS/S*-*.md` e `ROUNDS/D42-*.md`.

## Fila livre (ninguém pegou)

| id | frente | por onde começar | nota |
|---|---|---|---|
| F4 | Pix real: preparar o ensaio, sem ligar | `docs/runbooks/go-live-preflight.md` §4 | **ligar é do dono** (D-016). Hoje `SHOPMAN_PIX_ADAPTER=payment_mock` no arquivo e no vivo (drift sem divergência nessa chave, 02/10) |
| F2 | Triar o trabalho dormente do remoto: 29 branches com PR **fechado sem merge** e commits fora do `main` (de 1 a 26 commits; o maior é `codex/shopman-legal-google-oauth-20260911`, #614), 7 com conteúdo já no `main`, e os 15 `rescue/*` (10 a 17/09) | `make coordination`, seção "SEM PR" (lista cada um com o número do PR) | apagar o que já está no `main` ou foi recusado de propósito (ler o comentário de fechamento do PR); PR draft do que se perdeu sem querer. Ficam: `codex/print-layouts-20260912`/`rescue/print-layouts-*` (triados no #1120) e `dsh/handoff-onda1-e-p7-20260930` (worktree do DSH). Apagar branch remoto **não** é mecânica: lista na mão do dono antes |

## Aguardando o dono

| id | o que trava | onde |
|---|---|---|
| ManyChat | Faltam 4 modelos (`pontos_fidelidade`, `pedido_entregue_v2`, `fila_vaga_disponivel_v2`, `produto_chegou_v2`); `pagamento_falhou` foi enviado e está em análise na Meta. Depois, os flows de `pedido_em_preparo` e `reembolso_processado` (aprovados). A ligação evento → flow é linha no `MANYCHAT_FLOW_MAP` (`config/settings.py`) num PR, **não** o Admin. Trava: o Chrome visível, janela sem nada por cima, na aba "Criar modelo" do grupo do Claude, por ~20 min | `docs/reports/go-live-acceleration-20261002/MANYCHAT-ESTADO-0210.md` |
| Entrega | `fulfillment.courier="auto"`: chama a TaOn de verdade. Não reconferido no vivo em 02/10 | HANDOFF §0.5 |
| Link | gerar UM link de pagamento no PDV para provar que sai. Não reconferido no vivo em 02/10 | HANDOFF §0.3 |
| Pix | o ensaio do Pix real antes da virada | D-016 |
| Concierge | D41 (FAQ, copy, flow) e o ensaio manual: nenhum comando enxerga se o flow chama o External Request em toda mensagem (a API do ManyChat não expõe o flow) | `docs/plans/WHATSAPP-CONCIERGE-PLAN.md`, "Verificação" |
| — | D35 Threads · D38 Actions (conferido 02/10: `can_approve_pull_request_reviews: false`) · D39 pós-v1 · D41 Concierge | PENDING-DECISIONS |
| — | antigas: D2, D8, D18(b,d,e), D22, D23, D25, D26, D27, D30, D31 | PENDING-DECISIONS |

D34, D36, D37 e D40 **saíram desta lista**: o dono respondeu em 02/10 e o trabalho entrou
(#1365/#1374, #1373, #1371/#1372, #1370). Ver a atualização de 02/10 (dia) no topo do
`PENDING-DECISIONS.md`.

O texto completo de cada decisão está em `PENDING-DECISIONS.md`. **Não duplique aqui.**

## Adiado, com motivo

| id | frente | motivo | reabrir quando |
|---|---|---|---|
| A1 | `npm audit` acusa `node-forge` | não há versão corrigida; o job não é obrigatório; o pacote não chega ao `.output` (D-027, reconfirmada pelo dono em 02/10) | sair o 1.4.1 |
| A2 | Controles de data, o resto | PDV, Produção, B.I. e Compras entraram (#1371, #1372). Restam só os do Marketing (`CampaignForm`, `AnnouncementCard`, `GoogleBusinessPostOptions`, `MarketingOfferForm`), fora do go-live (D-017), e o aniversário do perfil na loja, que é superfície de cliente e não entra na D37 | o Marketing voltar ao escopo |

## Armadilhas ativas (leia antes de mexer)

1. `SHOPMAN_COURIER_ADAPTER` mora no arquivo do spec desde 10/10 (#1633), com o valor do vivo
   (D-026 superada). O drift que restou em 10/10 é `KDS__NUXT_PUBLIC_ORDERS_URL` só no arquivo: o
   vivo não a tem e a Saída do KDS aponta para `http://127.0.0.1:3004/`; o arquivo está certo.
2. ⛔ **O checkout principal está 3201 commits atrás** de `origin/main` (02/10 15:55 UTC), num branch do Codex
   de 28/08. Leia de `origin/main`, escreva em worktree.
3. ⛔ **NUNCA `doctl apps update` no spec vivo.**
4. O branch `dsh/handoff-onda1-e-p7-20260930` tem 1 commit fora do `main` mas o conteúdo já está
   lá; ele está em uso na worktree `.dsh-worktrees/go-live-acceleration` do DeepSeek Harness. Não
   apague: o `make coordination` o mostra como "conteúdo já no main".
5. O `make coordination` só mede CI e auto-merge **com `gh` autenticado**. Sem `gh` ele diz isso numa
   linha, e o `OK` do fim não cobre PR vermelho parado (o #1367 ficou 6 h vermelho com o resumo `OK`).
