# ADR-025 — O idioma dos eventos entre pacotes: anúncio depois do COMMIT

**Status:** Proposto (rascunho para revisão do dono, 2026-08-19)
**Data:** 2026-08-19
**Escopo:** os sinais publicados pelos pacotes do Core (`payman`, `cashman`, `orderman`, `craftsman`, `stockman`, `guestman`, `offerman`, `doorman`) e quem os escuta no orquestrador
**Origem:** achados P1 e P8 da auditoria do Payman (`auditoria-payman-2026-08-18.md`), com o mesmo tema já levantado na auditoria do Cashman
**Não decide:** se um sinal específico deve existir; isso continua sendo a regra da [ADR-001](adr-001-protocol-adapter.md) (anunciar → signal; precisar de retorno → adapter; comando confiável → directive)

---

## Contexto

A suíte publica sinais em oito pacotes e não tem um idioma só para publicá-los.
Hoje convivem três:

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

A diferença não é estilo. Emitir dentro da transação tem três consequências
concretas, e a primeira já estava armada: o PDV envolve `settle_terminal_tenders`
e a escrita da venda no livro do turno num `atomic` só
(`_settle_pos_sale`, `shopman/shop/services/pos.py`); com o `send` lá dentro, um
erro na segunda metade revertia o pagamento e deixava de pé o que o receiver já
tinha feito com a notícia de um dinheiro que, para o banco, nunca existiu. A
segunda: exceção de receiver aborta a operação que emitiu — o rabo abana o
cachorro. A terceira: um receiver que consulte por outra conexão não enxerga o
que o sinal afirma.

Uma correção de fato da auditoria: **os sinais do Payman não estão sem
consumidor.** O orquestrador conecta os cinco a `_on_payment_changed`, que
empurra o evento SSE da tela de acompanhamento. Esse receiver estava protegido
por acaso — ele mesmo usa `on_commit` para publicar, e um rollback descarta o
callback junto. A proteção era do receiver, não do contrato; o próximo
consumidor não herdaria nada.

## Decisão

1. **O idioma da casa é anunciar depois do COMMIT.** Todo `signal.send` de
   pacote do Core sai por `transaction.on_commit`. Fora de bloco atômico o
   Django roda o callback na hora, então chamador não-transacional não muda de
   comportamento.
2. **A garantia é do emissor, não do receiver.** Quem escuta não deve precisar
   saber em que transação foi chamado. Um `on_commit` no receiver continua
   legítimo quando o motivo é dele (o caso do `stockman/contrib/alerts`, que
   espera o `F()` ser aplicado), nunca como remendo para um emissor
   in-transaction.
3. **Os sinais ficam.** Não são peso morto: o SSE consome os do `payman`, e a
   ponte `craftsman → stockman` consome `production_changed`. O que faltava era
   contrato de entrega, não consumidor.
4. **O kwarg de instância é a instância viva, não um retrato.** Quando um verbo
   encadeia transições (o `reconcile_gateway_status` que autoriza e captura no
   mesmo snapshot), o receiver lê o estado FINAL. Quem precisa do valor exato de
   cada etapa lê a linha imutável do ledger (`transaction`, `entry`) ou releia o
   banco. Cada pacote documenta isso no docstring do seu módulo de sinais.
5. **A conversão dos pacotes restantes é caso a caso, não varredura.**
   `order_changed` dirige o `dispatch()` do lifecycle e mover para `on_commit`
   muda quando a fase roda — é mudança de comportamento, não de estilo, e pede
   PR próprio com testes de lifecycle. `production_changed` escreve o ledger de
   estoque pela ponte `craftsman/contrib/stockman`: ali o efeito é escrita no
   banco que deve viver na MESMA transação da produção, e mover para `on_commit`
   quebraria a atomicidade — a conversão precisa decidir antes se aquilo é
   anúncio ou escrita acoplada (pela ADR-001, escrita acoplada não é signal).

## Consequências

**Positivas**

- Efeito fantasma sob rollback deixa de ser possível no `payman` e no `cashman`,
  os dois pacotes que falam de dinheiro.
- Receiver quebrado passa a quebrar só a si mesmo.
- O consumidor novo (BI incremental, Broadcast) não precisa saber a transação de
  ninguém para escutar com segurança.

**Negativas / custos**

- Teste que espera receber sinal precisa executar dentro de
  `captureOnCommitCallbacks(execute=True)` (`TestCase`) ou
  `django_capture_on_commit_callbacks` (pytest). É ruído em quem já existia:
  `packages/payman/.../tests/test_signals.py` e
  `packages/cashman/.../tests/test_services.py` mostram a forma.
- A suíte fica temporariamente com dois idiomas até a conversão caso a caso
  terminar. Esta ADR é o registro de qual é o certo — e de que a diferença é
  dívida conhecida, não descuido.
- Um anúncio adiado nunca roda se o processo morrer entre COMMIT e callback.
  Sinal é anúncio best-effort e continua sendo: quem precisa de entrega
  garantida usa Directive ([ADR-003](adr-003-directives-sem-celery.md)).

## Invariantes

- Nenhum `signal.send` de pacote do Core dentro de bloco atômico sem
  `on_commit`, salvo exceção justificada por escrito no próprio código.
- Receiver nunca é caminho de escrita obrigatória: se o efeito precisa
  acontecer, ele é chamada direta, adapter ou directive (ADR-001).
- Sinal do Core não carrega promessa de ordem entre pacotes diferentes; a ordem
  garantida é só a de registro dos callbacks da mesma transação.

## Alternativas consideradas

- **Deixar cada pacote escolher.** É o estado atual: dois pacotes de dinheiro
  com contratos diferentes de entrega, e a diferença só aparece no dia do
  rollback.
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
- `shopman/shop/handlers/_sse_emitters.py` (`_on_payment_changed`),
  `shopman/shop/services/pos.py` (`_settle_pos_sale`)
- `auditoria-payman-2026-08-18.md` (P1, P8)
