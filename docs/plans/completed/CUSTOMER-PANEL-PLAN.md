# CUSTOMER-PANEL — o cliente acessível a quem está com a mão na massa

**Decisão do dono (24/08/2026): "os dois"** — bloco no PDV **já** (fase 1,
entregue) + página de cliente no gestor como frente planejada (fase 2).

## Fase 1 — bloco no modal do PDV ✅ (entregue no PR do fiscal_prefs)

No card do cliente identificado, aparecendo só quando há dado:

- **Preferências persistentes** (liga E desliga): "CPF na nota por padrão" e
  "nota por e-mail por padrão" (`Customer.metadata.fiscal_prefs`). Semântica:
  desmarcar NA VENDA é "hoje não"; desligar AQUI é "nunca mais".
- **Restrições alimentares** (`metadata.preferences`) — chip de ALERTA
  (segurança: quem vende o croissant precisa ver) + editável.
- **Observações do balcão** (`Customer.notes`) — editável.
- **Aniversário**: chip do mês; no DIA, aviso elegante ao operador na
  identificação, citando a promoção de aniversariante ativa **se existir**
  (`Promotion.birthday_only` — o Core já a aplica sozinho no reprice; sem
  promoção configurada, o aviso é só o parabéns — nunca inventar desconto).
- Endpoint: `POST pos/customer/<ref>/profile/` (parcial; `operate_pos`).
- Paridade de config no Admin (checkboxes ao lado do "Conta na casa").

## Fase 2 — página de cliente no gestor (planejada, não iniciada)

`orders-nuxt` rota `/customers` + `/customers/<ref>` (URL em inglês, texto
pt-BR):

- busca (nome/telefone/CPF/e-mail — a search do PDV já existe no backstage);
- ficha completa: identidade, contatos, endereços, preferências (as mesmas da
  fase 1), conta na casa (saldo + histórico de acertos), loyalty, histórico de
  pedidos com estado fiscal;
- edição do que é operacional; o que é config sensível (ligar conta na casa,
  price_tier) continua no Admin ("Admin não OPERA" limita o Admin, não exila
  config — e conceder crédito é config).

Pré-requisito: projections de cliente no backstage (`customer_detail`), reuso
do contrato do PDV onde couber.

## Anotado para o futuro (pedido do dono, 24/08)

- **Tela do cliente (customer display do PDV)**: quando existir, dar os
  parabéns ao aniversariante na tela voltada ao cliente — ver
  memória `project_pos_customer_display`.
