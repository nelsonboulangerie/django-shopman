# Ensaio da Concierge: placar com modelo (WP-09)

O WP-09 de `docs/plans/CONCIERGE-PLANO-DE-ACAO.md`: a leitura das partes com modelo,
`deepseek-flash` e `deepseek-v4-pro` lado a lado na rota `intents`, com o Jev no porteiro,
contra o conjunto de mensagens reais (`concierge/golden_set.json`). Autorização do dono:
D-040 (mensagem redigida à DeepSeek e ao Jev, rodada de até US$ 2 no total).

> **Estado:** RASCUNHO. Os placares pagos rodam no console do `maintenance-worker` de
> produção (a coordenação opera, o dono fez o login); as seções marcadas PENDENTE recebem
> a saída literal dos comandos quando ela chegar.

## Como foi medido

- **Onde:** console do `maintenance-worker` em produção, porque as chaves da DeepSeek e do
  Jev só existem no `AIConnection` de lá (nenhuma chave foi copiada para outro lugar).
- **Modelo por rodada:** trocado SÓ dentro do processo do comando (`ai._route` em
  memória). A rota de produção (`{"default": {"connection": "deepseek"}}`) não mudou, e
  a Concierge viva seguiu no modelo dela.
- **Jev no porteiro:** as notas que o Jev deu em sombra no alpha, gravadas em cada caso do
  conjunto (`alpha.jev_scores`). Nenhuma chamada nova ao Jev.
- **Gasto:** cada chamada passou pelo freio e pelo medidor de produção
  (`ai_governor.metered`: `AiInvocation` sem texto e `AiSpendDay`). O teto de cada rodada
  é o `--budget-usd` (tabela `LLM_PRICES`, preço de pico).
- **O que não fez:** não escreveu em dado de cliente nem mandou mensagem. O
  `concierge_check --live` só lê os campos do ManyChat (`getCustomFields`).

## Antes de gastar (passo 0, 20/11/2026 ~21h05Z)

```text
freio Limits(enabled=True, shop_usd_per_day=3.0, purposes={})
rotas {'default': {'connection': 'deepseek'}}
hoje [{'scope': 'decision', 'calls': 7, 'spent_usd_micros': 204, 'denied': 0}, {'scope': 'labeling', 'calls': 21, 'spent_usd_micros': 4821, 'denied': 0}, {'scope': 'shop', 'calls': 28, 'spent_usd_micros': 5025, 'denied': 0}]
intents ok
```

Ids conferidos contra `LLM_PRICES` (US$ por milhão de tokens, entrada/saída, pico):
`deepseek-flash` 0,30/1,20 e `deepseek-v4-pro` 1,32/3,96. Folga do dia: US$ 2,99.

**Custo previsto** (medido com cliente falso, sem rede): 103 chamadas por rodada, cerca
de 790 tokens de entrada e até 600 de saída cada. Três rodadas de flash: cerca de
US$ 0,13 (pior caso 0,29). Três de v4-pro: cerca de US$ 0,50 (pior caso 1,06).

## Ponto de comparação: sem modelo, no `main` de hoje

O mesmo conjunto com a leitura local (sem rede, custo zero), medido em 20/11/2026 18h03
no `main` (`e92a40f00`). Contra a linha de base de 16/11 (antes do WP-08 e dos ajustes desta semana):
partes 72/85 (eram 67/85), várias partes todas achadas 13/16 (eram 12/16), equipe achada
11/13 (eram 6/13), equipe sem precisar 4 (eram 4), uma parte lida como várias 8/50 (eram 7/50).

```text
═══ Intenções no plural (golden set) ═══
147 casos (16 com mais de uma parte). Leitura: local. Porteiro: regra local e, nos casos observados, as notas do Jev gravadas em sombra.

                                    antes (uma intenção)    depois (partes)
  Todas as partes achadas, várias   0/16                    13/16
  Todas as partes achadas, todos    35/66                   53/66
  Partes achadas                    50/85                   72/85
  Equipe achada                     11/13                   11/13
  Equipe sem precisar               3                       4
  Uma parte lida como várias                                8/50

Quem decidiu as partes: gate 44, local 103 · motivo do porteiro: jev_unsure 63, jev_certain 23, local_multiple 22, rules_single 21, rules_unsure 15, jev_two_intents 3
Por mensagem (todas): US$ 0.000000 de modelo · porteiro + leitura p50 0 ms, p95 0 ms
Equipe perdida: msg-109 "hmm, sera que posso pagar com cartão? o [dado fina" (unknown + unknown); msg-596 "[link omitido]" (unknown)
Equipe sem precisar: msg-696 "Cancela" (cancel_order); campo-1 "então quero 2 croissants. até que horas vocês fica" (order + hours_delivery + product_question + allergy); campo-2 "você não respondeu: até que horas vocês abrem? e o" (hours_delivery + product_question + allergy); campo-5 "o pão de queijo tem lactose? meu filho tem alergia" (allergy)

Partes perdidas (13; as primeiras 13):
  msg-53 "quero que me avise quando estiver disponivel, pode ser?": esperado product_question, saiu order (gate)
  msg-59 "seguimos. é para entrega, ok. qual a taxa?": esperado order|hours_delivery + hours_delivery, saiu unknown + hours_delivery + product_question (local)
  msg-113 "o link de pagamento por [dado financeiro ou segredo omitido], ok. avis": esperado complaint|human + complaint|human|order_status, saiu unknown + human + unknown + unknown + unknown (local)
  msg-119 "#menu [código omitido]": esperado product_question, saiu unknown (local)
  msg-205 "Bom dia tudo bem? Vai ter croissant hoje?": esperado product_question, saiu greet + unknown (local)
  msg-545 "O valor para pagar o pão de sábado": esperado order_status|order, saiu unknown (local)
  msg-557 "olá, bom dia. Gostaria de saber se vcs estarão abertos no próximo domi": esperado hours_delivery, saiu greet + order (local)
  msg-596 "[link omitido]": esperado job, saiu unknown (local)
  msg-608 "Por favor , preciso que entreguem em casa, tudo bem?": esperado hours_delivery|order, saiu unknown (local)
  msg-610 "Amanhã vai ter pão de forma?": esperado product_question, saiu unknown (local)
  msg-665 "Ainda é possível fazer pedidos?": esperado order|hours_delivery, saiu unknown (local)
  msg-686 "1 pão italiano grande e 2 croissant": esperado order, saiu unknown (local)
  campo-7 "Boa tarde! Amanhã vai ter pão de forma? Queria para entregar": esperado product_question + hours_delivery|order, saiu greet + unknown + order (local)
```

## Placar com `deepseek-flash` (3 rodadas)

Rodado em 20/11/2026 à noite, sozinho no console, com teto de US$ 0,40. Uma primeira
rodada completa (309 chamadas, US$ 0,103) se perdeu: a saída foi para o `/tmp` do
container, que reiniciou. O motivo das quedas não era deploy: o `maintenance-worker` é
`apps-s-1vcpu-0.5gb`, e dois shells em paralelo mais o próprio worker estouram a
memória. Um de cada vez funciona. Saída copiada da tela pela coordenação:

```text
═══ Intenções no plural (golden set) ═══
147 casos (16 com mais de uma parte). Leitura: model. Porteiro: regra local + notas do Jev em sombra.
antes → depois: várias todas achadas 0/16 → 13/16; todos 35/66 → 60/66; partes 50/85 → 79/85; equipe achada 11/13 → 11/13; equipe sem precisar 0 → 1; uma parte lida como várias 5/50
Leitura com o modelo: 92 de 147 (63%); US$ 0.00027 por leitura; p50 1336 ms, p95 2662 ms
Por mensagem: US$ 0.000230 · porteiro+leitura p50 1069 ms, p95 3394 ms
Falhas da leitura (caiu na divisão local): max_tokens 11
Equipe perdida: msg-109 "hmm, sera que posso pagar com cartão? o [dado fina" (house_info); msg-596 "[link omitido]" (unknown)
Equipe sem precisar: msg-696 "Cancela" (cancel_order)
Partes perdidas (6):
- msg-53 "quero que me avise quando estiver disponivel, pode ser?": esperado product_question, saiu order (gate)
- msg-59 "seguimos. é para entrega, ok. qual a taxa?": esperado order|hours_delivery + hours_delivery, saiu unknown + hours_delivery (model)
- msg-113 "o link de pagamento por [...], ok. avis": esperado complaint|human + complaint|human|order_status, saiu unknown + human + unknown + unknown + unknown (local)
- msg-596 "[link omitido]": esperado job, saiu unknown (model)
- msg-665 "Ainda é possível fazer pedidos?": esperado order|hours_delivery, saiu house_info (model)
- campo-7 "Boa tarde! Amanhã vai ter pão de forma? Queria para entregar": esperado product_question + hours_delivery|order, saiu greet + unknown + order (local)
Repetição, 3 rodadas, 147 casos em todas (r1 / r2 / r3 / em todas):
- várias todas achadas: 13/16, 13/16, 14/16 / 13/16
- todos: 60/66, 60/66, 61/66 / 60/66
- partes (mínimo): 79/85, 79/85, 80/85 / 79/85
- equipe achada: 11/13 nas três / 11/13
- equipe sem precisar: 1, 1, 2 / limpos 132/134
- uma parte lida como várias: 5, 4, 7 / limpos 43/50
Gasto da rodada: US$ 0.1003 de US$ 0.4000. Nada foi gravado.
```

**Achado (flash):** 11 leituras caíram na divisão local por `max_tokens`. O pedido da
leitura (`intents.build_request`) manda `max_tokens: 600` e nenhum `thinking`; a DeepSeek
aceita `thinking` (`ai.EXTRAS_BY_HOST`) e, raciocinando por padrão, gasta o teto antes do
JSON. Sem essas 11 quedas, as partes e a equipe tendem a subir; é correção própria.

## Placar com `deepseek-v4-pro` (3 rodadas, teto US$ 1,40)

PENDENTE: saída de `/tmp/wp09-pro.log`.

## `concierge_check --live`

PENDENTE: saída de `/tmp/wp09-check.txt`.

## Gasto do dia, depois

PENDENTE: o passo 0 de novo (`/tmp/wp09-freio-depois.txt`).

## Metas do WP-09 e veredito

| Meta | Sem modelo (hoje) | flash | v4-pro |
|---|---|---|---|
| Equipe achada 13/13 nas três rodadas | 11/13 | PENDENTE | PENDENTE |
| Partes achadas ≥ 90% | 72/85 (85%) | PENDENTE | PENDENTE |
| Várias partes, todas achadas ≥ 85% | 13/16 (81%) | PENDENTE | PENDENTE |
| Equipe sem precisar ≤ 4 | 4 | PENDENTE | PENDENTE |
| p95 da leitura < 2 s | 0 ms | PENDENTE | PENDENTE |

Recomendação de modelo: PENDENTE.

## Fora deste relatório

O ensaio no número do dono e as três conversas de verificação (respondida, atrasada,
assumida) a coordenação marca depois deste placar; entram como seção própria quando
acontecerem.
