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

Linhas conferidas em **2026-10-15 13:2x UTC** (fila de merge, `gh pr view` e branches contra o
remoto), contra `origin/main` = `48eb028c2`. Antes disso o quadro estava parado desde 02/10 e
carregava quatro linhas `EM_EXECUCAO`/`EM_PR` do suite-ux que **já estavam mergeadas** (o
`make coordination` as acusava como reivindicações órfãs há 286 h). Registros históricos:
`ROUNDS/R0-reconciliar-handoff.md` e `ROUNDS/R2-relatorio-da-reconciliacao.md`. O
`make coordination` acusa linha `EM_PR` cujo PR já saiu: ao mergear, **tire a linha no mesmo
PR** (escreva o registro com "na fila #N").

**ONDA4-5 (20/10):** import/export da Base de insumos e fornecedores entregue no PR #1964 (`codex/import-export-base`), empilhado sobre #1957. Prévia sem escrita, revisão/ator, erro por registro, aplicação e auditoria atômicas; exportação completa pelo kit. Quinze testes API e oito de navegador aprovados; 300 → 22 consultas para dez cadastros, e custo fixo 5/22/5 (fornecedor) e 6/23/5 (insumo) para prévia/aplicação/export com 2 ou 40 registros. Registro em `ROUNDS/ONDA4-5-import-export-base.md`.

**ONDA4-4 (20/10):** lote de fornecedores entregue no PR #1957 (`codex/lote-fornecedores`), com confirmação, Desfazer revisado e auditoria atômica. Sete testes API, dois de componente e quatro de navegador aprovados. Medição: 188 → 30 consultas para dez fornecedores; 2/40 fornecedores mantêm 28 consultas. Registro em `ROUNDS/ONDA4-4-lote-fornecedores.md`.

## Em execução agora

Frentes do turno de 15/10. Todas são de **outras sessões**; esta coordenação acompanha por PR
e não tem agente próprio em voo. Antes de pegar qualquer uma, confira o PR.

| id | frente | estado | branch / PR | desde (UTC) |
|---|---|---|---|---|
| §7.1-5a | Core: cliente em vários grupos (N:N) e vantagens tipadas | EM_PR | `claude/grupos-core` / #1812 | 2026-10-15 12:07 |
| §7.2-4 | Clientes: duplicar cadastro e etiquetar em lote | EM_PR | `claude/cadastro-clientes` / #1815 | 2026-10-15 12:5x |
| §7.2-3 | Produção: cadastro direto da ficha de execução no Nuxt | EM_PR | `claude/cadastro-receitas` / #1816 | 2026-10-15 12:5x |
| WATCHMAN | Saúde, autocura e desempenho (Codex, outro agente) | EM_PR | `codex/watchman-*` / #1809, #1813 | 2026-10-15 11:5x |

**SUITE-UX (03/10, sessão suite-ux):** mergeados #1398 (plano), #1404 (UX-R2), #1405 (UX-N1), #1406 (UX-G1), #1407 (UX-V1), #1408 (UX-P1), #1409 (UX-C1). **Fechado em 15/10:** UX-P2 #1419, UX-M1 #1420, UX-H1 (`claude/ux-h1-central-fila`) e UX-G2 (`claude/ux-g2-pronto-automatico-desfazer`) — conferidos: os quatro branches estão contidos no `main`. Registros em `ROUNDS/UX-*.md`.

**Turno de 15/10 (coordenação DSH):** mergeados #1810 (`GET /api/sessions` responde 200) e #1814 (card de desconto por tipo no B.I.). Higiene de disco: 185 worktrees removidas, 34 GB para ~140 GB livres. Reconciliação com o Codex: o núcleo das ondas 3, 4 e 5 do §7.2 já entrou por #1802 a #1806. Detalhe em `HANDOFF-DSH-2026-10-15.md`.

**Turno ARQUIVAR de 20/10:** Frente A, `offerman.Product.is_active`, entregue e colocada na fila no
#1945. A decisão está em D-034, a ordem em `ORDERS/2026-10-19-arquivar.md` e a prova em
`ROUNDS/ARQUIVAR-A-core-produto.md`. Não fica linha ativa no quadro porque a frente já saiu da
execução para a fila.

**Turno ARQUIVAR, Frente F:** o gesto confirmado de Arquivar/Desarquivar, individual e em lote,
foi entregue e colocado na fila no #1948 (`codex/arquivar-gesto`), com as dependências #1945 e
#1947 integradas. Prova funcional, desempenho, D1 a D12 e capturas em
`ROUNDS/ARQUIVAR-F-gesto.md`.

**Turno Arquivar (20/10, Frente D):** Compras passou a separar insumos e fornecedores
arquivados das listas correntes, com o filtro explícito **Arquivados**, no PR #1946. A
frente saiu do quadro ao entrar na fila; prova e limites estão em
`ROUNDS/D-arquivar-compras.md`.

**Turno ARQUIVAR (20/10):** Frente E, receitas com `RecipeEntry.is_active`, na fila no PR #1944. Detalhe em `ROUNDS/E-arquivar-receita.md`.

**Turno ARQUIVAR (20/10):** Frentes B+C, trava transversal e superfícies de produto arquivado,
entregues e colocadas na fila no PR #1947. A loja, a busca, a matriz, os feeds, os canais e o B.I.
agora respeitam o arquivamento; retração e reenvio foram provados por transporte simulado. Detalhe
em `ROUNDS/ARQUIVAR-BC-superficies.md`.

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
| SESS-N1 | `GET /api/sessions` faz N+1 em `Session.items`: página cheia de 25 = **26 consultas**. O prefetch já é previsto pelo modelo, então `prefetch_related("session_items")` no `SessionViewSet.get_queryset` cai para **2**. Confirmado ausente em `origin/main` `48eb028c2`. Follow-up de uma linha, mas muda comportamento observável; o agente do #1810 o deixou fora do escopo de propósito | `HANDOFF-DSH-2026-10-15.md`, "Defeito conhecido" |
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
2. ⛔ **O checkout principal está 4730 commits atrás** de `origin/main` (medido em 15/10 13:2x
   UTC), no branch `codex/shopman-backstage-marketing-hardening`. Leia de `origin/main`, escreva
   em worktree. O `make coordination` **não existe** neste checkout (o Makefile é velho demais):
   rode `python3 scripts/coordination_status.py` de um worktree atualizado.
3. ⛔ **NUNCA `doctl apps update` no spec vivo.**
4. O branch `dsh/handoff-onda1-e-p7-20260930` tem 1 commit fora do `main` mas o conteúdo já está
   lá; ele está em uso na worktree `.dsh-worktrees/go-live-acceleration` do DeepSeek Harness. Não
   apague: o `make coordination` o mostra como "conteúdo já no main".
5. O `make coordination` só mede CI e auto-merge **com `gh` autenticado**. Sem `gh` ele diz isso numa
   linha, e o `OK` do fim não cobre PR vermelho parado (o #1367 ficou 6 h vermelho com o resumo `OK`).
