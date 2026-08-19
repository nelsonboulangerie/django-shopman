# ADR-025 — O idioma dos eventos entre pacotes: anúncio depois do COMMIT

**Status:** Proposto (rascunho para revisão do dono, 2026-08-19)
**Data:** 2026-08-19
**Escopo:** os sinais publicados pelos pacotes do Core (`payman`, `cashman`, `orderman`, `craftsman`, `stockman`, `guestman`, `offerman`, `doorman`) e quem os escuta no orquestrador
**Origem:** achados P1 e P8 da auditoria do Payman (`auditoria-payman-2026-08-18.md`), com o mesmo tema já levantado na auditoria do Cashman
**Não decide:** se um sinal específico deve existir; isso continua sendo a regra da [ADR-001](adr-001-protocol-adapter.md) (anunciar → signal; precisar de retorno → adapter; comando confiável → directive)

---

## Contexto

A suíte publica sinais em oito pacotes e não tinha um critério escrito para
decidir quando o `send` sai. Hoje convivem três formas:

1. **`transaction.on_commit` na emissão** — `cashman` (todos os anúncios,
   `services/ledger.py` e `services/shifts.py`), `stockman`
   (`holds_materialized` em `services/planning.py`) e, desde a correção do P1,
   `payman` (`PaymentService._announce`).
2. **`send` dentro da transação** — `orderman` (`order_changed`), `craftsman`
   (`production_changed`), `guestman`, `offerman`, `doorman`.
3. **`on_commit` do lado de quem escuta** — o fan-out SSE do orquestrador
   (`shopman/shop/handlers/_sse_emitters.py`) recebe o sinal dentro da
   transação e adia só a publicação; o handler de alertas do `stockman`
   (`contrib/alerts/handlers.py`) faz o mesmo, ali por outro motivo (esperar o
   `F()` do `Quant` ser aplicado).

A diferença não é estilo. Emitir **um anúncio** dentro da transação tem três
consequências concretas, e a primeira já estava armada: o PDV envolve
`settle_terminal_tenders` e a escrita da venda no livro do turno num `atomic` só
(`_settle_pos_sale`, `shopman/shop/services/pos.py`); com o `send` lá dentro, um
erro na segunda metade revertia o pagamento e deixava de pé o que o receiver já
tinha feito com a notícia de um dinheiro que, para o banco, nunca existiu. A
segunda: exceção de receiver aborta a operação que emitiu — o rabo abana o
cachorro. A terceira: um receiver que consulte por outra conexão não enxerga o
que o sinal afirma.

Só que nem todo `send` é anúncio. Ao ler os dois pacotes que ainda emitem
dentro da transação, os dois se revelaram **escrita acoplada** — o receiver não
está sendo avisado, está completando a operação:

- **`order_changed`** (`shopman/shop/apps.py:188-202`): no `event_type ==
  "created"` o receiver roda `secure_stock(order)` **síncrono, de propósito**,
  com o comentário dizendo por quê — falha de reserva tem de desfazer o pedido
  inteiro, sem linha órfã. O resto do lifecycle **já é adiado** pelo próprio
  receiver: `_tx.on_commit(lambda: dispatch(order, phase))`.
- **`production_changed`** (`packages/craftsman/.../services/execution.py:320-330`,
  handlers em `craftsman/contrib/stockman/handlers.py`): o comentário no
  emissor chama os handlers de "the single canonical craftsman→stockman write
  path". O ledger de estoque (consumo de insumo + realização do output) é
  escrito ali.

Uma correção de fato da auditoria: **os sinais do Payman não estão sem
consumidor.** O orquestrador conecta os cinco a `_on_payment_changed`, que
empurra o evento SSE da tela de acompanhamento. Esse receiver estava protegido
por acaso — ele mesmo usa `on_commit` para publicar, e um rollback descarta o
callback junto. A proteção era do receiver, não do contrato; o próximo
consumidor não herdaria nada.

## Decisão

1. **Quem decide quando o `send` sai é o que o RECEIVER faz, não a busca por
   uniformidade.** Dois casos, dois idiomas, e a pergunta que separa os dois
   está no item 2:
   - **Anúncio** (ninguém depende dele para que a escrita esteja completa —
     SSE, B.I. incremental, broadcast, notificação): sai por
     `transaction.on_commit`. Fora de bloco atômico o Django roda o callback na
     hora, então chamador não-transacional não muda de comportamento.
   - **Escrita acoplada** (o efeito precisa ser atômico com a mudança — gate de
     estoque, ledger): fica **dentro** da transação, deliberadamente, com o
     porquê escrito no código, ao lado do `send`.
2. **O teste para saber em qual caso você está**, na hora de escrever um sinal
   novo: *se este receiver não rodar, a operação que emitiu continua correta?*
   - **Sim** → é anúncio: `on_commit`. A tela atualiza atrasada, o B.I. perde um
     ponto, e o dinheiro/estoque continuam certos.
   - **Não** → não é anúncio: ou é escrita acoplada, assumida como tal e
     documentada, ou você queria um adapter/Protocol (retorno síncrono) ou uma
     Directive (comando confiável) — [ADR-001](adr-001-protocol-adapter.md).
     Um receiver que precisa rodar e não roda falha em silêncio; esse é o
     defeito, não o `on_commit`.
3. **A garantia é do emissor, não do receiver.** No caso anúncio, quem escuta
   não deve precisar saber em que transação foi chamado. Um `on_commit` no
   receiver continua legítimo quando o motivo é dele (o caso do
   `stockman/contrib/alerts`, que espera o `F()` ser aplicado), nunca como
   remendo para um emissor que devia adiar.
4. **Os sinais ficam.** Não são peso morto: o SSE consome os do `payman`, e a
   ponte `craftsman → stockman` consome `production_changed`. O que faltava era
   contrato de entrega, não consumidor.
5. **O kwarg de instância é a instância viva, não um retrato.** Quando um verbo
   encadeia transições (o `reconcile_gateway_status` que autoriza e captura no
   mesmo snapshot), o receiver lê o estado FINAL. Quem precisa do valor exato de
   cada etapa lê a linha imutável do ledger (`transaction`, `entry`) ou releia o
   banco. Cada pacote documenta isso no docstring do seu módulo de sinais.
6. **`orderman` e `craftsman` FICAM COMO ESTÃO.** Não é conversão pendente; é
   decisão, e converter seria regressão:
   - **`order_changed`** já é `on_commit` onde importa — no receiver
     (`shopman/shop/apps.py:202`), que adia o `dispatch()`. Mover o `send` não
     ganharia nada e **quebraria o gate duro de estoque**: com o anúncio depois
     do COMMIT, o pedido sem estoque já estaria gravado e o `secure_stock`
     (`shopman/shop/apps.py:196`) não teria mais o que desfazer. Trocaria "o
     pedido não nasce" por "o pedido nasce e alguém descobre depois".
   - **`production_changed`** é caminho de escrita, não anúncio. Com
     `on_commit`, "fornada terminada" e "insumo consumido" viram duas
     transações: o processo que morre entre as duas deixa produção feita com
     estoque intacto — exatamente o fantasma que o ledger existe para impedir,
     e ainda por cima na direção que ninguém confere.

## Consequências

**Positivas**

- Efeito fantasma sob rollback deixa de ser possível no `payman` e no `cashman`,
  os dois pacotes que falam de dinheiro.
- Receiver de anúncio quebrado passa a quebrar só a si mesmo.
- O consumidor novo (BI incremental, Broadcast) não precisa saber a transação de
  ninguém para escutar com segurança.
- A suíte deixa de ter "dívida" que não era dívida: os dois emissores
  in-transaction passam a ser casos classificados e explicados, não pendências.

**Negativas / custos**

- Teste que espera receber anúncio precisa executar dentro de
  `captureOnCommitCallbacks(execute=True)` (`TestCase`) ou
  `django_capture_on_commit_callbacks` (pytest). É ruído em quem já existia:
  `packages/payman/.../tests/test_signals.py` e
  `packages/cashman/.../tests/test_services.py` mostram a forma.
- Convivem dois idiomas de emissão, e a diferença entre eles é semântica (o que
  o receiver faz), não sintática. Quem lê rápido pode achar que é inconsistência
  — por isso a regra é escrita aqui e o motivo fica ao lado de cada `send`
  acoplado.
- **Escrita acoplada por signal continua falhando em silêncio** se o handler não
  estiver registrado (o app de contrib fora do `INSTALLED_APPS`). Esta ADR não
  resolve isso; registra que os dois casos existentes aceitam o risco em troca
  da atomicidade, e que um caso NOVO de escrita acoplada deve preferir chamada
  direta ou ponte explícita (ADR-001).
- Um anúncio adiado nunca roda se o processo morrer entre COMMIT e callback.
  Sinal é anúncio best-effort e continua sendo: quem precisa de entrega
  garantida usa Directive ([ADR-003](adr-003-directives-sem-celery.md)).

## Invariantes

- **Sinal de anúncio sai por `on_commit`.** Anúncio é aquele cujo receiver, se
  não rodar, deixa a operação emissora igualmente correta.
- **Sinal usado como escrita acoplada fica dentro da transação, e diz isso no
  código** — comentário no ponto do `send` explicando qual atomicidade está
  sendo comprada. Sem o comentário, é `on_commit` por default.
- Receiver de anúncio nunca é caminho de escrita obrigatória: se o efeito
  precisa acontecer, ele é chamada direta, adapter ou directive (ADR-001).
- Sinal do Core não carrega promessa de ordem entre pacotes diferentes; a ordem
  garantida é só a de registro dos callbacks da mesma transação.

## Alternativas consideradas

- **Uniformizar tudo em `on_commit`.** Era a proposta original desta ADR e está
  errada: quebraria o gate de estoque do `order_changed` e partiria o ledger de
  produção em duas transações. Uniformidade não é o objetivo; previsibilidade é.
- **Deixar cada pacote escolher, sem critério escrito.** É o estado que gerou o
  P1: dois pacotes de dinheiro com contratos de entrega diferentes, e a
  diferença aparecendo só no dia do rollback.
- **Apagar os sinais e deixar só chamada direta.** Resolveria o P8 pelo vazio,
  mas o SSE (ADR-016) precisa do fan-out desacoplado, e a ponte
  `craftsman → stockman` é exemplo canônico da ADR-001.
- **Exigir `on_commit` do receiver.** Empurra a armadilha para quem chega
  depois, que é justamente quem não conhece o código.
- **Outbox durável (tabela de eventos + worker).** É o desenho certo quando
  houver consumidor que não pode perder evento; hoje seria infraestrutura para
  um consumidor só, e a Directive já cobre o caso "não pode perder".

## Referências

- ADR-001 (signal × adapter × directive), ADR-003 (directives), ADR-016 (SSE)
- `packages/payman/shopman/payman/service.py` (`PaymentService._announce`),
  `packages/cashman/shopman/cashman/services/ledger.py`
- `shopman/shop/apps.py:188-202` (gate de estoque síncrono + `dispatch` adiado),
  `packages/craftsman/shopman/craftsman/services/execution.py:320-330` e
  `packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py`
  (o caminho canônico de escrita craftsman→stockman)
- `shopman/shop/handlers/_sse_emitters.py` (`_on_payment_changed`),
  `shopman/shop/services/pos.py` (`_settle_pos_sale`)
- `auditoria-payman-2026-08-18.md` (P1, P8)
