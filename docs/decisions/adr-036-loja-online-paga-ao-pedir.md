# ADR-036 — Loja online paga ao pedir, com prazo de aceite e estorno automático

**Status:** Aceito
**Data:** 2026-10-14
**Decisão:** dono, perguntas 1 e 2 de `docs/reference/cenarios-de-pedido.md`, L1=1 e L2=1
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
   sozinho em". (Emendado em 09/11/2026: 5 minutos no pedido do dia, 60 na encomenda, aviso a
   1/3 do prazo do pedido. Ver a emenda no fim.)
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
só se ainda estiverem no valor de fábrica; outras chaves e ajustes feitos no Admin ficam. (Os 30
viram 5 e 60 pela `shop.0114`: ver a emenda de 09/11/2026.)

## Consequências

- Recusa vira estorno. É custo de tarifa (Pix/cartão) e de confiança, e é por isso que a nota do
  dono existe: medir os estornos (`cancellation_reason` = `confirmation_timeout` ou recusa do
  operador, com `payment_refunded`) e reavaliar se ficarem constantes.
- Os 30 minutos são decisão operacional, ajustável no Admin do canal (`confirmation.timeout_minutes`);
  o aviso tem de continuar menor que o prazo. (Viraram 5 no dia e 60 na encomenda: ver a emenda
  de 09/11/2026.)
- O WhatsApp segue `manual`: paga ao pedir, sem prazo de aceite. Dar a ele o mesmo prazo é
  decisão à parte.

## Emenda 09/11/2026 (decisão do dono)

Os 30 minutos do item 3 eram "tempo demais" para quem pagou e espera a resposta (a referência é
o iFood, que dá 8 minutos: `shopman/shop/services/ifood_accept_sync.py`). O prazo de aceite passa
a depender de quando o pedido é para:

- **Pedido para o mesmo dia, feito com a casa aberta: 5 minutos** de loja aberta
  (`confirmation.timeout_minutes = 5`). É o único caso em que o cliente espera a resposta na hora
  e a equipe está na tela.
- **Todo o resto: 60 minutos** de loja aberta (`confirmation.preorder_timeout_minutes = 60`):
  a encomenda para outro dia (data combinada posterior a hoje) e o pedido que chega com a casa
  fechada, mesmo sendo para hoje. Quem encomenda ou pede de madrugada não está na tela esperando,
  e a casa precisa de tempo para olhar a produção. Canal sem a chave usa o `timeout_minutes`
  em todos os casos.

A contagem continua em minutos de loja aberta, e o Pix pago continua reiniciando o prazo. Loja
aberta vale nas duas pontas: pedido feito com a casa fechada começa a contar na abertura, e o
prazo que não cabe até o fechamento continua na abertura seguinte (encomenda paga às 19:30 com
a casa fechando às 20:00 vence 30 minutos depois de ela reabrir, não às 20:30 com a casa
fechada). O aviso de 1/3 anda na mesma conta.

O aviso de pedido parado deixa de ser um número do canal (`stale_new_alert_minutes`, recusado no
`auto_cancel`) e passa a sair a **1/3 do prazo do próprio pedido**, a mesma proporção dos 10 de 30:
1min40s no pedido do dia, 20 minutos na encomenda. O título da janela do aviso ("Responda em…")
conta até a mesma hora que o corpo diz ("se ninguém aceitar até HH:MM"): o aviso grava o prazo do
pedido em `respond_by`, em vez da régua de 5 minutos da casa.

Banco vivo: migração `shop.0114_prazo_de_aceite_5_no_dia_60_na_encomenda` (30 → 5 só se ainda
estiver no valor de fábrica; acrescenta o 60 da encomenda; tira o `stale_new_alert_minutes` dos
canais `auto_cancel`). O WhatsApp segue `manual`, como dito acima.

No Gestor, a meta do pedido novo com prazo agendado sai do próprio timer (o prazo gravado em
`timeout_minutes` no `confirmation.timeout`, contado para trás a partir do vencimento): o número
do card chega à meta no instante em que o "cancela sozinho em" zera. Antes a meta contava da
criação do pedido, e o Pix pago aos 7 minutos nascia atrasado numa meta de 5.

**Decidido pelo dono em 09/11/2026.** O pedido PARA HOJE pago com a casa fechada (de madrugada,
antes de abrir) tem o prazo longo: 60 minutos contados da abertura, com aviso aos 20. Antes vencia
5 minutos depois de abrir, com a equipe ainda chegando.