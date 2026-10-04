/**
 * O detalhe de UM pedido, como as telas de operador o leem.
 *
 * Decisão do dono (28/09/2026): o detalhe do pedido do Gestor e o da encomenda
 * no PDV são telas IRMÃS — a mesma estrutura e o mesmo conteúdo, e só a barra de
 * ações muda de um contexto para o outro. O servidor serve um contrato só
 * (`shopman/backstage/projections/order_queue.py::OperatorOrderProjection`,
 * `build_operator_order(order, context=...)`), e este tipo é a PARTE COMUM dele:
 * o que o `OperatorOrderDetail` precisa para desenhar as seções.
 *
 * Cada app tem o contrato inteiro do seu lado (o Gestor pelo espelho gerado,
 * `orders-nuxt/app/generated/ordersContract.ts`; o PDV em `types/preorders.ts`) e
 * os dois casam com este por tipagem ESTRUTURAL, sem o kit importar app nenhum —
 * `defineProps<…>` resolve o tipo em tempo de compilação, e um tipo que mora
 * fora do kit deixaria o componente sem prop nenhuma.
 */

/** Uma ação que o servidor oferece no detalhe (a régua é dele; a tela obedece). */
export interface OrderDetailAction {
  ref: string;
  label: string;
  enabled: boolean;
  reason: string;
  payload_schema: Record<string, unknown>;
}

/** Um item do pedido que VALE agora (com os ajustes). */
export interface OrderDetailItem {
  sku: string;
  name: string;
  qty: string;
  unit_price_display: string;
  total_display: string;
}

/** Um evento do histórico. `operator_comment` é comentário de gente. */
export interface OrderDetailTimelineEvent {
  label: string;
  event_type: string;
  timestamp_display: string;
  actor: string;
  detail: string;
}

/** Quem é o cliente (WP-360): o servidor manda só o que sabe, já em português. */
export interface OrderDetailCustomerProfile {
  orders_label: string;
  last_order_display: string;
  average_ticket_display: string;
  favorite_product: string;
  segment_label: string;
  /** "success" | "warning" | "" — vazio é "segmento que não muda o atendimento". */
  segment_tone: string;
  notes: string;
  dietary_restrictions: string;
  birthday_display: string;
  is_birthday_today: boolean;
}

export interface OrderDetailFiscalLink {
  label?: string;
  href?: string;
  url?: string;
}

/** A parte comum do detalhe do pedido — o que as duas telas leem igual. */
export interface OperatorOrderDetail {
  ref: string;
  status: string;
  status_label: string;
  /** "orders" (Gestor) | "pos" (balcão): quem lê, e com isso as ações. */
  context: string;
  actions: OrderDetailAction[];
  channel_ref: string;
  channel_icon: string;
  total_display: string;
  customer_name: string;
  customer_ref: string;
  customer_phone: string;
  customer_phone_uri: string;
  customer_whatsapp_url: string;
  customer_email: string;
  customer_relay_phone: string;
  customer_relay_code: string;
  customer_relay_expires_at: string;
  fulfillment_type: string;
  fulfillment_label: string;
  /** "Sáb, 27/09 · 08h às 10h" — vazio no pedido de agora. */
  schedule_label: string;
  delivery_address: string;
  delivery_instructions: string;
  payment_method_label: string;
  payment_status_label: string;
  payment_link_notice: string;
  test_order_notice: string;
  is_gift: boolean;
  gift_recipient_name: string;
  gift_recipient_phone: string;
  gift_message: string;
  gift_hide_values: boolean;
  customer_profile: OrderDetailCustomerProfile | null;
  fiscal_status_label: string;
  fiscal_links: OrderDetailFiscalLink[];
  items: OrderDetailItem[];
  customer_note: string;
  kitchen_note: string;
  timeline: OrderDetailTimelineEvent[];
  /** O nome do canal como a loja o chama ("Loja online"); vazio cai no ref. */
  channel_name?: string;
  /** "aberto às 21:47" (o cabeçalho do detalhe em duas colunas). */
  opened_line?: string;
}
