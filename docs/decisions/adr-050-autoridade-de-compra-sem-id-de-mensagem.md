# ADR-050 — Autoridade de compra sem identificador de mensagem: sacola em valor absoluto, fechamento pelo código do orçamento

**Status:** Aceito
**Data:** 2026-11-20
**Escopo:** `shopman/storefront/concierge/service.py` (`_claim`, `assert_turn_authority`), `tools.py` (`_guard`, `review_order`, `place_order`, `_code_confirmation`), `effect_authority.py` (`lock_turn_authority`), `turn_outcome.py` (`collapse_repeats`)
**Origem:** WP-11 de `docs/plans/CONCIERGE-PLANO-DE-ACAO.md` (corte C6 revertido pelo dono em 16/11: "quero que a Concierge consiga montar o pedido do cliente NA CONVERSA"); compromisso DEV-2026-027

---

## Contexto

O ManyChat entrega a mensagem do WhatsApp **pelo menos uma vez**, sem identificador imutável
e sem horário verificado (`docs/guides/whatsapp-concierge.md`, "Ausência de ID de mensagem").
Um reenvio técnico é indistinguível de o cliente repetir a frase, e não há prova de que um
"sim" veio depois de um resumo. Por isso o contrato de hoje fecha toda mudança: com o
ingresso nesse estado (`_limited_event_assurance`), `_commercial_authority` é falso e
nenhuma ferramenta que muda sacola, pedido ou inscrição roda.

Isso impede o pedido na conversa (WP-12 a WP-14). O plano recomendava dois níveis de
autoridade; este ADR atacou o desenho antes de aceitar.

## Decisão

### 1. Autoridade de sacola (`_cart_authority`)

Concedida no claim quando **o cliente é verificado** (`binding.identity_assurance ==
"verified_customer"`) e **a conexão não é só leitura** (`SHOPMAN_CONCIERGE["read_only"]` e a
opção `read_only` da conexão), mesmo sem identificador de mensagem.

Vale para `set_item`, `set_fulfillment`, `review_order` e, com a prova do item 2,
`place_order` (`tools.CART_TOOLS`). Essas mudanças são reversíveis e em **valor absoluto**:
`set_item(sku, 4)` repetido dá 4, não 8.

**Furo achado e fechado.** O valor absoluto não basta: "mais 2" é relativo, e o leitor o
converte em absoluto contra a sacola de agora. Um reenvio de "mais 2" lido depois da
primeira aplicação viraria 6. Defesa: no mesmo lote não respondido, **mensagens idênticas
seguidas valem um comando** (`turn_outcome.collapse_repeats`, só com o ingresso limitado).
Nada é descartado: as duas ficam na transcrição, como o guia exige ("nenhum hash de contato
+ timestamp é usado para descartar mensagens"). O reenvio do provedor chega em segundos,
dentro do mesmo lote (o turno espera `dispatch_delay_seconds` e reivindica todas as
entradas sem resposta).

**Risco que fica, escrito:** um reenvio técnico que chegue DEPOIS de um turno inteiro
(resposta já enviada) é lido como o cliente repetindo a frase. É a mesma ambiguidade de
hoje para qualquer resposta; na sacola, o resumo mostra o total a cada mudança e o
fechamento (item 2) só acontece com o código, então o erro aparece antes de virar pedido.

### 2. Fechamento pelo código do orçamento

`place_order` com a autoridade completa (identificador verificado) segue como está: o "sim"
com horário verificado depois do resumo (`tools._confirmation`).

Sem ela, **só o código do orçamento confirma** (`tools._code_confirmation`):

- `review_order` devolve `confirmation_code`, quatro dígitos tirados do `quote_token`
  (`tools.confirmation_code`). O token muda quando a sacola, a entrega ou o pagamento
  mudam, então o código também muda;
- o resumo diz: "Responda ‘confirmo 4821’ para registrar.";
- aceitos: `4821`, `confirmo 4821`, `confirmar 4821`, `sim 4821`, `sim, confirmo 4821`.
  Toda mensagem depois do resumo tem de ser essa confirmação; outra fala no meio invalida,
  como já acontece no `_confirmation`.

**Furo achado e fechado.** Um "sim" sozinho não serve: o cliente pode responder "sim" ao
resumo v1 enquanto a casa já mandava o v2, e sem horário verificado o "sim" chega depois do
v2 e confirmaria o que o cliente não viu. Com o código, o "confirmo" do v1 carrega o código
do v1 e não confirma o v2.

**Repetição:** a mesma confirmação entregue duas vezes gera **um** pedido e **um** Pix, pelo
`quote_token` (`run_idempotent_mutation`, inalterado).

### 3. O que continua exigindo a autoridade completa

`add_to_order` (mexe em pedido já feito), `send_web_link` (copia a sacola para o site) e
`notify_when_available` (registra consentimento). Fora do WP-11.

### 4. A guarda do N2 não enfraquece

`effect_authority.lock_turn_authority` ganha `level`: o pedido fechado pelo código passa o
nível da sacola. A **posse** (cerca do turno, transferência à equipe, claim vencido,
identidade trocada) é reconferida igual, na transação do efeito (#2625).

## Consequências

- O pedido na conversa fica possível com o ManyChat de hoje, sem esperar identificador.
- **O cliente digita o código para confirmar** ("confirmo 4821"). O dono escolheu um botão
  "Confirmar pedido" (20/11/2026: "botao 'confirmar pedido' ok"), mas a documentação do
  ManyChat não o entrega no WhatsApp: resposta rápida não existe lá ("Quick Reply buttons
  are not supported by WhatsApp and Telegram channels"), os botões aceitos (`url`, `flow`,
  `node`) não levam payload, e o `dynamic_block_callback`, o único que leva o payload ao
  servidor, só está documentado para o Messenger. Por isso o texto com o código é a forma
  principal hoje. O botão com o código no payload vira a principal se um ensaio no número
  do dono provar que o `dynamic_block_callback` chega íntegro no WhatsApp (seguimento do
  WP-11); o texto fica de reserva.
- **Contorno descartado:** gravar o código num campo do contato e o botão `flow` lê-lo no
  clique. O flow lê o valor de agora, então o botão de um resumo antigo confirmaria o
  orçamento novo, que é o furo que o código fecha.
- Se o ManyChat um dia entregar identificador verificado, o caminho de hoje
  (`_confirmation` com "sim") volta a valer sozinho, sem código.

## Alternativas descartadas

- **"sim" com o servidor contando a ordem de chegada.** O horário de chegada ao servidor
  não é o horário em que o cliente escreveu; o furo do item 2 continua.
- **Botão do ManyChat com o token no retorno, hoje.** Seria a prova mais limpa e é a escolha
  do dono, mas o WhatsApp do ManyChat não documenta botão com payload (ver Consequências).
  Fica condicionado ao ensaio.
- **Descartar mensagens repetidas por hash.** Proibido pelo guia: perde a repetição
  legítima do cliente.
