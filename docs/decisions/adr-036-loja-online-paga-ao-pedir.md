# ADR-036 — Loja online paga ao pedir, com prazo de aceite e estorno automático

**Status:** Aceito em 2026-10-14 (decisão do dono, perguntas 1 e 2 de
`docs/reference/cenarios-de-pedido.md`, L1=1 e L2=1).
**Nota do dono:** "se os estornos ficarem constantes, reavaliar".

## Contexto

Até aqui a loja online cobrava **depois** do aceite: o Pix nascia quando a loja aceitava e vencia
em 10 minutos (`payment.timing = "post_commit"`). Quem pedia à noite e não via o aviso de manhã
perdia o pedido (P1-5). O cartão já autorizava no pedido e só cobrava no aceite, mas sem prazo:
ficava preso até a autorização vencer no Stripe, sete dias depois (P1-4, #1732).

O WhatsApp já cobrava no pedido (`at_commit`).

## Decisão

1. **O cliente paga ao pedir**, como no WhatsApp: `payment.timing = "at_commit"` no canal `web`. O
   Pix nasce no checkout, com o cliente na tela; o cartão autoriza no checkout e é cobrado no
   aceite (captura manual).
2. **Sem "pagar na entrega" no site** (L2=1): os métodos do canal seguem `["pix", "card"]`. Pedido
   remoto pago antes não arrisca corrida paga para pedido que não se confirma.
3. **A loja tem prazo para aceitar**: `confirmation.mode = "auto_cancel"`, `timeout_minutes = 30`,
   contados em horário de loja aberta (`business_calendar.next_operational_deadline`: pedido feito
   com a loja fechada começa a contar na abertura). O Pix pago reinicia o prazo. Aos 10 minutos
   (`stale_new_alert_minutes`) o Gestor recebe o aviso "Se ninguém aceitar até HH:MM, ele é
   cancelado sozinho e o que o cliente pagou é devolvido"; o card do quadro mostra "cancela
   sozinho em".
4. **Recusou ou venceu, o dinheiro volta sozinho.** Os dois saem por `cancellation.cancel` e pelo
   `lifecycle._on_cancelled`: o Pix capturado é estornado e o cartão autorizado é anulado no
   Stripe (o caminho do #1732, que grita se o Stripe recusar). O cliente recebe o aviso do
   cancelamento ("Não conseguimos confirmar seu pedido dentro do prazo.", chave
   `store_did_not_confirm`) e o do estorno (`payment_refunded`, #1720).
5. **O cartão autorizado pode ser aceito.** Com `at_commit`, o portão de aceite exigia dinheiro
   capturado, e a captura do cartão é justamente o aceite: o pedido travava. O portão
   (`lifecycle.ensure_payment_captured`) passa a aceitar o cartão autorizado.

## Como vale no banco vivo

O seed cobre bancos novos. O alpha recebe a migração de dados `shop.0094_loja_online_paga_ao_pedir`
no deploy: troca `post_commit` → `at_commit` e `manual` → `auto_cancel` (30 min) no canal `web`,
só se ainda estiverem no valor de fábrica; outras chaves e ajustes feitos no Admin ficam.

## Consequências

- Recusa vira estorno. É custo de tarifa (Pix/cartão) e de confiança, e é por isso que a nota do
  dono existe: medir os estornos (`cancellation_reason` = `confirmation_timeout` ou recusa do
  operador, com `payment_refunded`) e reavaliar se ficarem constantes.
- Os 30 minutos são decisão operacional, ajustável no Admin do canal (`confirmation.timeout_minutes`);
  o aviso tem de continuar menor que o prazo.
- O WhatsApp segue `manual`: paga ao pedir, sem prazo de aceite. Dar a ele o mesmo prazo é
  decisão à parte.
