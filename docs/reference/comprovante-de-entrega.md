# Comprovante de entrega dos avisos ao cliente

Decisão do dono (D3, 01/10/2026): e-mail e SMS podem sair sozinhos como reserva quando o
WhatsApp não confirmar, **só nos avisos críticos**, e todo envio crítico precisa de recibo.
Origem: o link de pagamento do pedido `PDV-260930-R62` foi "despachado 2×, entregue 0"
(`docs/reports/go-live-acceleration-20260930-diag/03-pdv-link-pagamento.md`).

## A regra em uma linha

**Aceite não é entrega.** "Entregue" só aparece quando o provedor devolveu um
identificador da mensagem. Sem identificador, o estado é "Aceito pelo provedor, sem
comprovante", e ninguém deve tratar isso como entregue.

## Os estados que o operador vê

No Gestor, detalhe do pedido, bloco **Avisos ao cliente** (um item por aviso, com canal,
hora, comprovante e a trilha de cada canal tentado):

| Estado na tela | Quando | O que prova |
|---|---|---|
| **Entregue com comprovante** | o provedor aceitou E devolveu identificador (`proof: receipt`) | que o provedor registrou a mensagem e assumiu a entrega. **Não** prova que chegou ao celular do cliente, nem que foi lida |
| **Aceito pelo provedor, sem comprovante** | o provedor disse "ok" sem identificador (`proof: no_receipt`) | só que a chamada foi aceita. A mensagem pode não ter saído (ex.: WhatsApp fora da janela de 24 h) |
| **Aceite não confirmado** | a resposta se perdeu (timeout, conexão caiu depois do envio) | nada. Pode ter saído ou não. Não reenvie sem falar com o cliente |
| **Falhou em todos os canais** | nenhum canal aceitou | que o cliente não recebeu por nós |
| **Não enviado** | o aviso foi omitido de propósito (sem contato, opt-out, pagamento já feito) | o motivo aparece na linha |
| **Na fila** / **Enviando** | o worker ainda não terminou | nada ainda |

O PDV (resultado da venda com link) e o aviso do link no Gestor usam a mesma régua:
"Entregue pelo e-mail às 18h42, com comprovante" ou "Aceito pelo WhatsApp às 18h42, sem
comprovante de entrega".

## O que cada canal comprova hoje

| Canal | Devolve identificador? | Observação |
|---|---|---|
| **WhatsApp (ManyChat)** | **Não.** A API do ManyChat responde `status: success` sem id de mensagem | sempre "aceito, sem comprovante". Texto livre (aviso sem template aprovado) só é entregue pela Meta dentro da janela de 24 h, e o ManyChat aceita mesmo fora dela |
| **E-mail (SMTP)** | **Sim**, o `Message-ID` da mensagem que o servidor SMTP aceitou (resposta 250) | o `Message-ID` é gerado pela casa com o domínio do remetente e localizável na caixa de Enviados da conta que envia. Prova que o servidor de e-mail assumiu a entrega; não prova caixa de entrada (pode cair em spam ou voltar depois) nem leitura |
| **SMS (Comtele)** | **Não.** A resposta de envio traz `hasError` e contagem, sem id | sempre "aceito, sem comprovante" |
| **WhatsApp Cloud (adapter direto, fora da cadeia hoje)** | Sim, o `wamid` da Meta | aceito pela Meta; não é recibo de leitura |

Consequência prática: hoje o único comprovante disponível na cadeia é o do **e-mail**.
Cliente de aviso crítico sem e-mail cadastrado termina "aceito, sem comprovante" e gera
alerta ao operador.

## Quais avisos são críticos, e por quê

Lista no código: `CRITICAL_NOTIFICATION_TEMPLATES` em `shopman/shop/services/notification.py`.

- `payment_link_sent`: é a cobrança inteira do pedido remoto anotado no PDV. Se não
  chega, a casa espera um dinheiro que ninguém pediu.
- `order_accepted`: é a confirmação do pedido ("Pedido confirmado, o total é…"). Sem ela
  o cliente não sabe que a casa vai preparar.

Mudar a lista é decisão do dono: cada evento a mais pode virar SMS pago e mensagem em
dobro.

## Como a cadeia se comporta

A cadeia do canal é configurada em `ChannelConfig.notifications` (ex.: PDV:
`manychat → email → sms`).

**Aviso crítico:**

1. tenta o primeiro canal;
2. aceito **com** identificador: para aí, "Entregue com comprovante";
3. aceito **sem** identificador, ou resposta **ambígua**: anota o salto e **segue para o
   próximo canal**;
4. recusado: segue para o próximo, como sempre;
5. fim da cadeia sem comprovante, mas com algum aceite: fica "Aceito pelo provedor, sem
   comprovante" e **cria alerta para o operador** (`OperatorAlert` tipo
   `notification_failed`): "foi aceito pelo provedor, mas nenhum canal devolveu
   comprovante de entrega. Confirme com o cliente que ele recebeu." Não há reenvio
   automático, que seria mais uma mensagem;
6. fim só com ambíguos: "Aceite não confirmado", alerta e bloqueio de reenvio
   automático (como antes).

**Demais avisos:** o primeiro aceite encerra a cadeia (com ou sem identificador), e a
resposta ambígua para a cadeia. Ligar o fallback em massa custaria SMS e viraria spam.

## Duplicata: o preço aceito

Em aviso crítico, se o WhatsApp de fato entregou (mesmo sem devolver identificador) e o
e-mail também sai, **o cliente recebe a mensagem duas vezes**, às vezes três (WhatsApp,
e-mail e SMS, quando não há e-mail que dê comprovante). O dono aceitou: recibo vale mais
que silêncio. O mesmo vale para a resposta ambígua: o primeiro canal pode ter entregue.

## Onde mora o dado

`Directive.payload["notification_delivery"]` da Directive `notification.send` de cada
aviso: `status`, `proof`, `critical`, `backend`, `message_id`, `recipient_fingerprint`
(nunca o contato) e `attempts` (um item por canal tentado). Esquema completo em
[data-schemas.md](data-schemas.md), seção `notification.send`.
