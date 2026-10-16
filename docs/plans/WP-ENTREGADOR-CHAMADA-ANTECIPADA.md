# WP-ENTREGADOR-CHAMADA-ANTECIPADA

Chamar o entregador da central (TaOn, via Machine) **durante o preparo**, para que
ele chegue quando a sacola fica pronta, e não depois.

Estado: **desenho aprovado pelo dono em 13/10/2026; o automático é pós-go-live.**
Antes dele, duas coisas já estão no ar: a coleta que ensina (PR 1) e um lembrete
temporário ao operador (PR 2). Nenhuma das duas decide sozinha.

## O que se aprendeu com o iFood

O iFood chama o entregador durante o preparo, pelo tempo de preparo que aprendeu
da loja; o "Pronto" da loja adianta a chamada; a loja ajusta o tempo em ±5 min.
A casa segue a mesma ideia, com a diferença de que a chamada é paga pela casa:
chamar cedo demais custa espera paga, chamar tarde custa pão frio.

## As regras (dono, 13/10/2026)

1. **Hora da chamada = início do preparo + preparo previsto − tempo de chegada do
   entregador.**
   - *Início do preparo*: o primeiro "Iniciar preparo" do KDS (`KDSTicket.started_at`,
     o menor entre as estações do pedido). Sem ele, `Order.preparing_at`.
   - *Preparo previsto*: aprendido do histórico (abaixo), por SKU, hora e dia.
   - *Tempo de chegada*: aprendido do histórico das corridas, por hora e dia.
2. **O Pronto do KDS é gatilho de reserva.** Se o pedido ficou pronto e a chamada
   ainda não saiu (previsão errada, ou pedido que não chama antes), o Pronto chama.
   É o que já acontece hoje com `fulfillment.courier="auto"` (`lifecycle.on_ready`).
3. **Só pedido JÁ PAGO chama antes.** Cobrança na porta e cliente novo chamam no
   Pronto: corrida paga para um pedido que pode não se confirmar é risco da casa.
4. **Encomenda usa os mesmos marcos, invertidos, a partir do horário marcado.**
   - chamada = horário marcado − tempo de chegada;
   - início do preparo = horário marcado − preparo previsto (é a Cozinha quem
     começa; o sistema só diz quando).
5. **iFood nunca chama** (quem entrega é o iFood; `courier.house_dispatches`, #1688).

## O que o modelo vai ler (coleta, PR 1)

Por pedido de entrega, com hora:

| Marco | Onde mora |
|---|---|
| Confirmado | `Order.accepted_at` |
| Início do preparo, por estação e por quem | `KDSTicket.started_at` / `started_by` (novo; vale para comanda não paga); `Order.data["kds_started"]` (pedido pago); `Order.preparing_at` |
| Pronto por estação, por quem e por qual porta | `KDSTicket.completed_at` / `completed_by` / `completed_via` |
| Pronto do pedido | `Order.ready_at` |
| Chamada pedida, por quem | evento `courier_dispatch_requested` (`OrderEvent.created_at`, `actor`) |
| Corrida aberta na central | `Order.data["courier"]["requested_at"]` |
| Aceita (A), em espera (S, se a Machine informar), coletou (E), finalizou (F), N/C | `Order.data["courier"]["status_at"]` (novo), também nas corridas arquivadas em `attempts` |
| Saiu / entregue / cancelado | `Order.dispatched_at` / `delivered_at` / `cancelled_at`; cancelamento da corrida em `courier_cancel_requested` |

Variáveis:

| Variável | Onde mora |
|---|---|
| SKUs e quantidades, nº de itens | `OrderItem` |
| Estação(ões) | `KDSTicket.kds_instance` |
| Hora e dia da semana | derivados dos marcos |
| Canal | `Order.channel_ref` |
| Operador que iniciou / marcou Pronto | `KDSTicket.started_by` / `completed_by` |
| Bairro e coordenadas | `Order.data["delivery_address_structured"]` (distância = da loja, derivada na leitura; `courier.estimate.km` quando cotado) |
| Encomenda | `Order.data["delivery_date"]` (`get_commitment_date`) |
| Carga simultânea da Cozinha | `KDSTicket.open_tickets_at_start` (novo: tickets abertos em todas as estações no instante do início) |

A leitura que já existe: `GET /api/v1/backstage/bi/delivery-timing/`
(`projections/bi_delivery_timing.py`): preparo real por SKU, hora e dia; chegada
do entregador (aceite e coleta) por hora e dia. Medianas, sem modelo.

## O lembrete temporário (PR 2)

Até o automático existir, o Gestor cobra o operador: X minutos (padrão 10,
configurável, liga/desliga em Admin → Loja → Entrega) depois do início do preparo
de uma entrega da casa sem corrida pedida, o cartão mostra o aviso "Pedido 0042 em
preparo há 10 min. Já dá para chamar o entregador?" com o botão "Chamar
entregador". É mecanismo independente: quando o automático chegar, o lembrete sai
inteiro (`Shop.defaults["delivery"]["courier_reminder"]` e o aviso do cartão).

## O que falta para o automático

1. Volume: semanas de corridas reais com `status_at` e preparos com `started_at`.
2. O previsor (mediana por SKU dominante × hora × dia, com piso de amostras e
   recuo para a mediana geral), e o ajuste ±5 min do dono no Admin.
3. A directive agendada `courier.dispatch` com `available_at` = hora da chamada,
   cancelada se o pedido for cancelado (#1693 já cancela corrida aberta) e
   adiantada pelo Pronto.
4. A trava do "já pago" (regra 3) no agendamento, não na tela.
