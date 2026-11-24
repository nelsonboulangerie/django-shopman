# COMERCIO-CONVERSACIONAL-ADAPTADOR-NICE-PLANO: a Nice sobre o framework, sem mover a Concierge

> **Estado:** plano de implementação. Nenhum código de produção neste PR.
> **Compromisso:** DEV-2026-045.
> **Deriva de:** `docs/research/INTELIGENCIA-COMERCIO-CONVERSACIONAL-v2.md`, seção 11 (o mapa do
> adaptador) e 15.7 (convivência), lida de `origin/claude/conversational-commerce-intelligence-eca993`
> enquanto o PR #2623 não estiver no `main`.
> **Irmão:** [COMERCIO-CONVERSACIONAL-FRAMEWORK-PLANO](COMERCIO-CONVERSACIONAL-FRAMEWORK-PLANO.md).
> As ondas dos dois estão juntas na seção 7 de lá. Os WPs F0 a F11 citados aqui são de lá.
> **Convive com:** [CONCIERGE-PLANO-DE-ACAO](CONCIERGE-PLANO-DE-ACAO.md), que segue vigente e não
> muda por causa deste plano.
> **Base:** `origin/main` em `032b74755` (17/11/2026). Toda evidência de código abaixo é desse
> commit.
>
> Legenda: **[MEDIDO]** saída de comando ou código com caminho; **[DECIDIDO]** decisão de
> engenharia fechada aqui; **[DIVERGE]** diferença com a v2, anotada (a v2 não se edita);
> **NÃO MEDIDO** quando não medi.

## 0. Em uma tela

- **O que é:** a implementação das portas do framework sobre o Shopman, mais o perfil da Nice.
  Não muda o núcleo para caber (v2 15.2) e não cria segundo livro de pedidos: `Session`,
  `Order`, pagamento e estoque continuam sendo a verdade; o framework guarda referência e
  evidência.
- **Primeiro passo no ar:** **N5, a decisão em sombra** (X1 da v2 11.5). A cada entrada, o
  framework decide em paralelo o que faria, sem enviar nada e sem escrever no comércio, e o
  registro é juntado depois com os pedidos do cliente em 24 horas e 7 dias. Cliente não vê;
  nenhuma chamada a modelo.
- **Os dois defeitos locais entram já, na onda 1:** N1 fecha a #2626 (modelo sem preço vira
  custo zero no placar) e N2 fecha a #2625 (posse não reconferida no instante do efeito, em
  quatro lugares, não dois).
- **Quanto:** 9 pacotes (N1 a N9). Com os 12 do framework, 21 pacotes em 10 ondas.
- **A Concierge não para:** os 16 WPs dela seguem. O adaptador lê a Concierge, não a reescreve,
  até o N9, que só começa depois do D1, do adaptador pronto, das duas decisões do dono e do
  WP-14 da Concierge no `main`.
- **Do dono:** as duas decisões que bloqueavam o N9 foram respondidas em 18/11 (seção 9): a Nice
  herda as três alçadas, só no WhatsApp, e quem estiver com o Gestor aberto assume pelo sino.

## 1. Mapa porta a porta, reconferido no código

A v2 11.1 foi escrita sobre `43eeeede4`. Reconferi cada linha em `032b74755` [MEDIDO, leitura
dos arquivos citados]. Onde mudou, a coluna "Reconferência" diz.

| Porta ou peça | O que existe | Reconferência | O adaptador faz | WP |
|---|---|---|---|---|
| **Canal** | `concierge/contracts.py` (`ChannelCapabilities`, `InboundEvent`, `WindowEvidence`, `ConversationAdapter`), `concierge/transport.py` (`ManyChatWhatsAppAdapter`, janela de 24 h, `supports_handoff=True`; `stable_event_identity_verified` e `delivery_receipts` vêm da opção da conexão) | Igual à v2. No alpha, `CONCIERGE_MANYCHAT_EVENT_ID_VERIFIED=false` (`.do/app.alpha-subdomains.yaml`): identidade do evento **não** verificada | Fachada `ChannelPort` sobre o `ConversationAdapter`; `capabilities()` traduz `ChannelCapabilities` | N4 |
| **Modelo** | `shopman/shop/ai.py` (`resolve`, `customer_text_approved`, `anthropic_client`, `jev_post`) e `shopman/shop/ai_governor.py` (`check`, `reserve`, `settle`, teto diário, registro) | **Mudou:** o freio e medidor que a v2 dá como "em andamento" entrou no `main` (#2316, 16/11). A porta está pronta | Fachada `ModelPort`: `interpret` pelo leitor local por regra (o "`--reader local`" do placar) e, quando houver chave, pela porta de IA com o governador; `draft` declarado indisponível (corte C1) | N4 |
| **Comércio, leitura** | Executores de leitura em `concierge/tools.py` sobre os services; `PromiseDecision` em `packages/stockman/shopman/stockman/protocols/sku.py` com `available_qty` factual, `orderable_ceiling` de política e `None` como "sem ledger", nunca "ilimitado" | Igual | `CommerceReadPort` em `shopman/shop/conversational/`, devolvendo `Fact` com fonte e validade; `promise()` preserva factual, esperado e planejado (não reduz a "disponível") | N4 |
| **Comércio, execução** | `place_order` com orçamento, confirmação posterior (`_confirmation`), `quote_token`, revisão esperada e `run_idempotent_mutation` (`shopman/shop/services/remote_mutations.py`); `discount._grant`; `cancellation._execute`; `order_addition.apply` | Igual, e o defeito A1 é **maior** que na v2 (seção 6) | `CommerceExecutePort` que embrulha os quatro efeitos com a `EffectGuard` dentro da unidade atômica; `locate` e `reconcile` sobre `remote_mutations.lookup_idempotent_mutation` | N2, N6 |
| **Equipe** | `concierge/handoff.py`; `service.mark_handoff` e `return_to_concierge`; `OperatorAlert` com `acknowledged_by`, `resolved_by`, `respond_by` (`shopman/backstage/models/alerts.py`); "vou verificar" planejado (Concierge WP-05 a WP-07, WP-15) | Igual; nenhum `concierge_verify` no `main` ainda | `StaffPort` sobre o cartão do sino e o "vou verificar" quando a Concierge os entregar | N7 |
| **Entender** | `concierge/intents.py`: atos no plural, validação em código, regra local que soma | Igual; o WP-03 da Concierge (#2605, aberto) mexe aqui | Traduz a leitura para `Understanding`, com `confidence: Unavailable(no_calibration)` até a calibração (X2) | N4, N5 |
| **Estado e posse** | `concierge/dialogue.py` em `Conversation.flags["dialogue"]`; `Conversation.turn_fence` (`shopman/shop/models/concierge.py`); `service.assert_turn_authority` | Igual. **Atenção:** `turn_fence` sobe com fala nova **e** com transferência (`mark_handoff` faz `turn_fence += 1` sob `select_for_update`). É a versão do episódio e a época de posse num contador só | Mapeia os dois conceitos do framework para o mesmo `turn_fence`. É mais estrito que o núcleo pede (fala nova também revoga), portanto seguro. [DIVERGE] anotado no `spec` do adaptador | N4 |
| **Regras da casa e verificação de saída** | `concierge/house_rules.py`: `RULES` com R1 a R14, exemplos que são testes, efeitos de reparo e retenção | Igual | As 14 regras entram no perfil da Nice como referência (`house_rules_ref`), não são copiadas para o núcleo | N3 |
| **Dizer** | Frase da casa por molde; o modelo não reescreve (dono, 16/11, corte C1) | Igual | Moldes da Nice como implementação da parte "molde" do `ReplyPlan` | N9 |
| **Exposição** | `OutboundAttempt` só de acréscimo, estados `executing`, `accepted`, `not_applied`, `unknown`, `delivered`, `read` | Igual. Casa um a um com `ExposureEvent` (`executing` = `submitted`; `prepared` é a `ConversationMessage` antes da tentativa) | Liga a exposição à decisão (`decision_id` no envelope) | N8 |
| **Régua** | `golden_set.json` (221 casos), `golden_memory.json` (47), `concierge_reply_eval`, `metrics.py`; placar com `--paid` e teto em PR (#2516, WP-02) | Igual; 221 conferido | Não muda. É a régua de não regressão do N9 | N9 |
| **Decidir** | Não existe como peça; o destino sai de regras encadeadas | Igual | Em sombra (N5), depois no turno (N9) | N5, N9 |
| **Registro de decisão** | Não existe; há `ConversationMessage.usage` | Igual | Tabela só de acréscimo no app `shop` | N5 |
| **Compromissos** | Só o embrião planejado | Igual | Sobre o "vou verificar" | N7 |
| **Junção com resultado** | Não existe | Igual | Junção conversa → pedido em 24 h e 7 dias, só telemetria | N5 |

### 1.1 Onde o adaptador mora [DECIDIDO]

| O quê | Onde | Motivo |
|---|---|---|
| Portas de negócio genéricas do Shopman: comércio (leitura e execução), armazenamento, relógio, resultados | `shopman/shop/conversational/` | São do Shopman, não da Nice: qualquer superfície conversacional futura usa as mesmas. `storefront` importa `shop`, nunca o contrário (regra de dependência do `CLAUDE.md`) |
| Tabelas do registro (decisão, episódio, recibo, exposição ligada) | `shopman/shop/models/conversational.py`, migração no app `shop` | Orquestrador, não Core: nenhum campo novo em `packages/` |
| Porta de canal, porta de modelo, perfil da Nice, sombra | `shopman/storefront/concierge/` | São da Nice e do canal dela |
| Valores do perfil | Os que já existem no `ChannelConfig` e na `Shop`, lidos pelo acessor que já os lê (`service.config()`, `ChannelConfig`) | ADR-042: configuração de loja não entra por env nem por `settings`. Ler `settings.SHOPMAN_*` num arquivo novo reprova `scripts/check_tenant_config.py` |
| Estado das linhas do perfil (dono, data, estado) | Arquivo revisado em código, `concierge/profile_lines.py` | Linha de alçada não se edita em painel (v2 9.1): muda por revisão e teste. O **valor** (o teto, por exemplo) continua editável no Admin |

## 2. Perfil de implantação da Nice, linha por linha

Regra única (v2 5.8): linha sem decisão fica ausente, com motivo, e a ação que depende dela
fica inelegível com código. O perfil **descreve** o que a Nice faz hoje; enquanto a Nice não
roda sobre o framework (até o N9), ele governa só a sombra. "Vigente" quer dizer que o
comportamento existe hoje no código legado; "aprovado" quer dizer que a linha vale para o
framework.

| ID | Linha | Valor hoje (fonte) | Dono | Estado |
|---|---|---|---|---|
| P01 | Inquilino e ambiente | Nelson; `shadow` no N5, `live` só no N9 | Engenharia | aprovado |
| P02 | Canal e capacidades | WhatsApp pelo ManyChat; janela de 24 h com prova; identidade do evento não verificada (`CONCIERGE_MANYCHAT_EVENT_ID_VERIFIED=false`) | Engenharia | aprovado |
| P03 | Identidade por canal | Telefone do WhatsApp = `transported`; vínculo verificado de cliente = `weak_verified`, desligado no alpha (`CONCIERGE_IDENTITY_LINK_ENABLED=false`) | Engenharia | aprovado |
| P04 | Leitor e modelo | Regra local primeiro; Jev no porteiro e DeepSeek na extração, só texto redigido, só conexão `customer_text_approved` | Dono (16/11, D-040) | aprovado |
| P05 | Gasto com modelo | Freio e teto diário do `ai_governor` | Dono (D-039, item 5) | aprovado |
| P06 | Regras da casa | `house_rules.RULES`, R1 a R14 | Dono (OBS0310-M, #1442) | aprovado |
| P07 | Movimentos ligados | `acknowledge`, `inform`, `cover_readings`, `inform_limitation`, `ask_clarification`, `handoff`; `verify_with_staff` quando o WP-05 da Concierge entrar | Dono (comportamento atual) | aprovado |
| P08 | Pedido na conversa (`present_terms`, `change_cart`, `commit_order`) | Pedido pelo dono em 16/11 (DEV-2026-027); construído nos WP-11 a WP-14 da Concierge | Dono | em validação até o WP-14 |
| P09 | **Desconto com teto** (`grant_discount`, A4) | Teto do `ChannelConfig.pricing.concierge_discount_max_percent` (padrão 2,5 no código; valor do alpha NÃO MEDIDO, o N3 mede pela 25060); um cupom por pedido; só no WhatsApp | Dono (OBS0310-O, #1444) | aprovado (dono, 18/11, decisão 1) |
| P10 | **Cancelamento em autoatendimento** (`cancel_order`, A3) | Só quando o próprio cliente poderia cancelar pelo site (`customer_orders.can_cancel`: preparo não começado), com confirmação de uma linha | Dono (OBS0310-O, #1445) | aprovado (dono, 18/11, decisão 1) |
| P11 | **Acréscimo a pedido feito** (`amend_order`, A3) | Só aumento, pelo `order_edit` do balcão: até "em preparo", sem NFC-e autorizada, fora do iFood | Dono (OBS0310-P, #1450) | aprovado (dono, 18/11, decisão 1) |
| P12 | Compensação | Nenhuma alçada | Dono (Q4) | ausente: só com pessoa |
| P13 | Recomendação (`recommend`) | Não existe | Dono (15.5, movimentos comerciais) | ausente: a sombra calcula a candidata, nada sai |
| P14 | Fontes de fato | Preço do canal (Offerman), promessa (Stockman, `PromiseDecision`), pedido (Orderman), horário e calendário (`Shop`), alérgenos (`concierge/allergens.py`); lidos ao vivo, valem para o turno | Engenharia | aprovado |
| P15 | Fila humana | Sino do Gestor (`OperatorAlert`), prazos 10 e 30 min no `ChannelConfig` (dono, 16/11); fora do expediente a Nice diz quando a equipe atende; aceite nominal: quem estiver com o Gestor aberto assume pelo sino, com nome, em até 10 min no expediente; fora dele a Nice não muda nada sozinha | Dono (16/11 e 18/11, decisão 2) | aprovado |
| P16 | Tetos do turno | `MAX_LOOPS` do `handler.py` (caminho de hoje), `MAX_READS_PER_TURN` do `concierge/profile.py` (leituras do motor, 20; 24/11, #3482), `claim_until`, teto do `ai_governor` | Engenharia | aprovado |
| P17 | Privacidade | Texto redigido (WP-03), `sensitive` nunca sai, nome e endereço não saem (WP-08), `/privacidade` declara quem recebe (WP-10), observação com 7 dias de retenção | Dono (D-039, D-040) | aprovado |
| P18 | Memória além do episódio | Só memória declarada | Dono (Q6) | ausente |
| P19 | Desfecho e janela | Só telemetria, nenhuma alegação de eficácia | Dono (Q1) | ausente |
| P20 | Sorteio de oferta | Nenhum | Dono (Q8) | ausente |
| P21 | Modo do app vivo | `CONCIERGE_READ_ONLY=true`, `assist`, coorte de um contato, transferência e devolução desligadas | Dono | vigente |

As três alçadas que já existem (P09 a P11) **não somem e não crescem em silêncio** (v2 11.3):
no legado seguem como estão, e no framework entram como aprovadas, só no WhatsApp, com os
mesmos limites (decisão 1, 18/11). O teto que o código traz como padrão não é, por estar no código,
política aprovada.

## 3. Convivência com os WPs em voo da Concierge (v2 15.7)

Estado em 17/11 [MEDIDO, `gh pr list`, `git worktree list`]:

| WP da Concierge | Estado | Arquivos que tocam este plano |
|---|---|---|
| WP-01 freio | **no `main`** (#2316) | nenhum conflito |
| WP-02 régua | PR #2516 aberto, verde | `reply_eval.py`, comando do placar |
| WP-03 sem chave, redigido | PR #2605 aberto | `service.py`, `intents.py`, `dialogue.py`, `observation_privacy.py` |
| WP-04 equipe pela regra | PR #2602 aberto | `handoff.py`, `house_rules.py`, `triage.py` |
| WP-10 privacidade | PR #2520 draft, 5 checks vermelhos | `privacy_inventory.py` |
| WP-05 a WP-16 | não começados | `service.py`, `intents.py`, `dialogue.py`, `tools.py`, `handler.py`, `maintenance_worker.py`, entre outros |

Regras [DECIDIDO]:

1. **Até o N9, o adaptador não edita `service.py`, `intents.py`, `dialogue.py` nem
   `house_rules.py`.** Lê e importa; não muda. É a forma concreta de "não mover a Concierge
   enquanto as portas mudam".
2. **N2 toca `tools.py`, `discount.py`, `cancellation.py` e `order_addition.py`.** Nenhum PR em
   voo toca esses arquivos hoje. `tools.py` é do WP-08 e do WP-11 da Concierge (ondas 4 e 5 de
   lá): o N2 entra antes, e quem pegar o WP-08 parte do `main` com o N2 dentro.
3. **N5 toca uma linha de `shopman/shop/management/commands/maintenance_worker.py`**, que o WP-06
   da Concierge também toca. Os dois nunca correm juntos: quem começa depois confere `gh pr
   list` e espera o outro entrar.
4. **N7 só começa com os WP-05, WP-06 e WP-07 da Concierge no `main`.** O "vou verificar" é
   comportamento da Concierge; o N7 só o embrulha como porta de equipe (v2 15.7, item i: os WPs
   entregam comportamento que o adaptador depois embrulha).
5. **N9 só começa com o WP-14 da Concierge no `main`**, quando `service.py` para de mudar por
   causa do pedido na conversa, e com o D1 pronto (v2 15.7, item iii).
6. A1 vira requisito dos WPs de pedido na conversa (v2 15.7, item i): o WP-11 parte do N2 e
   roda as provas dele; nenhum WP de pedido enfraquece a guarda que o N2 põe.

## 4. Onde entram as issues #2625 e #2626

| Issue | WP | Por que agora |
|---|---|---|
| #2626, placar trata modelo sem preço como custo zero (A2) | **N1**, onda 1 | Correção pequena e avulsa (v2 15.7, item ii). Não colide mais com o WP-01, que já entrou. O `ai_governor.prices_for` do `main` já devolve `(preços, conhecido)`: o N1 usa a mesma distinção em vez de inventar outra |
| #2625, posse não reconferida no instante do efeito (A1) | **N2**, onda 1 | O risco está latente (o app vivo é só leitura), mas os arquivos estão livres hoje e ficam disputados a partir da onda 4 da Concierge. Corrigir antes custa menos que corrigir dentro do WP-11 |

## 5. O defeito A1 é maior que na v2 [DIVERGE]

A v2 11.2 aponta dois lugares (pedido e desconto). Reconferindo em `032b74755`, são quatro, e a
#2625 já os lista no "pronto quando":

| Efeito | Onde confere | Onde grava | Problema |
|---|---|---|---|
| Pedido | `tools.py:1353`, dentro do `atomic` com conversa e sacola travadas | `checkout_service.process` em `tools.py:1395`, **depois** de o `atomic` fechar | A conferência e o efeito estão em unidades diferentes |
| Desconto | não confere | `discount.py:170`, `_grant` abre o próprio `atomic` | Não reconfere a posse em lugar nenhum |
| Cancelamento | `cancellation.py:244`, fora de transação e sem trava da conversa | `cancellation.py:258`, `atomic` do `customer_orders.cancel` | Confere, solta, depois grava |
| Acréscimo | `order_addition.py:333`, fora de transação e sem trava | `order_edit.edit` adiante | Idem |

A correção que respeita o contrato (v2 4.7, propriedade 4): travar a linha da conversa com
`select_for_update` **na mesma transação do efeito** e reconferir ali. Funciona porque
`service.mark_handoff` também trava a mesma linha antes de subir o `turn_fence`: com as duas
travando, a transferência e o efeito ficam linearizados. No pedido, o efeito local nasce dentro
de `checkout_service.process`, que depois dispara efeitos de rede (Pix); a guarda precisa
entrar **dentro** da unidade atômica do commit da sessão, nunca envolvendo a chamada de rede.

## 6. O primeiro passo no ar: decisão em sombra (N5, X1)

**O que roda.** Uma varredura periódica (um comando, chamado pelo `maintenance_worker`) pega as
entradas novas desde o último cursor: as da coorte atendida e as observadas passivamente
(`CONCIERGE_OBSERVATION_ENABLED=true`, todos os assuntos, 7 dias de retenção). Para cada uma,
monta o `ContextSnapshot` pelas portas de leitura (N4), lê pelo leitor local (sem modelo), roda
o `decide()` do framework (F5) com o perfil da Nice (N3) em `environment=shadow` e grava o
`DecisionRecord`. Uma segunda passada junta, por cliente identificado, pedidos em 24 horas e em
7 dias (`OutcomeEvent` com `censored` enquanto a janela não fecha).

**Por que varredura e não gancho no turno** [DECIDIDO]: o gancho exigiria editar `service.py`
ou `handler.py`, que a Concierge mexe em quase toda onda; e uma falha da sombra nunca pode
atrasar nem derrubar um turno vivo. O custo é o atraso: os fatos são lidos alguns minutos depois
da entrada, e cada fato grava `observed_at`, então o atraso aparece no registro em vez de se
esconder. [DIVERGE] A v2 diz "em cada turno"; aqui é "a cada entrada, logo depois".

**O que não faz.** Nenhuma chamada às portas de escrita, nenhum envio (K36 no mecanismo real),
nenhuma chamada a modelo, nenhum texto do cliente no registro (só referência, atos, movimentos,
códigos de bloqueio e hashes). O que deriva de entrada observada é apagado junto com ela
(`service.purge_observations`).

**O que responde em duas semanas.** Quantas entradas por dia o framework veria; o que ele
proporia contra o que a Nice fez na coorte (resposta, transferência, "não sei"); quantas vezes
uma ação ficou inelegível e por qual linha do perfil; quanto de fato ficou `Unknown` e de qual
fonte; e se o `DecisionRecord` basta para explicar cada proposta (o teste da cintura fina).

**Ligar no alpha.** O `main` é o deploy; a varredura nasce desligada por um campo da `Shop`
(ADR-042, sem env) e o N5 liga o campo no alpha depois do deploy, relatando no PR a primeira
passada. Não muda nada para o cliente e não gasta modelo, por isso não pede a palavra do dono
(mecânica de engenharia, `CLAUDE.md`).

## 7. Pacotes de trabalho

Tamanho e brief comum como no plano irmão (seção 4 de lá). A mais, para todo N: o banco do
alpha só se lê, e só pela conexão direta 25060; prova de concorrência roda no Postgres pelo
`make test-runtime`, com o arquivo novo acrescentado em `scripts/run_runtime_tests.py`
(sem esse passo, o teste pula em SQLite e não prova nada).

### N1 · Placar: modelo sem preço não é custo zero (#2626)

- **Objetivo:** preço ausente fica explícito no placar e veta conclusão econômica.
- **Depende de:** nada.
- **Arquivos:** `shopman/storefront/concierge/intent_benchmark.py` (`prices_for`),
  `shopman/storefront/concierge/intent_pilot.py` (o `_unpriced` descartado),
  `shopman/storefront/tests/test_intent_pilot.py`.
- **Fora do escopo:** `ai_governor.py` (só reusa); `reply_eval.py` (WP-02).
- **Pronto quando:** `pytest shopman/storefront/tests/test_intent_pilot.py` verde com o teste
  K34 nomeado: modelo sem preço aparece como "custo desconhecido", a lista de modelos sem preço
  sai no relatório, e o placar recusa comparar custo enquanto houver um. Fecha a #2626.
- **Cliente vê:** não. **Tamanho:** P.

### N2 · Posse reconferida no instante do efeito (#2625)

- **Objetivo:** nenhum efeito local nasce de comando cuja posse mudou, nos quatro efeitos da
  seção 5.
- **Depende de:** nada.
- **Arquivos:** `shopman/storefront/concierge/tools.py` (`place_order.commit_local`),
  `discount.py` (`_grant`), `cancellation.py` (`_execute`), `order_addition.py` (`apply`),
  `shopman/shop/services/checkout.py` se a guarda precisar de um ponto dentro do commit,
  `shopman/storefront/tests/test_concierge_posse_no_efeito.py` (novo),
  `scripts/run_runtime_tests.py`.
- **Fora do escopo:** `service.py` (trava na linha da conversa no chamador, não muda
  `assert_turn_authority`); `packages/` (se a única unidade atômica for do Core, para e escreve
  no PR); ligar escrita no app vivo.
- **Pronto quando:** `make test-runtime` verde com o arquivo novo: para cada um dos quatro
  efeitos, uma barreira (`threading.Event`, como em `test_concierge_commercial_races.py`)
  exatamente entre a conferência e a gravação, uma transferência para a equipe concorrendo, e a
  prova de que **nenhum efeito local** nasce (K11), mais o caso inverso: transferência depois da
  submissão é reconciliada sem promessa de desfazer (K12). As quatro suítes de corrida que já
  existem seguem verdes. Fecha a #2625.
- **Cliente vê:** não. **Tamanho:** G.

### N3 · Perfil da Nice

- **Objetivo:** o `DeploymentProfile` da Nice, com as 21 linhas da seção 2, dono e estado,
  montado a partir dos valores que já existem.
- **Depende de:** F2.
- **Arquivos:** `shopman/storefront/concierge/profile.py` (novo),
  `shopman/storefront/concierge/profile_lines.py` (novo),
  `shopman/storefront/tests/test_concierge_profile.py` (novo).
- **Fora do escopo:** mudar qualquer valor; ler `settings` direto (ADR-042).
- **Pronto quando:** `pytest shopman/storefront/tests/test_concierge_profile.py` verde com:
  o perfil valida pelo contrato estrito do framework; K39 no perfil real (P09 a P13 tornam as
  ações inelegíveis com o código da linha, e `inform_limitation` e `handoff` seguem
  admissíveis); o teto do desconto vem do `ChannelConfig`, nunca de constante. O PR traz o
  valor do teto no alpha, lido pela 25060 em transação somente leitura.
- **Cliente vê:** não. **Tamanho:** M.

### N4 · Portas de leitura sobre o Shopman

- **Objetivo:** `ChannelPort`, `ModelPort` (leitor local) e `CommerceReadPort` sobre o que
  existe, passando a parte da suíte de conformidade que cabe a portas de leitura.
- **Depende de:** F3.
- **Arquivos:** `shopman/shop/conversational/__init__.py`, `commerce_read.py` (novos),
  `shopman/storefront/concierge/ports.py` (novo: canal e modelo),
  `shopman/shop/tests/test_conversational_read_ports.py` (novo).
- **Fora do escopo:** escrita (N6); armazenamento (N8); qualquer chamada paga.
- **Pronto quando:** `pytest shopman/shop/tests/test_conversational_read_ports.py` verde rodando
  os testes de forma de porta do framework com um *harness* do Shopman: K04 (fonte que falha
  vira `Unknown`, nunca valor velho), `promise()` devolve factual, esperado e planejado
  separados, e `capabilities()` do canal reflete a conexão (identidade do evento não
  verificada no alpha).
- **Cliente vê:** não. **Tamanho:** G.

### N5 · Decisão em sombra (X1), o primeiro passo no ar

- **Objetivo:** a seção 6, no ar no alpha, desligável por campo da `Shop`.
- **Depende de:** F5, N3, N4.
- **Arquivos:** `shopman/shop/models/conversational.py` (novo: registro de decisão e de
  resultado, só acréscimo) e a migração no app `shop` (confira número repetido antes do PR),
  `shopman/shop/models/shop.py` (o campo que liga), `shopman/shop/conversational/decision_store.py`,
  `shopman/storefront/concierge/shadow.py` (novo),
  `shopman/storefront/management/commands/concierge_shadow_decisions.py` (novo: varredura e
  junção), uma linha em `shopman/shop/management/commands/maintenance_worker.py`, o Admin só de
  leitura do registro, `docs/reference/commands.md`, `docs/reference/data-schemas.md` (aponta
  para o contrato do framework, não o redefine),
  `shopman/storefront/tests/test_concierge_shadow.py` (novo).
- **Fora do escopo:** `service.py`, `handler.py`, `intents.py`; qualquer envio; qualquer
  modelo; alegação de eficácia.
- **Pronto quando:** `pytest shopman/storefront/tests/test_concierge_shadow.py` verde com: K36
  (em sombra, nenhuma chamada às portas de escrita nem envio, provado com espiões nas portas
  reais); a mesma entrada varrida duas vezes grava um registro (K01); o registro não tem texto
  do cliente; derivado de observação some no `purge_observations`; janela não fechada grava
  `censored` (K33). Depois do deploy, o PR traz a primeira passada no alpha (quantas entradas,
  quantas decisões, quantas inelegíveis e por qual linha).
- **Cliente vê:** não. **Tamanho:** G.

### N6 · Executor do contrato de efeito sobre o Shopman

- **Objetivo:** `CommerceExecutePort` embrulhando pedido, desconto, cancelamento e acréscimo com
  a `EffectGuard`, mais `locate` e `reconcile`, provados no Postgres.
- **Depende de:** F8, N2.
- **Arquivos:** `shopman/shop/conversational/commerce_execute.py` (novo),
  `shopman/shop/tests/test_conversational_execute_postgres.py` (novo),
  `scripts/run_runtime_tests.py`.
- **Fora do escopo:** ligar o executor no turno da Nice (N9); editar `tools.py` (chama os
  executores, não muda).
- **Pronto quando:** `make test-runtime` verde com o arquivo novo rodando, no Postgres, K08,
  K09, K10, K11, K12, K14, K15 e K16 da suíte de conformidade; o executor que pula a guarda
  reprova K11.
- **Cliente vê:** não. **Tamanho:** G.

### N7 · Porta de equipe sobre o "vou verificar"

- **Objetivo:** `StaffPort` sobre o cartão `concierge_verify` e os prazos da Concierge, com
  promessa, aceite nominal, cumprimento e reabertura.
- **Depende de:** F9; WP-05, WP-06 e WP-07 da Concierge no `main`. O aceite nominal segue a
  decisão 2 (18/11).
- **Arquivos:** `shopman/shop/conversational/staff.py` (novo),
  `shopman/shop/tests/test_conversational_staff.py` (novo).
- **Fora do escopo:** a tela do sino (WP-07); os prazos (WP-06).
- **Pronto quando:** `pytest shopman/shop/tests/test_conversational_staff.py` verde com K20
  (fila que não aceita: compromisso monitorado, nada afirma aceite) e K22 (prazo vencido escala
  e avisa o cliente uma vez) sobre o `OperatorAlert` real.
- **Cliente vê:** não. **Tamanho:** M.

### N8 · Armazenamento, relógio e resultados; o adaptador pronto

- **Objetivo:** `StorePort`, `ClockPort` e `OutcomesPort` sobre Django, Directive e Orderman, e
  a suíte de conformidade inteira rodando com o *harness* do Shopman.
- **Depende de:** F11, N5, N6.
- **Arquivos:** `shopman/shop/conversational/store.py`, `clock.py`, `outcomes.py`,
  `harness.py` (novos), `shopman/shop/models/conversational.py` (episódio e recibo) e a
  migração, `shopman/shop/tests/test_conversational_conformance.py` (novo),
  `scripts/run_runtime_tests.py`.
- **Fora do escopo:** ligar o framework no turno vivo.
- **Pronto quando:** `make test-runtime` verde com a suíte de conformidade inteira no Postgres,
  sem pulo; K13 rodado com dois trabalhadores reais sobre a mesma versão do episódio; a matriz
  do adaptador mostra K11 a K14 provados no mecanismo real. É o critério de saída do D2 (v2 10)
  e o "pronto" do adaptador (seção 8).
- **Cliente vê:** não. **Tamanho:** G.

### N9 · A Nice dentro do framework, atrás de chave

- **Objetivo:** o turno da Nice passa a ser o `engine.turn()` do framework com as portas do
  Shopman, por classe de ação, com o caminho legado como queda, sem mudar o que o cliente lê.
- **Depende de:** F11, N7, N8; WP-14 da Concierge no `main` (as decisões 1 e 2 do dono já
  foram dadas em 18/11).
- **Arquivos:** `shopman/storefront/concierge/service.py` (o ponto de troca, um só),
  `shopman/storefront/concierge/turn_framework.py` (novo), `profile_lines.py` (estados das
  linhas aprovadas), testes de não regressão. A sessão escreve no PR, antes de codar, a lista
  final; se passar de uma sessão, publica a divisão em PR draft e para.
- **Fora do escopo:** movimento novo (recomendação, compensação); redação por modelo; abrir
  para mais clientes.
- **Pronto quando:** o placar gratuito (`concierge_reply_eval`, 221 e 47 casos) sem regressão
  com a chave ligada e desligada; as suítes de corrida da Concierge verdes; o mesmo turno
  reexecutado dá a mesma decisão (K40) sobre conversas gravadas da coorte; o freio por classe
  de ação desliga a escrita em minutos e mantém informar e encaminhar.
- **Cliente vê:** não deveria; se a frase mudar, o PR fica em draft com a prévia e a pergunta.
  **Tamanho:** G.

## 8. Pronto do adaptador

Pela v2 15.2: a suíte comum passa **e** as provas de concorrência e reconciliação rodam no
mecanismo real. Aqui, isso é o N8 no `main`:

```bash
make test-runtime
```

com `test_conversational_conformance.py`, `test_conversational_execute_postgres.py` e
`test_concierge_posse_no_efeito.py` na lista do runtime e nenhum K pulado. Recua (v2 10) se o
adaptador precisar mudar o núcleo: aí o PR do adaptador para e abre a mudança no framework como
WP próprio.

## 9. Decisões do dono

Das oito de v2 15.5, só duas bloqueavam um pacote deste plano, e as duas bloqueavam o N9. As
outras seis têm padrão seguro que o plano já usa (seção 2: linha ausente, ação desligada) e não
travam nada até o D3.

**Respondidas em 18/11/2026** (pela coordenação; registro no comentário do dono no PR #2632):

| # | Pergunta | Resposta | O que mudou |
|---|---|---|---|
| 1 | A Nice herda, no framework, as três alçadas que já tem? | Sim, como estão hoje, só no WhatsApp: desconto até o teto do Admin, cancelamento só quando a própria cliente poderia cancelar pelo site, acréscimo só até "em preparo" | P09, P10 e P11 aprovadas. Ampliar para outro canal é pergunta nova |
| 2 | Quem assume o que a Nice passa para a equipe? | Quem estiver com o Gestor aberto assume pelo sino, com nome; 10 minutos para alguém assumir no expediente; fora do expediente a Nice não muda nada sozinha e diz quando a equipe volta | P15 aprovada com o aceite nominal. O N9 deixa de esperar o dono e segue esperando o D1, o N8 e o WP-14 da Concierge |

## 10. Fora deste plano

Experimentos X2 a X6 da v2 11.5 (calibração do leitor com chamada paga, oferecer para separar,
substituto na indisponibilidade, controle permanente) e os degraus D3 a D7 depois do N9 ficam
para um plano que nasce quando o N8 e o N5 tiverem duas semanas de registro. Rastreado na
issue #2631 (`ficou-de-fora`). O X3 (compromissos sobre o "vou verificar") não fica de
fora: é o N7.

## 11. Arquivos lidos

Em `032b74755`: `shopman/storefront/concierge/` (`contracts.py`, `transport.py`, `tools.py`
linhas 1191 a 1430, `discount.py`, `cancellation.py`, `order_addition.py`, `service.py`
(`_observed`, `assert_turn_authority`, `mark_handoff`, a lista de funções), `handler.py`,
`house_rules.py` (`RULES`), `intent_benchmark.py`, `intent_pilot.py`, `golden_set.json`
(contagem)); `shopman/shop/ai.py`, `shopman/shop/ai_governor.py`,
`shopman/shop/services/remote_mutations.py`, `shopman/shop/services/checkout.py` (`process`),
`shopman/shop/services/observability.py`, `shopman/shop/models/concierge.py`
(`Conversation`, `OutboundAttempt`), `shopman/backstage/models/alerts.py`,
`shopman/shop/config.py` (teto do desconto), `shopman/shop/management/commands/maintenance_worker.py`,
`packages/stockman/shopman/stockman/protocols/sku.py` (`PromiseDecision`),
`shopman/storefront/tests/test_concierge_privacy_postgres.py`,
`shopman/storefront/tests/test_concierge_commercial_races.py`, `scripts/run_runtime_tests.py`,
`.do/app.alpha-subdomains.yaml` (bloco da Concierge). PRs #2316, #2516, #2520, #2602, #2605,
#2623 e issues #2625 e #2626 por `gh`. Banco do alpha: não consultado nesta sessão.
