# Ensaio da Concierge: placar com modelo (WP-09)

O WP-09 de `docs/plans/CONCIERGE-PLANO-DE-ACAO.md`: a leitura das partes com modelo,
`deepseek-flash` e `deepseek-v4-pro` lado a lado na rota `intents`, com o Jev no porteiro,
contra o conjunto de mensagens reais (`concierge/golden_set.json`). Autorização do dono:
D-040 (mensagem redigida à DeepSeek e ao Jev, rodada de até US$ 2 no total).

> **Estado:** medido em 20/11/2026, no console do `maintenance-worker` de produção (a
> coordenação operou, o dono fez o login). Gasto total: **US$ 0,369** dos US$ 2 da D-040.
> **Recomendação: `deepseek-flash` na rota `intents`**, com duas correções antes de
> chamar a meta de batida (#2909, #2910).

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

## Placar com `deepseek-v4-pro` (3 rodadas, teto US$ 1,30)

Rodado logo depois do flash, sozinho, com a fila de diretivas pausada pela coordenação
enquanto rodava (religada em seguida). Saída copiada da tela:

```text
antes → depois:
- várias todas achadas 0/16 → 12/16
- todos 35/66 → 56/66
- partes 50/85 → 75/85
- equipe achada 11/13 → 11/13
- equipe sem precisar 0 → 1
- uma parte lida como várias 6/50
Quem decidiu as partes: gate 44, model 62, local 41. Motivo do porteiro: jev_unsure 63, jev_certain 23, local_multiple 22, rules_single 21, rules_unsure 15, jev_two_intents 3.
Leitura com o modelo: 62 de 147 (42%); US$ 0.00092 por leitura; p50 2151 ms, p95 3977 ms.
Por mensagem: US$ 0.000387 · porteiro+leitura p50 2135 ms, p95 4471 ms.
Falhas da leitura (caiu na divisão local): APITimeoutError 41
Equipe perdida: msg-109 (unknown + unknown); msg-596 (unknown).
Equipe sem precisar: msg-696 "Cancela".
Partes perdidas (10): msg-53 (gate → order); msg-59 (local); msg-113 (local); msg-119 "#menu [código omitido]" (local); msg-545 "O valor para pagar o pão de sábado" (local); msg-596 (model); msg-608 "Por favor, preciso que entreguem em casa, tudo bem?" (local); msg-665 (model → house_info); campo-2 (local: allergy lida como product_question); campo-7 (local)
Repetição r1 / r2 / r3 / em todas:
- várias 12/16, 12/16, 13/16, 12/16
- todos 56/66, 56/66, 58/66, 55/66
- partes 75/85, 75/85, 77/85, 74/85
- equipe 11/13 nas três, 11/13
- sem precisar 1/1/1, limpos 133/134
- uma lida como várias 6/4/7, limpos 42/50
Gasto da rodada: US$ 0.1652 de US$ 1.3000.
```

O v4-pro perdeu **por tempo, não por qualidade**: 41 das 103 leituras estouraram o
timeout de 4 s da leitura (`intents.READ_TIMEOUT_S`) e caíram na divisão local. Seis das
dez partes perdidas são dessas quedas. Uma revanche justa pede timeout maior, e mesmo
assim o p50 dele (2,15 s) já passa da meta de p95.

## `concierge_check --live`

```text
Configuração OK: modo assist, contrato 3, conexão, coorte e ManyChat.
ManyChat OK: campo concierge_handoff existe (manychat-whatsapp-primary).
Não conferido por comando: se o flow chama o Concierge em toda mensagem (ensaio manual do checklist).
```

## Gasto do dia, depois

```text
freio Limits(enabled=True, shop_usd_per_day=3.0, purposes={}); rotas {'default': {'connection': 'deepseek'}}; intents ok
hoje: decision 7 calls / 204 µ$; intents 944 calls / 376085 µ$; labeling 21 / 4821; shop 972 / 381110; denied 0 em todos.
```

Total do WP-09: US$ 0,369 (flash perdido no `/tmp` 0,103 + flash 0,100 + pro 0,165).
Nenhuma chamada negada pelo freio. A Concierge viva seguiu no modelo dela o tempo todo.

## Metas do WP-09 e veredito

Medido "em todas as 3 rodadas" (o pior das três).

| Meta | Sem modelo (hoje) | flash | v4-pro |
|---|---|---|---|
| Equipe achada 13/13 nas três rodadas | 11/13 | 11/13 ✗ | 11/13 ✗ |
| Partes achadas ≥ 90% | 72/85 (85%) | **79/85 (93%) ✓** | 74/85 (87%) ✗ |
| Várias partes, todas achadas ≥ 85% | 13/16 (81%) | 13/16 (81%) ✗ | 12/16 (75%) ✗ |
| Equipe sem precisar ≤ 4 | 4 | **1 ✓** | **1 ✓** |
| p95 da leitura < 2 s | 0 ms | 2.662 ms ✗ | 3.977 ms ✗ |
| Custo por mensagem | 0 | US$ 0,00023 | US$ 0,00039 |

**Recomendação: `deepseek-flash` na rota `intents`.** Ganha do v4-pro em qualidade
(partes 79 contra 74), em tempo (p50 1,3 s contra 2,2 s) e custa 40% menos por
mensagem. Contra a leitura sem modelo, sobe as partes de 72 para 79 e corta a equipe
sem precisar de 4 para 1.

**Três metas não batidas, com o caso e a issue:**

- **p95 da leitura (2,66 s) e as 11 quedas por `max_tokens`** do flash: o pedido da
  leitura não desliga o raciocínio da DeepSeek, que gasta o teto de 600 antes do JSON.
  Duas das três "várias partes" perdidas (msg-113 e campo-7) são leituras que caíram na
  divisão local. É a #2909, com uma rodada curta de prova (e a revanche do v4-pro com
  timeout maior, no mesmo passo).
- **Equipe achada 11/13**, nos três modos: msg-109 (o dado financeiro apagado era o sinal
  de cobrança) e msg-596 (só um link, que a redação apaga). Não é o modelo, é o que chega
  a ele. É a #2910.

**O que muda em produção, e quem decide.** Nada na rota: a conexão `deepseek` foi criada
no Admin em 19/11 com o modelo `deepseek-flash` (confirmado pela coordenação em 20/11), e a
rota `intents`, sem entrada própria, cai na `default`, que aponta para ela. A leitura de
produção já é o `deepseek-flash` recomendado aqui. O que falta para a meta de tempo é o
pedido da leitura sem raciocínio (#2909). Pelo plano, meta não batida não segura a
abertura das respostas: a Concierge abre como está, com o "vou verificar" cobrindo o que a
leitura não achar. Abrir para o grupo de até 20 contatos é palavra do dono, com este
relatório.

## Fora deste relatório

O ensaio no número do dono e as três conversas de verificação (respondida, atrasada,
assumida) a coordenação marca depois deste placar; entram como seção própria quando
acontecerem.


## Depois do relatório: a correção da leitura e a revanche do v4-pro (20/11/2026, noite)

O dono mudou a régua (20/11, ~22h35): "segundos de demora na resposta não são
problematicos, desde que a resposta seja 'correta'". **A correção decide** (partes,
várias partes, equipe achada, equipe sem precisar); o tempo só desempata e só reprova
acima de uns 10 s no p95. O custo não é o problema.

### Leitura sem raciocínio (#2911, prova do #2909)

Produção, deploy de 23h23Z, `deepseek-flash`, rodada única, com o pedido da leitura
desligando o raciocínio da DeepSeek (que vinha ligado por padrão):

```text
- várias todas achadas 0/16 → 16/16
- todos 36/66 → 63/66
- partes 51/85 → 82/85
- equipe achada 12/13 → 12/13
- equipe sem precisar 0 → 3
- uma parte lida como várias 5/50
Leitura com o modelo: 103 de 147 (70%); US$ 0.00013 por leitura; p50 882 ms, p95 1254 ms.
Por mensagem: US$ 0.000090 · porteiro+leitura p50 803 ms, p95 1224 ms.
Falhas da leitura: nenhuma (zero max_tokens, zero timeout).
Equipe perdida: msg-109 (house_info + unknown).
Equipe sem precisar: msg-90 "mas ja são 15h50 … como fica?" (complaint); msg-100 "sim, já tinha confirmado! vai logo que estou c..." (order_status + complaint); msg-696 "Cancela" (cancel_order).
Partes perdidas (3): msg-53 (gate→order); msg-119 "#menu [código omitido]" → unknown (model); msg-665 "Ainda é possível fazer pedidos?" → product_question (model).
Gasto: US$ 0.0133 de 0.15.
```

As quedas por `max_tokens` sumiram e o p95 caiu de 2,66 s para 1,25 s. A equipe achada
subiu para 12/13 com o #2912 (a msg-596); a msg-109 segue na #2910, régua do WP-13.

### Revanche do `deepseek-v4-pro`

Mesmas condições (raciocínio desligado, rodada única), com timeout de 20 s só no processo
do comando. Deploy de 23h36Z:

```text
- várias todas achadas 0/16 → 14/16
- todos 36/66 → 61/66
- partes 51/85 → 80/85
- equipe achada 12/13 → 12/13
- equipe sem precisar 0 → 1
- uma parte lida como várias 5/50
Leitura com o modelo: 95 de 147 (65%); US$ 0.00045 por leitura; p50 1324 ms, p95 1787 ms.
Por mensagem: US$ 0.000307 · porteiro+leitura p50 1240 ms, p95 1747 ms.
Falhas da leitura (caiu na divisão local): unreadable 2.
Equipe perdida: msg-109 (house_info + unknown).
Equipe sem precisar: msg-696 "Cancela".
Partes perdidas (5): msg-53 (gate→order); msg-59 "qual a taxa?" → só hours_delivery (model); msg-119 → unknown (local); msg-665 → house_info (model); campo-2 → hours_delivery + product_question (local).
Gasto: US$ 0.0451 de 0.40.
```

### Veredito

| | flash (sem raciocínio) | v4-pro (sem raciocínio, 20 s) |
|---|---|---|
| Partes | **82/85** | 80/85 |
| Várias partes, todas | **16/16** | 14/16 |
| Equipe achada | 12/13 | 12/13 |
| Equipe sem precisar | 3 | **1** |
| p95 da leitura | **1,25 s** | 1,79 s |
| Por mensagem | **US$ 0,00009** | US$ 0,00031 |

**Fica o `deepseek-flash`**, que já é o modelo da leitura em produção. Pela régua do dono
o v4-pro não passa: perde nas partes e nas várias partes e empata na equipe. Ele só é
melhor em "equipe sem precisar" (1 contra 3), que não decide a troca. As duas mensagens
que o flash mandou à equipe sem precisar (msg-90 e msg-100) ficam como alvo de régua na
#2922, sem rodada nova.

**Todas as metas do WP-09 batidas com o flash**, menos a equipe achada 13/13 (12/13, a
msg-109 depende do WP-13, #2910). Gasto total do WP-09: **US$ 0,427** dos US$ 2 da D-040.
