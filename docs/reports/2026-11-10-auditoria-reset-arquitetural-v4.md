# Auditoria do reset arquitetural do Django Shopman, versão 4

**Estado:** relatório prévio, para análise adversarial por um terceiro agente externo.
**Não é para mergear.** Este arquivo vive num branch só para ficar acessível. Não é decisão, não
autoriza implementação e não altera nenhum documento canônico.
**Base factual:** `origin/main` em `7f829e02f89b8c10fc5e00b683a6a31617026fc7`.
**Autoria:** Claude (coordenador), consolidando três rodadas.

| Rodada | Quem | O que fez | Onde está |
|---|---|---|---|
| v2 | Claude, 24 agentes em leitura | Inventário e veredito "aprova com reparos" | `docs/reports/2026-11-10-auditoria-reset-arquitetural.md` no `main` |
| Revisão e v3 | Codex | Revisão adversarial da v2 e proposta consolidada | branches `codex/reset-review-decisions` e `codex/reset-report-v3` (PRs #2259 e #2260, não mergeados) |
| v4 | Claude, 7 verificadores e 2 céticos em leitura | Reconferiu no código as afirmações novas da v3 | este arquivo |

**Limite que vale para as três rodadas:** nenhum teste, migration, seed ou medição foi executado.
Tudo é leitura de código e de documentos. Cada fato abaixo traz `arquivo:linha` ou comando para
reconferência. Convergência entre agentes do mesmo modelo não é prova.

## 0. Contexto mínimo para quem chega agora

- **Django Shopman** é a suíte de uma padaria (loja online, PDV, cozinha, produção, compras,
  fiscal, entrega). Ainda não está em uso comercial.
- **Kernels:** 13 pacotes pip-instaláveis em `packages/*` (offerman, stockman, craftsman, orderman,
  guestman, doorman, payman, buyman, fiscalman, cashman, watchman, refs, utils). Não se importam
  entre si fora de pontes `contrib/` e `adapters/`.
- **Aplicação:** três apps Django. `shopman/shop` é o orquestrador; `shopman/storefront` e
  `shopman/backstage` servem API e projections para 11 apps Nuxt em `surfaces/`.
- **Tag `go-live-v1`:** ainda não existe. Quando existir, arma a ADR-015: migrations passam a ser
  append-only; `RemoveField`, `RenameField`, `DeleteModel` exigem marcador de expand-contract.
  `CreateModel` e `AddField` continuam livres.
- **Sem data de go-live** (D-030): vira quando toda linha da matriz
  `docs/plans/GO-LIVE-READINESS-PLAN.md` estiver `VERIFICADO`. O banco atual vira a produção
  (D-029); não há reset de migrations no caminho.
- **Registro de decisões:** `docs/coordination/DECISIONS.md`, append-only, estados fechados
  (`DECIDIDA`, `EM_EXECUCAO`, `EXECUTADA`, `ADIADA`, `SUPERSEDIDA`, `BLOQUEADA`), `:14-19`.
- **ADR-001:** Protocol/adapter só com duas ou mais implementações reais (`:178-180`).

## 1. Pergunta

> Qual é a menor transformação coerente que entrega uma arquitetura simples, robusta,
> substituível e pronta para crescer, sem reescrever kernels comprovadamente fortes e sem levar
> para produção um fato que depois não se recupera?

O critério que organiza este relatório é um só: **antes da tag entra o que não se recupera depois
dela e o que custa dias. Todo o resto entra depois, uma fatia por vez.**

## 2. O que está registrado, o que o dono disse e o que é proposta

Esta separação é o ponto em que a v3 mais errou (listou propostas como "confirmadas").

**Decisões no registro (`main`):**

| Decisão | Conteúdo | Linha |
|---|---|---|
| D-017 | Fora do go-live só Marketing e B.I.; "entra todo o resto" | `DECISIONS.md:684-694` |
| D-029 | A virada é no próprio app e banco vivos | `:914-927` |
| D-030 | Sem data alvo | `:935-942` |
| D-035 | Concierge pode ficar para depois (superseda D-017 nesse ponto) | `:1003` |
| D-036 | Trocar kernel por sistema externo: desejável, sem prazo; sem Protocol na frente de kernel sem segunda implementação real | `:1022-1036` |
| D-037 | `FiscalDocument` antes da primeira NFC-e real | `:1040` |
| D-038 | Só três reparos seguram a tag: pacote de dias, `FiscalDocument`, colunas do carimbo dos fatos | `:1056-1076` |

**Falas do dono sem redação própria no registro:**

- Sobre substituibilidade: "fiz desde o início pensando nisso".
- Sobre prazo para trocar kernel por sistema externo: "Sem prazo".
- Sobre o que bloqueia a tag: "não sei, se vira aí. quero no menor tempo possível".
- Sobre `FiscalDocument` antes da primeira nota real: "Antes, claro".
- Sobre o Concierge: "Pode ser depois".

**Propostas, sem decisão:** monolito modular como nome do alvo; módulos de aplicação por ciclo;
perfis de provider; Taskman, Spendman, Human e Assetman (só existem no PR #2259:
`git grep -i "taskman\|spendman\|assetman" origin/main` só acha o relatório v2).

## 3. Veredito da v4

**APROVAR O RESET COMO ARQUITETURA ALVO, COM CORTE ESTREITO ANTES DA TAG.**

- A arquitetura alvo da v3 (seção 4 abaixo, corrigida) é boa e deve virar ADR.
- O plano da v3 não serve como gate de go-live: põe cinco ou seis entidades novas e a
  reorganização em módulos antes da tag, sem teto e sem mostrar o que se perde por esperar.
- O corte da v2 (D-038) estava estreito demais em três pontos, que a v3 apontou com razão e esta
  rodada confirmou no código (seção 5).

Quatro verbos, como na v3: **preservar** kernels e invariantes corretos; **corrigir** concorrência,
idempotência e escrita por fora; **construir** o que não tem registro durável; **mover** lógica
certa que mora no lugar errado, apagando a entrada antiga na mesma fatia.

## 4. Arquitetura alvo

### 4.1 Kernels

Respondem uma pergunta canônica, com linguagem, lifecycle, invariantes e autoridade próprios. Não
importam a aplicação (gate: `shopman/shop/tests/test_import_boundaries.py:432`) nem kernels irmãos
fora das pontes (gate `:451`; hoje 72 imports kernel→kernel, todos em `contrib/` ou `adapters/`).

| Pacote | Posição |
|---|---|
| cashman, payman, miolo do orderman, ledger e promessa do stockman, execução do craftsman | Preservar; contract tests em Postgres |
| fiscalman | Completar antes da tag (`FiscalDocument`); hoje não tem `models` |
| buyman | Completar depois (pedido de compra e recebimento em tabela) |
| guestman | Corrigir: o desfazer do merge regrava `Order.data` inteiro (`contrib/merge/service.py:456-463`) |
| offerman, doorman | Preservar; sem achado estrutural nesta auditoria |
| refs, utils, watchman | Bibliotecas e infraestrutura; não são donos de fato de negócio |

### 4.2 Substituibilidade e perfis de provider

A substituibilidade de um kernel é **intenção de desenho, sem prazo**. Não é invariante hoje, e
dizer que é seria falso:

- A aplicação lê models de kernel direto: 960 linhas de import (shop 534, backstage 403,
  storefront 23). Comando:
  `rg -n "^\s*from shopman\.(offerman|stockman|craftsman|orderman|guestman|doorman|payman|buyman|fiscalman|cashman|watchman|refs)\.models(\.\w+)* import" shopman/<app> --glob '!**/tests/**' --glob '!**/migrations/**' | wc -l`
- Quatro ciclos compartilham transação local entre kernels e por isso **só admitem provider nativo
  até redesenho**:
  1. commit do pedido com reserva, na loja online (`packages/orderman/.../commit.py:299-300,597`;
     PDV e marketplace saem antes da reserva, `shopman/shop/lifecycle.py:201-204`);
  2. PDV, pagamento com caixa (`shopman/shop/services/pos.py:4843-4854`);
  3. cancelamento com pagamento (`shopman/shop/services/cancellation.py:19-63`);
  4. produção com estoque (`craftsman/contrib/stockman`).
- A ADR-001 diz por escrito que trocar kernel "não é plug-and-play" (`:203-205`).

Perfis (formulação da v3, mantida):

| Perfil | Garantias | Uso |
|---|---|---|
| Nativo transacional | mesma transação, rollback local | padrão no monolito |
| Remoto operacional | idempotência, timeout, retry, compensação | sistema externo que assume a capacidade online |
| Importação/exportação | sincronização, reconciliação, defasagem declarada | planilha ou ERP fora do comando online |

Regra testável, no lugar de "ORM não é API pública irrestrita":

1. Toda escrita em model de kernel passa pelos services do kernel, com gate.
2. A leitura direta de models de kernel pela aplicação não cresce: catraca por arquivo sobre o
   número de hoje.
3. O contrato de cada kernel é sua suíte em Postgres. Não há documento paralelo.
4. Protocol ou registry na frente de estoque, pedido, caixa ou pagamento só nasce com segunda
   implementação real.

O que já existe e a fachada aproveita: `get_adapter` com 89 chamadas em 30 arquivos (stock 24,
courier 16, customer 14, payment 10, catalog 9), com default interno para stock, catalog,
production e customer (`shopman/shop/adapters/__init__.py:26-62`).

### 4.3 Módulos de aplicação

Pacotes Python dentro da aplicação. Não são apps Django novos e não mudam `app_label` nem
`db_table`. Os sete nomes da v3 cobrem cerca de 39% de `shopman/shop/services` (177 arquivos,
81.879 linhas) e se sobrepõem em `pos.py`, `operator_orders.py`, `order_edit.py` e `kds.py`.
Lista proposta:

- **Processos** (coordenam ciclo, abrem transação): `sales`, `orders` (absorve fulfillment e KDS),
  `delivery`, `production`, `procurement`, `closing`, `operations`.
- **Capacidades** (chamadas por processo): `payments`, `fiscal`, `catalog`, `availability`,
  `customers`, `identity`, `notifications`.
- **Canal:** `channels/ifood`. **Carregado como está:** `marketing` (cerca de 24% de
  `shop/services`).
- **Dependência:** surface → processo → capacidade → kernel. Processo não importa processo (fala
  por signal ou directive).

Onde o defeito "organizado pelo público da tela" está medido: `backstage/services` (domínio de
produção, compras, fechamento e catálogo morando na superfície; 604 imports backstage→kernels).
Em `shop` ele não existe: `shop→backstage` são 41 imports em 9 arquivos, todos em
`shopman/shop/adapters/`.

### 4.4 Projections, integrations e surfaces

- Projection: modelo de leitura, sem autoridade de escrita, nunca payload de comando.
- Integration: tradução para provedor externo, webhook e reconciliação.
- Surface: apresenta estado e envia intenção. **Só calcula como prévia declarada; todo valor que
  entra em comando é recalculado ou conferido pelo servidor.** A venda sem conexão do PDV é a
  exceção nomeada: calcula total e troco no cliente
  (`surfaces/pos-nuxt/app/presentation/offlineSales.ts`) e o servidor reconcilia
  (`shopman/shop/services/pos_offline_sale.py:1-40`).

## 5. O corte da tag

### 5.1 Antes da tag

| # | Item | Por que não pode esperar | Esforço (inferência) |
|---|---|---|---|
| 1 | Pacote de dias da D-038 | Já decidido | dias |
| 2 | `FiscalDocument` no fiscalman | Hoje a nota são chaves `nfce_*` em `Order.data`, um slot por pedido (`shopman/shop/handlers/fiscal.py:497-517,594-595`): rejeição, tentativa e segunda nota não têm registro. D-037 | 1,5 a 2 semanas |
| 3 | Carimbo dos fatos **com escritores**, nos caminhos de dinheiro e estoque (venda PDV, pagamento, recebimento, despacho) | Dispositivo/posto e correlação/causa são irrecuperáveis para todo fato gravado antes de o escritor preencher. Só criar a coluna não evita perda: `AddField` é livre depois da tag | depende do mapa de escritores |
| 4 | Manifesto cenário→teste, lacunas dos cenários 2, 3, 4 e 6, e os testes de corrida dentro do gate Postgres | Seção 7 | 3,5 a 4,5 dias, mais o que reprovar ao rodar |
| 5 | Guarda de imutabilidade do `OrderEvent` | É append-only só na docstring: sem guarda de `save`/`delete`, FK `CASCADE` (`packages/orderman/shopman/orderman/models/order.py:420-427`). Todo adiamento da seção 5.2 se apoia nele | horas |
| 6 | Recebimento: dedupe permanente, `source_ref` no `Move.metadata`, registro durável da recusa | `purchase.receipt` fora de `PERSISTENT_SCOPES` com validade de 24 h (`shopman/shop/services/remote_mutations.py:250`; `cleanup_idempotency_keys.py:19-36`); `source_ref` só nos 12 últimos caracteres de `reason` (`shopman/backstage/services/purchase.py:2463-2465`); recusa só cria Directive de notificação (`:516-596`) | horas a 1 dia |
| 7 | `RuleConfig.rule_path` no caminho final dos módulos de regra | Persiste caminho Python no banco (`shopman/shop/models/rules.py:28,75`); mover depois exige data migration | horas, se a decisão de caminho existir |

Itens 3 a 6 são a emenda que esta rodada propõe à D-038. **Pedem a palavra do dono.**

Estado da ficha em relação à tabela "Fundação transversal":

| Ledger | Ator | Idempotência | Dispositivo, correlação |
|---|---|---|---|
| stockman `Move` | FK `user` (`SET_NULL`, `move.py:84-89`) | nenhuma | nenhum |
| cashman `Entry` | FK `operator` e `approved_by` | constraints únicas | FK `shift`, `order_ref`, `payment_ref`, `parent` |
| payman `PaymentTransaction` | nenhum (`transaction.py:42-65`) | `idempotency_key` único | `gateway_id` |
| orderman `OrderEvent` | texto de 128 caracteres | nenhuma | `seq` por pedido |
| craftsman `WorkOrderEvent` | texto | `idempotency_key` | nenhum |
| orderman `Directive` | nenhum | `dedupe_key` | nenhum |

### 5.2 Depois da tag, uma fatia por vez

A ADR-015 não encarece nenhum destes: são tabela aditiva com backfill de um fato que já é durável,
ou movimento de pacote Python sem migration.

| Item | O fato já é durável hoje em | Perda real por esperar |
|---|---|---|
| `PurchaseReceipt` e `PurchaseOrder` em tabela | `Move kind=BUY` imutável por linha, com ator, fornecedor, chave da NF, custo (`purchase.py:327-349,2030-2068`; guardas em `move.py:13-26`) | Pedido de compra é apagado ao receber (`:1152-1166`). Aceitável se o item 6 da 5.1 entrar |
| `DeliveryRun` e custódia | `Order.data["courier"]` sob `select_for_update` com `OrderEvent` por transição (`shopman/shop/services/courier.py:951,978`); troco no livro do cashman (`cashman/models/entry.py:130-176`) | `driver` não é copiado para a tentativa arquivada (`courier.py:903-916`) |
| Revisão de pedido como entidade | `OrderEvent` por revisão com diff, settlement e `approved_by` (`shopman/shop/services/order_edit.py:1372-1397`) | Nenhuma identificada |
| Criar os módulos da 4.3 e mover arquivos | não muda autoridade de dado | Custo é de teste: 1.054 `patch("shopman...")` em 128 arquivos quebram por caminho |
| Taskman | seção 6 | Nenhuma |
| Saldo por pedido no payman, fila em pacote neutro, schema por loja | v2, seção 12 | Nenhuma |

Cada entidade nova nasce já no módulo destino. Não se cria no lugar velho para mover em seguida
(defeito de ordem da v3, Fase 3 antes da Fase 4).

### 5.3 Fora antes da tag

Mudança de `app_label` ou de permissão (o descritor de instância recria RBAC a cada release e um
erro derruba o deploy, `config/instance_descriptors.py:701-709`); corte de histórico de
migrations; `lock_timeout` global.

## 6. Taskman

**Recomendação: manter no Backstage, com gatilho de extração.**

O que existe (`shopman/backstage/models/operation.py`, `services/operations.py`,
`api/operation_checklists.py`): 5 models, cerca de 994 linhas Python, 8 testes Python e 8 de
superfície, um consumidor (`surfaces/orders-nuxt/pages/checklists.vue`). FK para fora só
`AUTH_USER_MODEL`. Nenhum import de kernel.

O que a descrição "proto-Taskman funcional" esconde:

- só `start_checklist_run` tem transação e lock (`services/operations.py:44-45`); as outras três
  funções não;
- "rotina encerrada não muda" mora na view (`api/operation_checklists.py:64`), não no serviço;
- `CANCELLED`, `SKIPPED` e `BLOCKED` não têm escritor;
- a dupla conferência aceita a mesma pessoa (`services/operations.py:124-133`;
  `test_operation_domain.py:107-119`);
- não há atribuição, prazo, recorrência, dependência nem agrupamento em projeto.

Pelo critério de domínio (pergunta, linguagem, lifecycle, invariantes, autoridade), passa como
domínio candidato, não como kernel maduro. A v2 errou ao condicionar a "segundo consumidor": essa
regra é de adapter, não de kernel. Extrair agora congela desenho imaturo em `packages/` e exige
troca de `app_label` e permissão.

**Gatilho:** primeira tarefa fora de checklist diário (atribuição ou prazo); primeiro escritor
fora do backstage; ou primeiro escritor de `linked_domain`/`linked_ref`.
**Antes da tag, sem mover nada:** levar a guarda de rotina encerrada para o serviço e decidir se
dupla conferência exige pessoa diferente (decisão de produto).

`Human`, `Assetman` e `Spendman`: mesmo rito, nenhuma evidência de código nesta rodada.

## 7. Cenários críticos

A suíte principal roda em SQLite (`config/settings.py:617-671`; `runtime-gate.yml:202-203`). Há um
gate em Postgres por lista fechada (`scripts/run_runtime_tests.py:30-150`, job
`runtime-security-reliability`).

| # | Cenário | Estado | Evidência | Falta |
|---|---|---|---|---|
| 1 | Pix confirmado depois do cancelamento | Coberto | `shopman/shop/tests/test_payment_webhooks.py:872,1495` | A corrida real existe e está fora do gate |
| 2 | Cartão recusado | Parcial, **mal enunciado** | Recusa só grava `payment.last_decline` (`shopman/shop/services/payment.py:1263-1287`); quem libera a reserva é o vencimento | Teste: recusa, vencimento, holds liberados |
| 3 | PDV com pagamento misto | Coberto no caminho feliz | `shopman/shop/tests/test_pos_cash_ledger.py:333,351,380,411` | Falha no livro com pagamento misto |
| 4 | Venda sem conexão reenviada | Coberto para pedido e caixa | `test_pos_venda_sem_conexao.py:103`; `test_pos_cash_ledger.py:892` (threads, Postgres) | Afirmar Move e diretiva fiscal únicos. Nasce desligada (`Shop.pos_offline_sale_enabled=False`) |
| 5 | `finish` simultâneo | Coberto, concorrência real | `test_concurrent_finish_does_not_double_credit.py:117` | nada |
| 6 | Cancelamento depois da baixa | Parcial | Pernas provadas em separado; orquestração só com mock (`test_lifecycle.py:826`) | Uma prova conjunta das quatro compensações |
| 7 | NF reescaneada | Coberto, sequencial | `shopman/backstage/tests/test_purchase_recibo_e_dinheiro.py:79` | Item 6 da seção 5.1 |
| 8 | Edição de encomenda | Coberto, funcional | `shopman/shop/tests/test_order_edit.py:156,253,296,327` | Sem teste com threads |

Enunciado corrigido do cenário 2: "pedido de cartão recusado e não repago libera a reserva no
vencimento".

**Cenário 9, proposto: toda corrida escrita roda no gate Postgres.** A catraca
`shopman/shop/tests/test_runtime_gate.py:33` só enxerga o marcador `requires_postgres`. 22
arquivos de teste usam skip inline (`if connection.vendor != "postgresql": pytest.skip`) e estão
fora da lista do gate. Entre eles `test_cancellation_fresh_state.py`,
`test_cod_custody_concurrency.py`, `test_pos_committed_sale_recovery.py`,
`test_h03_payment_guard_lock.py`. Se nenhum outro workflow os executa, são provas escritas que
não rodam. **Não verificado:** o que `omotenashi-gate.yml` e `orders-isolated-capacity.yml`
executam.

Já cobertos e fora da lista por isso: iFood duplicado (`test_ifood_lifecycle_e2e.py:178`,
`test_webhook_claim_race.py:34`) e NFC-e rejeitada (`test_fiscal_handlers.py:80-169`).

## 8. Superfícies

A rodada 1 da v2 inventariou 27 pontos em 11 apps, sem veredito. Uma amostra dirigida nesta
rodada não achou máquina de estados nem regra de preço duplicada em escala. Achou um defeito
candidato, independente do reset: o recibo do navegador no PDV grava
`discountPct: item.discount?.value` sem ler o tipo
(`surfaces/pos-nuxt/app/composables/usePosSale.ts:3806`) e aplica como percentual
(`presentation/receipt.ts:78-83`), mesmo quando o desconto é em reais. Não reproduzido em tela.

Menor auditoria necessária: tabela `campo do comando → origem (projection ou tela) → tratamento no
servidor (recalcula, confere e recusa, aceita calado)` para pos, storefront, orders, purchase,
production (`finish`, `close`) e kds (transições). 6 a 8 agente-horas. Corre em paralelo. Não é
pré-condição do desenho do backend; é pré-condição para estimar o movimento dos módulos.

## 9. ADR-001

- **Manter:** pureza e pontes (`:32-98`), teste signal × Protocol (`:142-154`), regra das duas
  implementações (`:178-180`).
- **Reescrever por estar velho:** `:11-14` (oito cores, são 13); `:107-119` (`CheckoutService`
  não existe); `:129-136` (`StockBackend`, `ContaazulBackend` não existem); `:157-165`
  (`PaymentBackend` vive em `packages/payman/shopman/payman/protocols.py:70`; o setting é
  `SHOPMAN_PAYMENT_ADAPTERS`); `:190-192` (falso hoje); `:209-214` (o teste está em
  `test_import_boundaries.py:451`).
- **Superar** `:203-205`, texto proposto:

> Substituir um kernel não é plug-and-play hoje, e isso é dívida medida, não escolha. A
> substituição é intenção de desenho: a escrita é fechada nos services do kernel, a leitura direta
> não cresce, e o contrato de cada kernel é uma suíte executável. Um provider não nativo só entra
> num ciclo cujas garantias ele satisfaz.

## 10. Textos propostos para o registro de decisões

São propostas. Só valem com a palavra do dono, como entrada nova que superseda a anterior.

**Para superseder a D-036:**

> **Substituibilidade de kernel é intenção de desenho, sem prazo.** O Shopman foi desenhado para
> que um domínio possa ser atendido pelo kernel nativo ou por outro sistema. Não é entrega datada,
> e nenhuma mudança pode torná-la mais cara. Consequência: (1) toda escrita em model de kernel
> passa pelos services do kernel, com gate; (2) a leitura direta de models de kernel pela
> aplicação não cresce; (3) as garantias de cada kernel viram suíte de contrato em Postgres; (4)
> os ciclos com transação local entre kernels ficam listados como "só nativo até redesenho"; (5)
> Protocol na frente de estoque, pedido, caixa ou pagamento só nasce com segunda implementação
> real.

**Para emendar a D-038:**

> **O corte da tag, emendado.** Critério único: segura a tag o que não se recupera depois dela e
> o que custa dias. Além do pacote de dias e do `FiscalDocument`: (a) o carimbo dos fatos passa a
> exigir os escritores de dispositivo e correlação nos caminhos de dinheiro e estoque, não só as
> colunas; (b) manifesto cenário→teste, lacunas dos cenários 2, 3, 4 e 6 e os testes de corrida
> dentro do gate Postgres; (c) guarda de imutabilidade do `OrderEvent`, `source_ref` no Move e
> registro durável da recusa de recebimento. Não seguem para a matriz: módulos por ciclo, Taskman,
> `PurchaseReceipt`, `DeliveryRun`, revisão de pedido. Gatilho de promoção: qualquer cenário ou
> escritor sem trava reproduzido com perda de dinheiro, estoque ou nota vira linha da matriz no
> mesmo dia.

## 11. Estimativas

| Estimável agora | Valor |
|---|---|
| Lacunas dos cenários, manifesto e catraca do gate | 3,5 a 4,5 dias |
| Reparos de recebimento e guarda do `OrderEvent` | horas a 1 dia |
| `FiscalDocument` | 1,5 a 2 semanas |
| Auditoria de superfícies | 6 a 8 agente-horas |

| Depende de medir primeiro | O que falta |
|---|---|
| Escritores do carimbo | mapa de escritores por caminho |
| O que reprova quando os 22 testes de corrida rodarem em Postgres | rodar |
| Movimento dos módulos | auditoria de superfícies e decisão de fronteiras |
| Latência e contenção | baseline p50/p95 |

Referência de vazão (30 dias, `git log --first-parent`): cerca de 550 PRs mergeados, perto de 3%
estruturais; o resto é correção e feature.

## 12. Divergências abertas entre Claude e Codex

É aqui que o terceiro agente mais ajuda. Para cada linha, diga quem tem razão e por quê.

| # | Tema | Codex (v3) | Claude (v4) |
|---|---|---|---|
| 1 | Critério do corte | Nenhum fato essencial nasce só em JSON genérico | Nenhum fato **irrecuperável** nasce sem registro durável; JSON com evento imutável é recuperável |
| 2 | `PurchaseReceipt`, `DeliveryRun`, revisão de pedido | Decidir e construir antes de dado real | Depois da tag; antes, só os reparos pequenos |
| 3 | Reorganização em módulos | Antes do go-live, é o motivo do reset | Depois; mover pacote Python não muda autoridade de dado |
| 4 | Estado da D-038 | Contestada até baseline | Decidida; emenda por entrada nova |
| 5 | D-036 | Substituibilidade como invariante | Intenção de desenho com catraca; "invariante" é falso contra quatro ciclos |
| 6 | Taskman | Avaliar extração agora | Adiar com gatilho |
| 7 | Estimativa | Nenhuma antes do baseline | Estimar o estimável, com teto |
| 8 | Oito cenários | Construir como gate bloqueante | Seis já bloqueiam; fechar quatro lacunas e o furo do gate |
| 9 | Auditoria de superfícies | Antes de aprovar o reset | Em paralelo; só bloqueia a estimativa do movimento |

## 13. Onde esta versão tem menos certeza

1. **Os 22 testes de corrida fora do gate.** A contagem foi reconferida; a conclusão "não rodam em
   lugar nenhum" não. Dois workflows com Postgres não foram inspecionados.
2. **Risco aceito dos escritores de `Order.data` sem lock** (v2: 12 pontos). Nenhum foi
   reproduzido com perda. Pode estar subestimado.
3. **"O `OrderEvent` preserva o fato"** sustenta o adiamento de três entidades. Se a guarda de
   imutabilidade não entrar antes da tag, o argumento cai.
4. **Tamanho do item 3 da seção 5.1** (escritores do carimbo). Sem mapa, pode ser de dias a
   semanas, e é o item que mais pode esticar o caminho até a tag.
5. **Classificação dos services por módulo** foi feita por nome de arquivo, não por leitura do
   conteúdo. Os 39% são ordem de grandeza.
6. **Contagens que não se reproduziram entre agentes:** ocorrências de `status ===` por app;
   número de arquivos em `shop/services` (177, um agente disse 189). As conclusões não dependem
   delas.
7. **`driver` consultável na Machine por `id_mch`** é inferência; a API não foi consultada.
8. **Agendamento de `cleanup_idempotency_keys` fora do repositório** não foi verificado; no
   repositório não há.
9. **Viés de autoria:** o coordenador desta versão escreveu a v2 e a D-038. As concessões da
   seção 5 foram feitas contra a própria v2, mas o corte continua mais perto dela que da v3.

## 14. Pedido ao terceiro agente

Trabalhe só em leitura sobre `origin/main`. Não escreva código, não altere documentos, não abra
nem mergeie PR. Cite `arquivo:linha` ou comando. Se puder executar testes num ambiente isolado,
diga exatamente o que rodou.

Responda:

1. O critério "irrecuperável ou custa dias" é o certo para o corte da tag? Há item da seção 5.2
   que na verdade se perde por esperar?
2. Há item da seção 5.1 que pode sair sem perda irrecuperável?
3. Os 22 testes de corrida rodam em algum workflow? Se puder, rode-os em Postgres e relate.
4. A guarda do `OrderEvent` basta para sustentar o adiamento de `DeliveryRun` e da revisão de
   pedido?
5. A lista "só nativo até redesenho" da seção 4.2 está completa?
6. O texto proposto para a D-036 honra "fiz desde o início pensando nisso" sem prometer o que o
   código não entrega?
7. A lista de módulos da seção 4.3 tem sobreposição ou buraco?
8. Taskman: o gatilho proposto é objetivo o bastante?
9. Em cada linha da seção 12, quem tem razão?
10. O que as três rodadas deixaram de olhar?

Classifique cada objeção como **BLOQUEANTE**, **CORREÇÃO OBRIGATÓRIA**, **MELHORIA** ou **SEM
FUNDAMENTO**, e termine com um veredito: **APROVAR V4**, **APROVAR V4 COM CORREÇÕES** (com o
texto exato) ou **REJEITAR V4** (com alternativa completa e menor).
