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

Conferido contra o remoto em 2026-10-02 15:55 UTC (`origin/main` = `bddd02693`, #1375). Registros:
`ROUNDS/R0-reconciliar-handoff.md` (a conferência do HANDOFF) e `ROUNDS/R2-relatorio-da-reconciliacao.md`
(o que o R0 e este quadro ainda erravam). O `make coordination` acusa linha `EM_PR` cujo PR já saiu:
ao mergear, **tire a linha no mesmo PR** (escreva o registro com "na fila #N").

## Em execução agora

| id | frente | estado | sessão | branch / PR | desde (UTC) |
|---|---|---|---|---|---|
| R1 | Receitas: comando `import_recipe_versions` (C.7 do WP-RECEITAS-DO-DONO) | `EM_PR` (import trocado pela porta pública em 02/10 16:3x; só o "Marketing — cadeia completa" vermelho, D-027, não obrigatório) | coordenacao-pedidos-4f89d4 (desencalhe; autora: coordenador noturno 02/10) | #1367 (`claude/receitas-fx-import`) | 2026-10-02 16:29 |
| T0 | Ordem 0: ordem durável, BOARD, HANDOFF linha 75 (rota da observação é por LINHA); brief T6 | `EM_PR` | coordenacao-pedidos-4f89d4 | #1379 (`claude/coordenacao-pedidos-4f89d4`) | 2026-10-02 16:29 |
| T1 | PDV: formas de pagamento travadas até a revisão do desconto voltar (opção b) | `EM_PR` (fila) | coordenacao-pedidos-4f89d4 | #1380 (`claude/pdv-pagamento-espera-revisao`) | 2026-10-02 16:29 |
| T1b | PDV: o "Exato" (tecla `=`) espera a revisão também | `EM_EXECUCAO` (depois do #1380) | coordenacao-pedidos-4f89d4 | `claude/pdv-exato-espera-revisao` | 2026-10-02 17:20 |
| T2 | Loja: um só aviso no cardápio (overlay narra, card azul de caminho feliz sai) | `EM_PR` (fila) | coordenacao-pedidos-4f89d4 | #1381 (`claude/loja-cardapio-um-aviso`) | 2026-10-02 16:29 |
| T3 | Loja: observação por item vira folha (BottomSheet) | `EM_PR` (fila) | coordenacao-pedidos-4f89d4 | #1383 (`claude/loja-observacao-em-folha`) | 2026-10-02 16:29 |
| T4 | PDV: modo Encomendas vira assistente | `EM_EXECUCAO` | coordenacao-pedidos-4f89d4 | `claude/pdv-encomenda-assistente` | 2026-10-02 17:05 |
| T5 | PDV > Encomendas: matar redundâncias R1 a R5 | `EM_PR` (fila) | coordenacao-pedidos-4f89d4 | #1382 (`claude/encomendas-sem-redundancia`) | 2026-10-02 16:29 |
| T6 | PDV > Encomendas: brief do redesenho | `AGUARDA_DONO` (P1 a P7 do brief) | coordenacao-pedidos-4f89d4 | #1379, `docs/plans/WP-POS-ENCOMENDAS-REDESENHO-BRIEF.md` | 2026-10-02 16:29 |
| T7 | Primitivas no kit (`OperatorSchedulePicker`, `OperatorReasonDialog`) | `AGUARDA_DONO` (aval do brief T6) | nada | nada | 2026-10-02 16:29 |

**R1 está parado desde 09:25 UTC.** Auto-merge ligado, `BLOCKED`. Causa: o comando novo importa
interno do kernel, `import_recipe_versions.py:60` → `shopman.craftsman.contrib.formula.percentages`
(`test_architecture.py::test_no_deep_kernel_imports_all_apps` e
`test_import_boundaries.py::test_framework_does_not_import_protected_kernel_internals`, run
36988496707). Reprovam por isso "Shop rest", "Shop heavy", "Testes (test-shop)" e "Coverage Gate".
O vermelho do "Marketing — cadeia completa" é o `node-forge` (D-027, não obrigatório). Próximo
passo: trocar o import pela porta pública do Craftsman, como o #1374 fez em `7979427a1`. As 14
fichas já estão publicadas no alpha e no seed (#1370): o comando é para a próxima importação, não
segura o go-live.

## Fila livre (ninguém pegou)

| id | frente | por onde começar | nota |
|---|---|---|---|
| F4 | Pix real: preparar o ensaio, sem ligar | `docs/runbooks/go-live-preflight.md` §4 | **ligar é do dono** (D-016). Hoje `SHOPMAN_PIX_ADAPTER=payment_mock` no arquivo e no vivo (drift sem divergência nessa chave, 02/10) |
| F5 | Trazer `JEV_API_KEY` (`type: SECRET`, sem `value`) e `SHOPMAN_INTENT_PILOT_PROVIDERS_APPROVED` para o arquivo do spec | `python3 scripts/check_do_spec_drift.py --context shopman-do-app-admin` | as duas existem só no vivo desde 02/10; o drift deve voltar a acusar só `SHOPMAN_COURIER_ADAPTER`. Ler o valor de `PROVIDERS_APPROVED` no painel, nunca adivinhar |
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

1. ⛔ **O drift do spec está `[FAIL]`, e não é mais só uma chave.** Em 02/10 14:40 UTC, três existem
   só no vivo: `SHOPMAN_COURIER_ADAPTER` (de propósito, D-020/D-026), `JEV_API_KEY` e
   `SHOPMAN_INTENT_PILOT_PROVIDERS_APPROVED` (F5). **Aplicar o arquivo desliga a entrega por
   parceiro e o Jev.**
2. ⛔ **O checkout principal está 3201 commits atrás** de `origin/main` (02/10 15:55 UTC), num branch do Codex
   de 28/08. Leia de `origin/main`, escreva em worktree.
3. ⛔ **NUNCA `doctl apps update` no spec vivo.**
4. O branch `dsh/handoff-onda1-e-p7-20260930` tem 1 commit fora do `main` mas o conteúdo já está
   lá; ele está em uso na worktree `.dsh-worktrees/go-live-acceleration` do DeepSeek Harness. Não
   apague: o `make coordination` o mostra como "conteúdo já no main".
5. O `make coordination` só mede CI e auto-merge **com `gh` autenticado**. Sem `gh` ele diz isso numa
   linha, e o `OK` do fim não cobre PR vermelho parado (o #1367 ficou 6 h vermelho com o resumo `OK`).
